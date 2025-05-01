# sbat_gui_qt.py
import requests
import pytz
import configparser
import os
import sys
import threading
import queue  # For thread-safe communication
from constants import *

# --- PySide6 Imports ---
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QGridLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QMessageBox,
    QSizePolicy,
)
from PySide6.QtCore import QTimer, Qt, Slot  # Import Slot explicitly
from PySide6.QtGui import QTextCursor, QFont  # Import QFont


# --- Global Variables ---
checking_thread = None
stop_event = threading.Event()
auth_token = None
all_dates_seen = set()
previous_dates = set()
gui_queue = queue.Queue()  # Queue for thread-safe GUI updates


# --- Utility Functions (Mostly Unchanged) ---
def get_config_path():
    """Determines the correct path for the config.ini file."""
    if getattr(sys, "frozen", False):
        # If the application is run as a bundle, the PyInstaller bootloader
        # extends the sys module by a flag frozen=True and sets the app
        # path into variable _MEIPASS'.
        base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, CONFIG_FILENAME)


def log_message(message):
    """Safely adds a message to the GUI log area from any thread via queue."""
    gui_queue.put(message)


def load_credentials_from_config():
    """Loads credentials from config.ini if it exists."""
    config_file = get_config_path()
    config = configparser.ConfigParser()
    username, password = "", ""
    if os.path.exists(config_file):
        try:
            config.read(config_file)
            username = config.get("Credentials", "username", fallback="")
            password = config.get("Credentials", "password", fallback="")
        except configparser.Error as e:
            print(
                f"[Config Load Error] {config_file}: {e}"
            )  # Log to console before GUI starts
    return {"username": username, "password": password}


def save_credentials_to_config(username, password):
    """Saves credentials to config.ini."""
    config_file = get_config_path()
    config = configparser.ConfigParser()
    if os.path.exists(config_file):
        try:
            config.read(config_file)
        except configparser.Error as e:
            log_message(f"Warning: Could not read existing config before saving: {e}")
            config = configparser.ConfigParser()

    if "Credentials" not in config:
        config.add_section("Credentials")

    config.set("Credentials", "username", username)
    config.set("Credentials", "password", password)

    try:
        with open(config_file, "w") as configfile:
            config.write(configfile)
        log_message(f"Credentials saved to '{config_file}'.")
        return True
    except IOError as e:
        log_message(f"Error saving credentials to {config_file}: {e}")
        # Show Qt error dialog (needs main window reference or call directly)
        show_error_dialog_qt("File Error", f"Could not save credentials:\n{e}")
        return False


def get_sleep_time() -> int:
    """Calculates sleep time based on Brussels time."""
    try:
        brussels_tz = pytz.timezone("Europe/Brussels")
        now_brussels = datetime.now(brussels_tz)
        hour_in_brussels = now_brussels.hour
        # New slots get added at these times usually
        if hour_in_brussels == 7 or hour_in_brussels == 16:
            log_message(
                f"Brussels time {now_brussels.strftime('%H:%M')}. Using short sleep (30s)."
            )
            return 30
    except Exception as e:
        log_message(
            f"Warning: Could not determine Brussels time ({e}). Defaulting to 120s sleep."
        )
    return 120


# --- Qt Specific Helpers ---
def show_error_dialog_qt(title, message, parent=None):
    """Displays a Qt error message dialog."""
    msg_box = QMessageBox(parent)
    msg_box.setIcon(QMessageBox.Icon.Critical)
    msg_box.setWindowTitle(title)
    msg_box.setText(message)
    msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
    msg_box.exec()


def show_info_dialog_qt(title, message, parent=None):
    """Displays a Qt info message dialog."""
    msg_box = QMessageBox(parent)
    msg_box.setIcon(QMessageBox.Icon.Information)
    msg_box.setWindowTitle(title)
    msg_box.setText(message)  # Use setText for primary message if short
    # msg_box.setInformativeText(message) # Use for longer secondary text if needed
    msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
    msg_box.exec()


