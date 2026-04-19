# SBAT Practical Exam Slot Checker

## Project Purpose
Monitors Belgian SBAT driving exam booking system for available Type B (car) practical exam slots in East Flanders. Notifies users when new dates appear.

## Tech Stack
- **Language:** Python 3
- **HTTP:** requests
- **GUI:** PySide6 (cross-platform)
- **Auth:** Playwright (browser-based itsme OIDC authentication)
- **Timezone:** pytz (Europe/Brussels)
- **Packaging:** PyInstaller (sbat_checker.spec)

## Architecture
```
constants.py        — Shared API URLs, exam center IDs, payload templates
auth.py             — Authentication module (Playwright itsme + manual token fallback)
sbat.py             — CLI version (headless polling loop)
sbat_gui_pyside.py  — PySide6/Qt GUI (cross-platform)
```

## Authentication Flow
SBAT uses Belgium's itsme app (OpenID Connect) for authentication:
1. `AuthSession` opens a visible browser to `https://rijbewijs.sbat.be/praktijk/examen/login`
2. User confirms identity via itsme phone app (once)
3. Bearer token is captured from the callback URL or API request headers
4. Browser context stays alive — itsme session cookies are preserved
5. JWT `exp` claim is decoded to schedule a silent refresh ~5 min before expiry
6. On refresh: existing page navigates back to login URL; itsme session auto-completes OIDC without phone confirmation
7. If silent refresh fails (itsme session expired): user is prompted for full re-auth
8. Fallback: `--token` CLI flag or "Paste Token" GUI field (no silent refresh available for manual tokens)

## API Details
- **Base URL:** `https://api-rijbewijs.sbat.be/praktijk/api/`
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
python sbat_gui_pyside.py

# First run: install Playwright browser
playwright install chromium
```

## Token Handling
Bearer tokens have ~1 hour TTL and are kept in memory only. On expiry, the GUI prompts re-authentication. No tokens are persisted to disk.
