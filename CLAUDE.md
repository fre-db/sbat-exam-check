# SBAT Practical Exam Slot Checker

## Project Purpose
Monitors Belgian SBAT driving exam booking system for available Type B (car) practical exam slots in East Flanders. Notifies users when new dates appear.

## Tech Stack
- **Language:** Python 3
- **HTTP:** requests
- **GUI:** PySide6 (macOS/Windows), GTK3 via PyGObject (Linux)
- **Auth:** Playwright (browser-based itsme OIDC authentication)
- **Timezone:** pytz (Europe/Brussels)
- **Packaging:** PyInstaller (sbat_checker_qt.spec)

## Architecture
```
constants.py        — Shared API URLs, exam center IDs, payload templates
auth.py             — Authentication module (Playwright itsme + manual token fallback)
sbat.py             — CLI version (headless polling loop)
sbat_gui_pyside.py  — PySide6/Qt GUI (macOS/Windows)
sbat_gui_gtk.py     — GTK3 GUI (Linux)
config.ini          — Local credential/token cache (gitignored)
```

## Authentication Flow
SBAT uses Belgium's itsme app (OpenID Connect) for authentication:
1. Playwright opens `https://rijbewijs.sbat.be/praktijk/examen/login` in a visible browser
2. User confirms identity via itsme phone app
3. Script intercepts the resulting Bearer token from network requests to `api.rijbewijs.sbat.be`
4. Token is cached to `config.ini` and reused until 401
5. Fallback: `--token` CLI flag or "Paste Token" GUI field for manual token entry

## API Details
- **Base URL:** `https://api.rijbewijs.sbat.be/praktijk/api/`
- **Availability endpoint:** `POST /exam/available` with Bearer token
- **Payload:** `{ licenseType: "B", examType: "E2", examCenterId: <id>, startDate: "<ISO>" }`
- **Monitored centers:** Brakel(7), Sint-Niklaas(10), St-Denijs(1), Erembodegem(9), Eeklo(8)

## Key Conventions
- **Adaptive polling:** 30s at 7AM/4PM Brussels time (when new slots typically appear), 120s otherwise
- **Thread-safe GUI:** Background polling thread communicates with GUI via `queue.Queue` (100ms poll)
- **Cross-platform notifications:** AppleScript (macOS), ctypes MessageBox (Windows), console (Linux)
- **State tracking:** `all_dates_seen` (cumulative) and `previous_dates` (last check) sets for change detection

## Running
```bash
# CLI
python sbat.py
python sbat.py --token <bearer-token>  # manual token

# GUI
python sbat_gui_pyside.py   # macOS/Windows
python sbat_gui_gtk.py       # Linux

# First run: install Playwright browser
playwright install chromium
```

## Config
`config.ini` is auto-created in the script directory. Stores cached Bearer token. Gitignored — never commit.
