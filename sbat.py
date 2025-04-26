import requests
import time
import pytz
from datetime import datetime, timedelta
import subprocess
import configparser
import os
import sys
import platform


def get_credentials(write: bool = False):
    config = configparser.ConfigParser()
    if getattr(sys, "frozen", False):
        #  If the script is frozen (e.g., packaged by PyInstaller)
        config_file = os.path.join(os.path.dirname(sys.executable), "config.ini")
    else:
        #  If the script is run directly
        config_file = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "config.ini"
        )

    if not os.path.exists(config_file):
        print(f"Configuration file '{config_file}' not found. Creating a new one.")
        config["Credentials"] = {}  # Create the section
    else:
        config.read(config_file)

    if (
        write
        or "Credentials" not in config
        or "username" not in config["Credentials"]
        or "password" not in config["Credentials"]
    ):
        print("Credentials not found in configuration. Please enter them.")
        config["Credentials"]["username"] = input("Enter your username: ")
        config["Credentials"]["password"] = input("Enter your password: ")

        with open(config_file, "w") as configfile:
            config.write(configfile)
        print(f"Credentials saved to '{config_file}'.")

    return dict(config["Credentials"])


url = "https://api.rijbewijs.sbat.be/praktijk/api/exam/available"
auth_url = "https://api.rijbewijs.sbat.be/praktijk/api/user/authenticate"
auth = get_credentials()

# An example response from the SBAT API
response_example = [
    {
        "id": 316276,
        "typesBlob": '["B"]',
        "examTypesBlob": '["E2"]',
        "examType": "E2",
        "from": "2024-08-30T10:15:00",
        "till": "2024-08-30T11:10:00",
        "dayScheduleId": 135,
        "examCenterId": 7,
        "drivingSchool": None,
        "examinee": None,
        "isPublic": True,
    },
    {
        "id": 316289,
        "typesBlob": '["B"]',
        "examTypesBlob": '["E2"]',
        "examType": "E2",
        "from": "2024-08-30T09:20:00",
        "till": "2024-08-30T10:15:00",
        "dayScheduleId": 131,
        "examCenterId": 7,
        "drivingSchool": None,
        "examinee": None,
        "isPublic": True,
    },
    {
        "id": 316341,
        "typesBlob": '["B"]',
        "examTypesBlob": '["E2"]',
        "examType": "E2",
        "from": "2024-08-30T11:10:00",
        "till": "2024-08-30T12:05:00",
        "dayScheduleId": 131,
        "examCenterId": 7,
        "drivingSchool": None,
        "examinee": None,
        "isPublic": True,
    },
    {
        "id": 340213,
        "typesBlob": '["B"]',
        "examTypesBlob": '["E2"]',
        "examType": "E2",
        "from": "2024-08-30T16:05:00",
        "till": "2024-08-30T17:00:00",
        "dayScheduleId": 131,
        "examCenterId": 7,
        "drivingSchool": None,
        "examinee": None,
        "isPublic": True,
    },
]

# IDs of the 5 exam centers in East-Flanders
center_ids = [
    (7, "Brakel"),
    (10, "Sint-Niklaas"),
    (1, "St-Denijs"),
    (9, "Erembodegem"),
    (8, "Eeklo"),
]
# We search for exam dates for Rijbewijs B, from tomorrow onwards
payload = {
    "licenseType": "B",
    "examType": "E2",
    # "startDate": f'{datetime.now().strftime("%Y-%m-%d")}T00:00'
    "startDate": f"{(datetime.now() + timedelta(hours=24)).strftime('%Y-%m-%d')}T00:00",
}
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
    auth_response = requests.post(auth_url, json=auth, headers=headers)
    if auth_response.status_code == 401:
        print(
            "Wrong username/password, update config.ini",
            auth_response.status_code,
            auth_response.text,
        )
        display_error(auth_response)
        auth_response = requests.post(
            auth_url, json=get_credentials(write=True), headers=headers
        )
    headers["Authorization"] = f"Bearer {auth_response.text}"


headers = {
    "Content-Type": "application/json",
    "User-Agent": "curl/7.64.1",
}
update_auth(headers)

while True:
    check_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    centers_available, new_dates = {}, set()
    for id, center in center_ids:
        payload["examCenterId"] = id
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code != 200:
            print(check_timestamp, "PROBLEM", response.status_code, response.content)
            update_auth(headers)
            response = requests.post(url, headers=headers, json=payload)

            if not response.status_code != 200:
                print(check_timestamp, "CRASH", response.status_code, response.content)
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