# --- API Interaction (Unchanged) ---
def attempt_authentication(username, password):
    """Attempts to authenticate and returns the token or None."""
    global auth_token
    headers = {"Content-Type": "application/json", "User-Agent": USER_AGENT}
    credentials = {"username": username, "password": password}
    log_message("Attempting authentication...")
    try:
        response = requests.post(
            AUTH_URL, json=credentials, headers=headers, timeout=15
        )
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)

        if response.text:  # Check if response body is not empty
            log_message("Authentication successful.")
            auth_token = response.text.strip('"')  # Remove potential quotes
            return auth_token
        else:
            log_message(
                f"Authentication failed. Status: {response.status_code}, Empty Response Body"
            )
            auth_token = None
            return None

    except requests.exceptions.HTTPError as http_err:
        log_message(
            f"Authentication failed. Status: {http_err.response.status_code}, Response: {http_err.response.text[:200]}..."
        )
        auth_token = None
        return None
    except requests.exceptions.RequestException as e:
        log_message(f"Network error during authentication: {e}")
        auth_token = None
        return None
    except Exception as e:  # Catch other potential errors
        log_message(f"An unexpected error occurred during authentication: {e}")
        auth_token = None
        return None


def run_checks(username, password):
    """The main checking loop running in the background thread."""
    global auth_token, all_dates_seen, previous_dates

    # Initial authentication attempt within the thread
    if not auth_token:
        if not attempt_authentication(username, password):
            log_message("Initial authentication failed in thread. Stopping checks.")
            gui_queue.put("STOPPED_AUTH_FAILURE")
            return  # Stop the thread if initial auth fails

    headers = {
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
        "Authorization": f"Bearer {auth_token}",
    }

    log_message("Starting SBAT exam check loop...")
    while not stop_event.is_set():
        centers_with_new_data = {}
        current_run_dates = set()
        request_failed_in_cycle = False
        auth_needed = False

        for center_id, center_name in CENTER_IDS:
            if stop_event.is_set():
                break  # Exit loop immediately if stop is requested

            payload = PAYLOAD_BASE.copy()
            payload["examCenterId"] = center_id
            # Ensure start date is always calculated relative to now
            payload["startDate"] = (
                f"{(datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')}T00:00"
            )

            try:
                response = requests.post(
                    AVAILABLE_URL, headers=headers, json=payload, timeout=20
                )

                if response.status_code == 200:
                    if data := response.json():
                        center_dates = {
                            # Use YYYY-MM-DD format consistently
                            center_name + " " + slot.get("from", "")[:10]
                            for slot in data
                            if slot.get("from")  # Ensure 'from' exists
                        }
                        current_run_dates.update(center_dates)
                        # Find dates for this center that haven't been seen *at all* before
                        new_dates_for_center = center_dates - all_dates_seen
                        if new_dates_for_center:
                            # Store the raw data for formatting later
                            centers_with_new_data[center_name] = data

                elif response.status_code == 401:
                    log_message(
                        f"Authorization token expired or invalid (checking {center_name}). Re-authenticating..."
                    )
                    auth_needed = True
                    break  # Break inner loop to re-authenticate

                else:
                    # Raise an exception for non-200/401 status codes
                    response.raise_for_status()

            except requests.exceptions.HTTPError as http_err:
                log_message(
                    f"HTTP error checking {center_name}: {http_err.response.status_code} - {http_err.response.text[:200]}..."
                )
                request_failed_in_cycle = True
            except requests.exceptions.RequestException as req_err:
                log_message(f"Network error checking {center_name}: {req_err}")
                request_failed_in_cycle = True
            except Exception as e:
                log_message(f"Unexpected error checking {center_name}: {e}")
                request_failed_in_cycle = True

        # --- After checking all centers ---

        if stop_event.is_set():
            break  # Exit outer loop if stop is requested

        if auth_needed:
            log_message("Attempting re-authentication...")
            new_token = attempt_authentication(username, password)
            if new_token:
                auth_token = new_token  # Update global token
                headers["Authorization"] = (
                    f"Bearer {new_token}"  # Update headers for next cycle
                )
                log_message("Re-authentication successful. Continuing checks.")
                # Optional: Add a short sleep before continuing to avoid hammering API
                stop_event.wait(5)
                continue  # Restart the check cycle immediately
            else:
                log_message("Re-authentication failed. Stopping checks.")
                gui_queue.put("STOPPED_AUTH_FAILURE")
                break  # Exit outer loop

        # Process results only if the cycle didn't fail and wasn't interrupted for auth
        if not request_failed_in_cycle:
            # Find dates found in this run that were not found in the *previous* run
            newly_found_dates_since_last = current_run_dates - previous_dates

            if centers_with_new_data and newly_found_dates_since_last:
                center_messages = []
                log_message("--- NEW DATES FOUND! ---")
                # Sort centers by name for consistent output
                for center in sorted(centers_with_new_data.keys()):
                    data = centers_with_new_data[center]
                    # Extract unique dates found *in this run* for this center
                    dates_in_run = sorted(
                        list(
                            {
                                slot.get("from", "")[:10]
                                for slot in data
                                if slot.get("from")
                            }
                        )
                    )
                    # Filter to show only dates that are actually new since the last check
                    new_dates_output = [
                        d
                        for d in dates_in_run
                        if f"{center} {d}" in newly_found_dates_since_last
                    ]

                    if new_dates_output:
                        msg = f"  {center}: {', '.join(new_dates_output)}"
                        center_messages.append(msg)
                        log_message(msg)  # Log each center individually

                log_message("-------------------------")

                if center_messages:
                    # Send message to GUI thread to show the dialog
                    dialog_message = "\n".join(center_messages)
                    gui_queue.put(("SHOW_INFO", dialog_message))
                else:
                    # This case might happen if data structure changes or filtering is too strict
                    log_message(
                        "New data detected but couldn't format message (or no truly new dates)."
                    )

                # Update seen dates *after* processing
                all_dates_seen.update(current_run_dates)
                previous_dates = current_run_dates.copy()

            elif not newly_found_dates_since_last and not request_failed_in_cycle:
                log_message(
                    f"No new dates detected. Total unique dates seen so far: {len(all_dates_seen)}"
                )
                # Still update previous_dates even if no new ones, in case some disappeared
                previous_dates = current_run_dates.copy()
                # Ensure all_dates_seen includes everything from this run too
                all_dates_seen.update(current_run_dates)
            else:
                # This case covers request_failed_in_cycle = True
                log_message("Check cycle completed with errors. Will retry.")
                # Do not update previous_dates or all_dates_seen if errors occurred

        # --- Sleep before next cycle ---
        if not stop_event.is_set():
            sleep_duration = get_sleep_time()
            log_message(f"Sleeping for {sleep_duration} seconds...")
            stop_event.wait(sleep_duration)  # Use wait() for interruptible sleep

    # --- End of While Loop ---
    log_message("Checking loop stopped.")
    # Send stop message only if not already stopped by auth failure
    if not auth_needed:  # Avoid sending duplicate stop messages
        # Check if queue is not full before putting (optional, good practice)
        if not gui_queue.full():
            gui_queue.put("STOPPED_NORMAL")


