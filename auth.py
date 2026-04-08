"""
Authentication module for SBAT exam checker.

Supports two methods:
1. Playwright-based browser auth (itsme OIDC flow)
2. Manual token paste (fallback)

Tokens are ~1 hour TTL so they are only kept in memory, not persisted to disk.
"""

import time

from constants import SBAT_LOGIN_URL, AVAILABLE_URL


def test_token(token):
    """Test if a Bearer token is still valid by making a lightweight API request."""
    import requests
    from constants import CENTER_IDS, USER_AGENT
    from datetime import datetime, timedelta

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
    Open a browser for itsme authentication and capture the Bearer token.

    Opens the SBAT login page in a visible Chromium browser. The user completes
    the itsme OIDC flow on their phone. The script intercepts the resulting
    Bearer token from the callback URL or API request headers.

    Args:
        log_fn: Optional callback for log messages (e.g., gui_queue.put)

    Returns:
        The Bearer token string, or None if authentication failed/timed out.
    """
    def log(msg):
        if log_fn:
            log_fn(msg)
        else:
            print(msg)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log("Playwright is not installed. Install with: pip install playwright && playwright install chromium")
        return None

    captured_token = None

    log("Opening browser for itsme authentication...")
    log("Please confirm your identity in the itsme app on your phone.")

    with sync_playwright() as p:
        # Try system Chrome first (no need for playwright install chromium),
        # fall back to Playwright's bundled Chromium
        try:
            browser = p.chromium.launch(headless=False, channel="chrome")
        except Exception:
            browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        def on_request(request):
            nonlocal captured_token
            if captured_token:
                return
            url = request.url

            # Method 1: Extract token from callback URL query parameter
            # SBAT redirects to /callback?token=<JWT> after itsme auth
            if "callback" in url and "token=" in url:
                try:
                    from urllib.parse import urlparse, parse_qs
                    parsed = urlparse(url)
                    token_values = parse_qs(parsed.query).get("token", [])
                    if token_values:
                        captured_token = token_values[0]
                        log("Token captured from callback URL.")
                        return
                except Exception:
                    pass

            # Method 2: Intercept Bearer token from API request headers
            if "rijbewijs" in url and "sbat" in url:
                auth_header = request.headers.get("authorization", "")
                if auth_header.lower().startswith("bearer "):
                    token = auth_header[7:]  # Skip "bearer " (7 chars)
                    if token:
                        captured_token = token
                        log("Token captured from request Authorization header.")

        page.on("request", on_request)

        page.goto(SBAT_LOGIN_URL)

        # Wait for the token to be captured (timeout after 120 seconds)
        timeout = 120
        start = time.time()
        while not captured_token and time.time() - start < timeout:
            try:
                page.wait_for_timeout(1000)
            except Exception:
                break

        browser.close()

    if captured_token:
        return captured_token
    else:
        log("Authentication timed out. No token captured within 120 seconds.")
        return None


def get_token(manual_token=None, log_fn=None):
    """
    Get a valid Bearer token using the best available method.

    Tries in order:
    1. Manual token (if provided via --token flag or paste)
    2. Browser-based itsme authentication

    Args:
        manual_token: A manually provided Bearer token (optional)
        log_fn: Optional callback for log messages

    Returns:
        A valid Bearer token string, or None if all methods fail.
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
