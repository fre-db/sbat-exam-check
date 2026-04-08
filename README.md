# SBAT Practical Exam Slot Checker

## English

### Description
This Python script periodically checks the SBAT practical driving exam booking system (`api-rijbewijs.sbat.be`) for available slots for the Type B (car) practical exam in the East Flanders region of Belgium. It monitors specific exam centers and notifies the user via a system dialog and console message when new dates become available.

### Releases / Pre-compiled Versions
For users who prefer not to install Python or manage dependencies, pre-compiled versions for macOS and Windows are available.

1.  **Download:** Go to the [**Releases**](https://github.com/fre-db/sbat-exam-check/releases) page of this GitHub repository.
    * **Windows:** Download the `sbat-windows.exe` file.
    * **macOS:** Download the `sbat-mac` file.
2.  **Run:**
    * **Windows:** Double-click the `.exe` file. You might see a Windows SmartScreen warning because the application isn't signed. Click "More info" and then "Run anyway".
    * **macOS:** Double-click the file. You might see a security warning because the application is from an unidentified developer. Right-click (or Control-click) the app icon, choose "Open", and then click "Open" in the dialog box. You only need to do this the first time.
3.  **Operation:** The application will run in the background (likely opening a terminal/console window on Windows, or just running without a visible window after the initial permission on macOS). It will display system notifications when new exam slots are found. To stop it, close the terminal/console window or use the Activity Monitor (macOS) / Task Manager (Windows) to end the process.

### Script usage (with devbox)
1.  Install [devbox](https://www.jetify.com/devbox) if you don't have it.
2.  Run `devbox run setup` to install Python dependencies and the Playwright browser.
3.  Run one of the scripts:
    * `devbox run cli` (CLI)
    * `devbox run gui` (GUI)

### Script usage (manual)
1.  Ensure you have Python 3 and the required libraries installed (`pip install -r requirements.txt`).
2.  Install the Playwright browser: `playwright install chromium`
3.  Run one of the scripts from your terminal:
    * `python3 sbat.py` (CLI)
    * `python3 sbat_gui_pyside.py` (GUI)

### Authentication
SBAT uses Belgium's **itsme** app for authentication. When you start the application:
1. A browser window opens to the SBAT login page.
2. Complete the itsme verification on your phone.
3. The application captures your session token automatically and begins checking for slots.

Alternatively, you can manually provide a Bearer token:
* CLI: `python3 sbat.py --token YOUR_BEARER_TOKEN`
* GUI: Use the "Paste Token" field

Tokens are kept in memory only (~1 hour TTL) and are not saved to disk.

### Disclaimer
* This script relies on an unofficial API endpoint (`api-rijbewijs.sbat.be`) used by the SBAT booking system. This API may change without notice, which could break the script.
* Use this script responsibly and ensure compliance with the SBAT website's terms of service.

---

## Nederlands

### Beschrijving
Dit Python-script controleert automatisch het SBAT-boekingssysteem (`api-rijbewijs.sbat.be`) voor beschikbare tijdsloten voor het praktijkexamen rijbewijs Type B (auto) in de regio Oost-Vlaanderen, België. Het monitort periodiek specifieke examencentra en geeft de gebruiker een melding via een systeembericht en consolebericht wanneer er nieuwe data beschikbaar komen.

### Releases / Gecompileerde Versies
Voor gebruikers die liever geen Python installeren of dependencies beheren, zijn voorgecompileerde versies voor macOS en Windows beschikbaar.

1.  **Downloaden:** Ga naar de [**Releases**](https://github.com/fre-db/sbat-exam-check/releases) pagina van deze GitHub repository.
    * **Windows:** Download het `sbat-windows.exe`-bestand
    * **macOS:** Download het `sbat-mac` bestand. 
2.  **Uitvoeren:**
    * **Windows:** Dubbelklik op het `.exe`-bestand. U krijgt mogelijk een Windows SmartScreen-waarschuwing omdat de applicatie niet is ondertekend. Klik op "Meer informatie" en vervolgens op "Toch uitvoeren".
    * **macOS:** Dubbelklik op het bestand. U krijgt mogelijk een beveiligingswaarschuwing omdat de applicatie van een onbekende ontwikkelaar afkomstig is. Klik met de rechtermuisknop (of Control-klik) op het app-pictogram, kies "Open" en klik vervolgens op "Open" in het dialoogvenster. Dit hoeft u alleen de eerste keer te doen.
3.  **Werking:** De applicatie draait op de achtergrond (opent waarschijnlijk een terminal/console-venster op Windows, of draait zonder zichtbaar venster na de eerste toestemming op macOS). Het toont systeemmeldingen wanneer nieuwe examen-slots worden gevonden. Om te stoppen, sluit u het terminal/console-venster of gebruikt u de Activiteitenweergave (macOS) / Taakbeheer (Windows) om het proces te beëindigen.

### Script gebruik (met devbox)
1.  Installeer [devbox](https://www.jetify.com/devbox) als u dit nog niet heeft.
2.  Voer `devbox run setup` uit om Python-afhankelijkheden en de Playwright-browser te installeren.
3.  Voer een van de scripts uit:
    * `devbox run cli` (CLI)
    * `devbox run gui` (GUI)

### Script gebruik (manueel)
1.  Zorg ervoor dat Python 3 en de vereiste bibliotheken zijn geïnstalleerd (`pip install -r requirements.txt`).
2.  Installeer de Playwright-browser: `playwright install chromium`
3.  Voer een van de scripts uit vanaf uw terminal:
    * `python3 sbat.py` (CLI)
    * `python3 sbat_gui_pyside.py` (GUI)

### Authenticatie
SBAT gebruikt de Belgische **itsme**-app voor authenticatie. Wanneer u de applicatie start:
1. Er opent een browservenster naar de SBAT-loginpagina.
2. Bevestig uw identiteit via de itsme-app op uw telefoon.
3. De applicatie vangt uw sessietoken automatisch op en begint met het controleren van beschikbare slots.

U kunt ook handmatig een Bearer-token invoeren:
* CLI: `python3 sbat.py --token UW_BEARER_TOKEN`
* GUI: Gebruik het "Paste Token"-veld

Tokens worden alleen in het geheugen bewaard (~1 uur geldig) en worden niet op schijf opgeslagen.

### Disclaimer
* Dit script maakt gebruik van een onofficieel API-eindpunt (`api-rijbewijs.sbat.be`) dat wordt gebruikt door het SBAT-boekingssysteem. Deze API kan zonder kennisgeving wijzigen, wat het script onbruikbaar kan maken.
* Gebruik dit script op verantwoorde wijze en zorg ervoor dat u voldoet aan de gebruiksvoorwaarden van de SBAT-website.
