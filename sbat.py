import argparse
import requests
import time
import pytz
import subprocess
import sys
import platform

from constants import *
from auth import get_token, authenticate_with_browser

all_dates_seen = set()
previous_dates = set()


def display_dialog(center_to_data: dict[str, list[dict]]):
    center_messages = [
        center + " " + ", ".join({slot.get("from", "")[:10] for slot in data}) + "\\n"
        for center, data in center_to_data.items()
    ]
    message = "\\n".join(center_messages)

    if platform.system() == "Darwin":  # macOS
        script = f'''
        tell app "System Events"
            display dialog "{message}" with title "Dates available"
        end tell
        '''
        subprocess.call(["osascript", "-e", script])
    elif platform.system() == "Windows":
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, message, "Dates available", 0)
    else:  # For other operating systems (e.g., Linux)
        print("Dates available:\n", message)  # Fallback to printing in the terminal


def display_error(response):
    """Display an error dialog box, cross-platform."""
    error_message = response.text
    if platform.system() == "Darwin":  # macOS
        script = """
        on run argv
            set dialogText to item 1 of argv
            tell app "System Events"
                display dialog dialogText with title "Exam crawl failure"
            end tell
        end run
        """
        subprocess.call(["osascript", "-e", script, error_message])
    elif platform.system() == "Windows":
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, error_message, "Exam crawl failure", 0)
    else:  # For other operating systems
        print("Error:", error_message)  # Fallback to printing in the terminal


def get_sleep_time() -> int:
    # Checks every 2 minutes and every 30 seconds at 7AM and 4PM (most likely time for new dates)
    hour_in_brussels = datetime.now().astimezone(pytz.timezone("Europe/Brussels")).hour
    return 30 if hour_in_brussels in {7, 16} else 120


def update_auth(headers: dict):
    """Re-authenticate via browser-based itsme flow."""
    print("Token expired or invalid. Re-authenticating...")
    token = authenticate_with_browser()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    else:
        print("Re-authentication failed.")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SBAT Exam Slot Checker")
    parser.add_argument("--token", help="Manually provide a Bearer token (skip browser auth)")
    args = parser.parse_args()

    token = get_token(manual_token=args.token)
    if not token:
        print("Authentication failed. Exiting.")
        sys.exit(1)

    headers = {
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
        "Authorization": f"Bearer {token}",
    }

    while True:
        check_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        centers_available, new_dates = {}, set()
        for id, center in CENTER_IDS:
            PAYLOAD_BASE["examCenterId"] = id
            response = requests.post(AVAILABLE_URL, headers=headers, json=PAYLOAD_BASE)
            if response.status_code != 200:
                print(
                    check_timestamp, "PROBLEM", response.status_code, response.content
                )
                update_auth(headers)
                response = requests.post(AVAILABLE_URL, headers=headers, json=PAYLOAD_BASE)

                if not response.status_code != 200:
                    print(
                        check_timestamp, "CRASH", response.status_code, response.content
                    )
                    display_error(response)
                    sys.exit(1)

            if data := response.json():
                centers_available[center] = data
                new_dates = new_dates.union(
                    {center + " " + slot.get("from", "")[:10] for slot in data}
                )

        all_dates_seen = all_dates_seen.union(new_dates)
        if centers_available and not new_dates.issubset(previous_dates):
            previous_dates = new_dates
            print(check_timestamp, centers_available.items())
            display_dialog(centers_available)
        else:
            print(check_timestamp, "nothing new going on", all_dates_seen)

        time.sleep(get_sleep_time())