# --- Qt Application Class ---
class SbatCheckerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SBAT Exam Slot Checker")
        self.setGeometry(100, 100, 600, 450)  # x, y, width, height

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        self.main_layout = QVBoxLayout(self.central_widget)

        # --- Credentials Group ---
        cred_group = QGroupBox("Credentials")
        cred_layout = QGridLayout(cred_group)  # Use QGridLayout for alignment

        user_label = QLabel("Username:")
        self.user_entry = QLineEdit()
        pass_label = QLabel("Password:")
        self.pass_entry = QLineEdit()
        self.pass_entry.setEchoMode(QLineEdit.EchoMode.Password)  # Mask password

        cred_layout.addWidget(user_label, 0, 0)
        cred_layout.addWidget(self.user_entry, 0, 1)
        cred_layout.addWidget(pass_label, 1, 0)
        cred_layout.addWidget(self.pass_entry, 1, 1)

        self.main_layout.addWidget(cred_group)

        # --- Control Area ---
        # Using a simple layout for just one button
        self.start_stop_button = QPushButton("Start Checking")
        self.start_stop_button.clicked.connect(self.on_start_stop_clicked)
        # Make button take minimum horizontal space
        self.start_stop_button.setSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed
        )
        self.main_layout.addWidget(
            self.start_stop_button, alignment=Qt.AlignmentFlag.AlignLeft
        )

        # --- Log Area ---
        log_group = QGroupBox("Log Output")
        log_layout = QVBoxLayout(log_group)  # Use QVBoxLayout inside group

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        log_layout.addWidget(self.log_view)
        # Make log area expand vertically and horizontally
        log_group.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.log_view.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        self.main_layout.addWidget(log_group)

        # --- Initial Setup ---
        initial_creds = load_credentials_from_config()
        self.user_entry.setText(initial_creds.get("username", ""))
        self.pass_entry.setText(initial_creds.get("password", ""))

        if initial_creds.get("username"):
            self.append_log("Credentials loaded from config.ini.")
        else:
            self.append_log("config.ini not found or empty. Please enter credentials.")

        # --- Queue Timer ---
        self.queue_timer = QTimer(self)
        self.queue_timer.timeout.connect(self.process_gui_queue_qt)
        self.queue_timer.start(100)  # Check queue every 100ms

    def append_log(self, message):
        """Appends a message to the Qt QTextEdit."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_view.append(f"{timestamp} - {message}")
        # Auto-scroll to the end
        self.log_view.moveCursor(QTextCursor.MoveOperation.End)
        # self.log_view.ensureCursorVisible() # Alternative scrolling method

    @Slot()  # Decorator to explicitly mark as a Qt slot
    def process_gui_queue_qt(self):
        """Processes messages from the queue to update the GUI."""
        try:
            while not gui_queue.empty():  # Check if queue is empty first
                message = gui_queue.get_nowait()  # Use get_nowait
                if message == "STOPPED_AUTH_FAILURE":
                    self.append_log("Authentication failed. Controls reset.")
                    self.reset_gui_controls()
                elif message == "STOPPED_NORMAL":
                    self.append_log("Checker stopped normally. Controls reset.")
                    self.reset_gui_controls()
                elif isinstance(message, tuple) and message[0] == "SHOW_INFO":
                    show_info_dialog_qt("NEW DATES FOUND", message[1], parent=self)
                elif isinstance(message, str):  # Log string messages
                    self.append_log(message)
                else:
                    self.append_log(
                        f"Received unexpected message type: {type(message)}"
                    )

        except queue.Empty:
            pass  # No messages in the queue

    @Slot()
    def on_start_stop_clicked(self):
        """Handles the Start/Stop button click."""
        if self.start_stop_button.text() == "Start Checking":
            self.start_checking()
        else:
            self.stop_checking()

    def start_checking(self):
        global checking_thread, stop_event, auth_token, all_dates_seen, previous_dates

        if checking_thread and checking_thread.is_alive():
            self.append_log("Checker is already running.")
            return

        user = self.user_entry.text()
        pwd = self.pass_entry.text()

        if not user or not pwd:
            show_error_dialog_qt(
                "Input Required",
                "Please enter both username and password.",
                parent=self,
            )
            return

        # Reset state variables
        stop_event.clear()
        auth_token = None  # Reset token before attempting auth
        all_dates_seen = set()
        previous_dates = set()

        # Clear the log before starting a new check run
        # self.log_view.clear() # Optional: uncomment to clear log on start

        # Update GUI immediately to provide feedback
        self.user_entry.setEnabled(False)
        self.pass_entry.setEnabled(False)
        self.start_stop_button.setText("Starting...")
        self.start_stop_button.setEnabled(False)  # Disable button during initial auth
        QApplication.processEvents()  # Process GUI events to show changes

        # Perform initial authentication in a separate thread to avoid blocking GUI
        auth_thread = threading.Thread(
            target=self._initial_auth_and_start, args=(user, pwd), daemon=True
        )
        auth_thread.start()

    def _initial_auth_and_start(self, user, pwd):
        """Helper function to run initial auth in a thread."""
        global checking_thread
        token = attempt_authentication(user, pwd)

        # Use queue to communicate result back to GUI thread
        if token:
            gui_queue.put(("AUTH_SUCCESS", user, pwd))
        else:
            gui_queue.put("AUTH_FAILURE")

    @Slot()  # Process messages from the auth thread
    def process_gui_queue_qt(self):
        """Processes messages from the queue to update the GUI."""
        try:
            while not gui_queue.empty():
                message_data = gui_queue.get_nowait()

                if (
                    isinstance(message_data, tuple)
                    and message_data[0] == "AUTH_SUCCESS"
                ):
                    _, user, pwd = message_data  # Unpack data
                    self.append_log("Initial authentication successful.")
                    save_credentials_to_config(user, pwd)  # Save credentials

                    # Update GUI to 'running' state
                    self.start_stop_button.setText("Stop Checking")
                    self.start_stop_button.setEnabled(True)  # Re-enable button

                    # Start the main checking thread
                    checking_thread = threading.Thread(
                        target=run_checks, args=(user, pwd), daemon=True
                    )
                    checking_thread.start()

                elif message_data == "AUTH_FAILURE":
                    self.append_log("Initial authentication failed.")
                    show_error_dialog_qt(
                        "Authentication Failed",
                        "Could not authenticate. Check details and logs.",
                        parent=self,
                    )
                    self.reset_gui_controls()  # Reset GUI back to initial state

                # --- Handle other messages ---
                elif message_data == "STOPPED_AUTH_FAILURE":
                    self.append_log(
                        "Authentication failed during checks. Controls reset."
                    )
                    self.reset_gui_controls()
                elif message_data == "STOPPED_NORMAL":
                    self.append_log("Checker stopped normally. Controls reset.")
                    self.reset_gui_controls()
                elif isinstance(message_data, tuple) and message_data[0] == "SHOW_INFO":
                    show_info_dialog_qt("NEW DATES FOUND", message_data[1], parent=self)
                elif isinstance(message_data, str):  # Log string messages
                    self.append_log(message_data)
                else:
                    self.append_log(
                        f"Received unexpected message type: {type(message_data)}"
                    )

        except queue.Empty:
            pass  # No messages in the queue

    def stop_checking(self):
        global checking_thread
        if checking_thread and checking_thread.is_alive():
            self.append_log("Stopping checker...")
            stop_event.set()
            # The thread checks stop_event periodically and will exit.
            # We reset GUI controls when the "STOPPED_NORMAL" message is received.
            self.start_stop_button.setText("Stopping...")
            self.start_stop_button.setEnabled(False)  # Disable while stopping
        else:
            self.append_log("Checker is not running.")
            self.reset_gui_controls()  # Reset if already stopped

    def reset_gui_controls(self):
        """Resets the GUI controls to the 'stopped' state."""
        self.user_entry.setEnabled(True)
        self.pass_entry.setEnabled(True)
        self.start_stop_button.setText("Start Checking")
        self.start_stop_button.setEnabled(True)
        # Logging is handled by the caller or queue message

    def closeEvent(self, event):
        """Handles window close event."""
        global checking_thread
        self.append_log("Close requested.")
        if self.queue_timer:
            self.queue_timer.stop()  # Stop the queue timer

        if checking_thread and checking_thread.is_alive():
            self.append_log("Stopping checker thread...")
            stop_event.set()
            # Give the thread a moment to stop - adjust timeout as needed
            checking_thread.join(timeout=1.5)
            if checking_thread.is_alive():
                self.append_log("Warning: Checker thread did not stop gracefully.")

        self.append_log("Exiting application.")
        event.accept()  # Accept the close event


# --- Main Execution ---
if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = SbatCheckerWindow()
    win.show()
    sys.exit(app.exec())
