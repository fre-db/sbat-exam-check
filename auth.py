"""
Authentication module for SBAT exam checker.

Supports two methods:
1. AuthSession — persistent Playwright browser session with silent token refresh
2. Manual token paste (fallback)

Tokens are ~1 hour TTL. AuthSession keeps the browser context alive so the
itsme session cookies persist, enabling silent re-authentication without
requiring the user to confirm on their phone again.
"""

import base64
import json
import queue
import threading
import time
from datetime import datetime, timezone

from constants import SBAT_LOGIN_URL, AVAILABLE_URL


def _decode_jwt_exp(token):
    """
    Decode the JWT payload and return the expiry as a UTC datetime.
    Does not verify the signature — only used for scheduling refresh.
    Returns None if decoding fails.
    """
    try:
        payload_b64 = token.split(".")[1]
        # JWT uses base64url encoding without padding
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        exp = payload.get("exp")
        if exp:
            return datetime.fromtimestamp(exp, tz=timezone.utc)
    except Exception:
        pass
    return None


def _capture_token_from_request(request):
    """
    Try to extract a Bearer token from a Playwright request.
    Returns the token string or None. Caller is responsible for logging.
    """
    url = request.url

    # Method 1: Token in callback URL query parameter
    if "callback" in url and "token=" in url:
        try:
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(url)
            token_values = parse_qs(parsed.query).get("token", [])
            if token_values:
                return token_values[0]
        except Exception:
            pass

    # Method 2: Bearer token in Authorization request header
    if "rijbewijs" in url and "sbat" in url:
        auth_header = request.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            token = auth_header[7:]
            if token:
                return token

    return None


