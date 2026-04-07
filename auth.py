"""
Authentication module for SBAT exam checker.

Supports two methods:
1. Playwright-based browser auth (itsme OIDC flow)
2. Manual token paste (fallback)
"""

import configparser
import os
import sys
import time

from constants import CONFIG_FILENAME, SBAT_LOGIN_URL, AVAILABLE_URL


def get_config_path():
    if getattr(sys, "frozen", False):
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, CONFIG_FILENAME)


def load_cached_token():
    """Load a previously cached Bearer token from config.ini."""
    config_file = get_config_path()
    config = configparser.ConfigParser()
    if os.path.exists(config_file):
        try:
            config.read(config_file)
            return config.get("Token", "bearer", fallback=None)
        except configparser.Error:
            pass
    return None


def save_cached_token(token):
    """Save a Bearer token to config.ini for reuse."""
    config_file = get_config_path()
    config = configparser.ConfigParser()
    if os.path.exists(config_file):
        try:
            config.read(config_file)
        except configparser.Error:
            config = configparser.ConfigParser()

    if "Token" not in config:
        config.add_section("Token")

    config.set("Token", "bearer", token)

    with open(config_file, "w") as f:
        config.write(f)


def test_token(token):
    """Test if a Bearer token is still valid by making a lightweight API request."""
    import requests
    from constants import CENTER_IDS, USER_AGENT

    headers = {
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
        "Authorization": f"Bearer {token}",
    }
    # Test with a single center
    center_id = CENTER_IDS[0][0]
    from datetime import datetime, timedelta

    payload = {
        "licenseType": "B",
        "examType": "E2",
        "examCenterId": center_id,
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
    the itsme OIDC flow on their phone. The script intercepts API requests to
    capture the resulting Bearer token.

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
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        def on_request(request):
            nonlocal captured_token
            if captured_token:
                return
            # Look for requests to the SBAT API that carry a Bearer token
            auth_header = request.headers.get("authorization", "")
            if (
                "api.rijbewijs.sbat.be" in request.url
                and auth_header.startswith("Bearer ")
            ):
                token = auth_header[len("Bearer "):]
                if token:
                    captured_token = token
                    log("Bearer token captured successfully.")

        page.on("request", on_request)

        page.goto(SBAT_LOGIN_URL)

        # Wait for the token to be captured (timeout after 120 seconds)
        timeout = 120
        start = time.time()
        while not captured_token and time.time() - start < timeout:
            try:
                page.wait_for_timeout(500)
            except Exception:
                break

        if not captured_token:
            # Try to extract token from localStorage/sessionStorage as fallback
            try:
                for storage_fn in [
                    "localStorage",
                    "sessionStorage",
                ]:
                    result = page.evaluate(
                        f"""() => {{
                        const storage = window.{storage_fn};
                        for (let i = 0; i < storage.length; i++) {{
                            const key = storage.key(i);
                            const val = storage.getItem(key);
                            if (val && val.length > 20 && val.length < 2000) {{
                                // Heuristic: tokens are typically long strings
                                if (key.toLowerCase().includes('token') || key.toLowerCase().includes('auth') || key.toLowerCase().includes('bearer')) {{
                                    return val;
                                }}
                            }}
                        }}
                        return null;
                    }}"""
                    )
                    if result:
                        captured_token = result.strip('"')
                        log("Token found in browser storage.")
                        break
            except Exception:
                pass

        browser.close()

    if captured_token:
        save_cached_token(captured_token)
        return captured_token
    else:
        log("Authentication timed out. No token captured within 120 seconds.")
        return None


def get_token(manual_token=None, log_fn=None):
    """
    Get a valid Bearer token using the best available method.

    Tries in order:
    1. Manual token (if provided via --token flag or paste)
    2. Cached token from config.ini (if still valid)
    3. Browser-based itsme authentication

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

    # 1. Manual token
    if manual_token:
        log("Using manually provided token...")
        if test_token(manual_token):
            save_cached_token(manual_token)
            return manual_token
        else:
            log("Manually provided token is invalid or expired.")

    # 2. Cached token
    cached = load_cached_token()
    if cached:
        log("Testing cached token...")
        if test_token(cached):
            log("Cached token is still valid.")
            return cached
        else:
            log("Cached token expired.")

    # 3. Browser auth
    return authenticate_with_browser(log_fn=log_fn)