class AuthSession:
    """
    Manages a persistent Playwright browser session for SBAT itsme authentication.

    Keeps the browser context alive after initial auth so itsme session cookies
    are preserved. Subsequent token refreshes navigate the same page back to the
    login URL — if the itsme session is still valid, a new JWT is issued without
    requiring phone confirmation.

    Uses a dedicated background thread for all Playwright operations (Playwright
    sync API must be used from a single thread).
    """

    def __init__(self, log_fn=None):
        self._log_fn = log_fn
        self._command_queue = queue.Queue()
        self._thread = None
        self.token = None
        self.token_expiry = None  # UTC datetime

    def _log(self, msg):
        if self._log_fn:
            self._log_fn(msg)
        else:
            print(msg)

    def start(self):
        """
        Launch the browser and perform initial itsme authentication.
        Blocks until a token is captured or timeout (120s).
        Returns the token string, or None on failure.
        """
        result = {"token": None}
        done = threading.Event()
        self._thread = threading.Thread(
            target=self._run_loop, args=(result, done), daemon=True
        )
        self._thread.start()
        done.wait()  # Wait for initial auth to complete
        return result["token"]

    def refresh_token(self):
        """
        Silently refresh the token by clearing localStorage and navigating to the
        app, which causes the SPA to redirect to login. Relies on itsme session
        cookies being preserved in the browser context.
        Blocks until a new token is captured or timeout (60s).
        Returns the new token string, or None if silent refresh failed.
        """
        result = {"token": None}
        done = threading.Event()
        self._command_queue.put(("refresh", result, done))
        done.wait(timeout=65)  # 5s buffer over the 60s internal timeout
        return result["token"]

    def close(self):
        """Clean up the browser and stop the Playwright thread."""
        if self._thread and self._thread.is_alive():
            self._command_queue.put(("close", None, None))
            self._thread.join(timeout=5)

    def _run_loop(self, initial_result, initial_done):
        """
        Playwright thread main loop. Handles initial auth then processes
        refresh/close commands from the queue.
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self._log("Playwright is not installed. Run: pip install playwright && playwright install chromium")
            initial_result["token"] = None
            initial_done.set()
            return

        with sync_playwright() as p:
            # Try system Chrome first, fall back to Playwright's bundled Chromium
            try:
                browser = p.chromium.launch(headless=False, channel="chrome")
            except Exception:
                browser = p.chromium.launch(headless=False)

            context = browser.new_context()
            page = context.new_page()

            # --- Initial authentication ---
            token = self._wait_for_token(page, timeout=120)
            initial_result["token"] = token
            if token:
                self.token = token
                self.token_expiry = _decode_jwt_exp(token)
            initial_done.set()

            if not token:
                browser.close()
                return

            # Minimize the browser window so it doesn't steal focus during
            # silent refresh navigations (macOS brings Chrome to the front on
            # page.goto, which buries the Qt GUI).
            try:
                cdp = context.new_cdp_session(page)
                window_info = cdp.send("Browser.getWindowForTarget")
                cdp.send("Browser.setWindowBounds", {
                    "windowId": window_info["windowId"],
                    "bounds": {"windowState": "minimized"},
                })
            except Exception:
                pass  # Window management is best-effort

            # --- Command loop: process refresh/close requests ---
            while True:
                try:
                    cmd, result, done = self._command_queue.get(timeout=1)
                except queue.Empty:
                    continue

                if cmd == "close":
                    break

                if cmd == "refresh":
                    new_token = self._wait_for_token(
                        page, timeout=60, skip_token=self.token
                    )
                    if new_token:
                        self.token = new_token
                        self.token_expiry = _decode_jwt_exp(new_token)
                        self._log("Token refreshed silently.")
                    else:
                        self._log("Silent refresh failed. Re-authentication required.")
                    result["token"] = new_token
                    done.set()

            browser.close()

    def _wait_for_token(self, page, timeout, skip_token=None):
        """
        Navigate to the SBAT app and wait for a token to be captured.

        skip_token: if set, ignore any captured token that matches this value.
                    Used during refresh to avoid re-capturing the expiring token
                    that the SBAT SPA sends in Authorization headers on page load.

        For silent refresh: clears localStorage so the SPA detects no token and
        redirects itself to the login route, then checks the privacy policy
        checkbox and clicks the itsme button. The itsme IDP session cookies
        are preserved in the browser context, so OIDC completes without phone
        confirmation and the new token arrives via the callback URL.

        Returns the token string or None on timeout.
        """
        captured = {"token": None}

        def on_request(request):
            if captured["token"]:
                return
            token = _capture_token_from_request(request)
            if token and token != skip_token:
                self._log("Token captured.")
                captured["token"] = token

        page.on("request", on_request)

        try:
            if skip_token:
                self._log("Attempting silent token refresh...")
                # Clear localStorage so the SPA detects no token and redirects to login
                page.evaluate("localStorage.clear()")
                page.goto("https://rijbewijs.sbat.be/praktijk/examen/overview")
                self._log(f"[diag] landed on: {page.url}")
                try:
                    page.wait_for_load_state("networkidle", timeout=5000)
                except Exception as e:
                    self._log(f"[diag] networkidle: {e}")
                try:
                    page.click('label:has-text("privacybeleid")', timeout=5000)
                    self._log("Checked privacy policy checkbox.")
                    page.click('div.btn', timeout=5000)
                    self._log("Clicked itsme login button.")
                except Exception as e:
                    self._log(f"[diag] Login interaction failed: {e}")

                if not captured["token"]:
                    # Wait a few seconds to see where the itsme redirect lands.
                    # If still on itsme.be after this, the IDP session expired and
                    # phone confirmation is required — fail fast instead of waiting 60s.
                    page.wait_for_timeout(5000)
                    post_click_url = page.url
                    self._log(f"[diag] post-click URL: {post_click_url}")
                    if "itsme.be" in post_click_url:
                        self._log("itsme session expired. Phone confirmation required — silent refresh not possible.")
                        return None
            else:
                self._log("Opening browser for itsme authentication...")
                self._log("Please confirm your identity in the itsme app on your phone.")
                page.goto(SBAT_LOGIN_URL)

            start = time.time()
            while not captured["token"] and time.time() - start < timeout:
                try:
                    page.wait_for_timeout(500)
                except Exception:
                    break
        finally:
            page.remove_listener("request", on_request)

        if not captured["token"]:
            self._log(f"Authentication timed out after {timeout}s.")
        return captured["token"]


# ---------------------------------------------------------------------------
# Standalone helpers — used for manual token paste and CLI --token flag
# ---------------------------------------------------------------------------

def test_token(token):
    """Test if a Bearer token is still valid by making a lightweight API request."""
    import requests
    from constants import CENTER_IDS, USER_AGENT
    from datetime import timedelta

    headers = {
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
        "Authorization": f"Bearer {token}",
    }
    payload = {
        "licenseType": "B",
        "examType": "E2",
        "examCenterId": CENTER_IDS[0][0],
        "startDate": f"{(datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')}T00:00",
    }
    try:
        response = requests.post(AVAILABLE_URL, headers=headers, json=payload, timeout=10)
        return response.status_code == 200
    except Exception:
        return False


def authenticate_with_browser(log_fn=None):
    """
    Convenience function for one-shot browser auth (CLI use).
    Opens a browser, waits for token, closes browser.
    For the GUI, prefer AuthSession which keeps the browser alive for silent refresh.
    """
    session = AuthSession(log_fn=log_fn)
    token = session.start()
    # For one-shot use, close immediately after getting the token
    if token:
        session.close()
    return token


def get_token(manual_token=None, log_fn=None):
    """
    Get a valid Bearer token using the best available method.

    Tries in order:
    1. Manual token (if provided via --token flag)
    2. Browser-based itsme authentication

    For the GUI, use AuthSession directly instead to enable silent refresh.
    """
    def log(msg):
        if log_fn:
            log_fn(msg)
        else:
            print(msg)

    if manual_token:
        log("Using manually provided token...")
        if test_token(manual_token):
            return manual_token
        else:
            log("Manually provided token is invalid or expired.")

    return authenticate_with_browser(log_fn=log_fn)
