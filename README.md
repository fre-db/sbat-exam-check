# SBAT Practical Exam Slot Checker

## English

### Description
This Python script automatically checks the SBAT practical driving exam booking system (`api.rijbewijs.sbat.be`) for available slots for the Type B (car) practical exam in the East Flanders region of Belgium. It monitors specific exam centers and notifies the user via a system dialog or console message when new dates become available.

### Features
* Checks for available Type B (E2) practical exam slots periodically, starting from the next day.
* Monitors the following exam centers in East Flanders: Brakel, Sint-Niklaas, St-Denijs, Erembodegem, Eeklo.
* Prompts the user to enter credentials if the configuration file or credentials are missing, and saves them.
* Displays a system notification when new, previously unseen dates are found.


### Releases / Pre-compiled Versions
For users who prefer not to install Python or manage dependencies, pre-compiled versions for macOS and Windows are available.

1.  **Download:** Go to the [**Releases**](https://github.com/fre-db/sbat-exam-check/releases) page of this GitHub repository.
    * **Windows:** Download the `sbat-windows.exe` file.
    * **macOS:** Download the `sbat-mac` file.
2.  **Run:**
    * **Windows:** Double-click the `.exe` file. You might see a Windows SmartScreen warning because the application isn't signed. Click "More info" and then "Run anyway".
    * **macOS:** Double-click the file. You might see a security warning because the application is from an unidentified developer. Right-click (or Control-click) the app icon, choose "Open", and then click "Open" in the dialog box. You only need to do this the first time.
3.  **First usage:** When you run the application for the first time, it will look for `config.ini` in the *same folder*. If not found, it will prompt you to enter your credentials and create the `config.ini` file.
4.  **Operation:** The application will run in the background (likely opening a terminal/console window on Windows, or just running without a visible window after the initial permission on macOS). It will display system notifications when new exam slots are found. To stop it, close the terminal/console window or use the Activity Monitor (macOS) / Task Manager (Windows) to end the process.

### Script usage
1.  Ensure you have Python and the required libraries installed (`pip install requests pytz`).
2.  Place the `sbat.py` script in a directory.
3.  Run the script from your terminal: `python sbat.py`
4.  If `config.ini` is not set up, follow the prompts to enter your credentials.
5.  The script will run continuously in the background, checking for available slots and displaying notifications when new ones are found.


### Configuration
1.  The script uses a `config.ini` file located in the same directory as the script (or the executable's directory if packaged).
2.  If the file doesn't exist or lacks credentials, the script will prompt you to enter your SBAT username and password, which it will then save to `config.ini`.
3.  The file structure should look like this:
    ```ini
    [Credentials]
    username = YOUR_SBAT_USERNAME
    password = YOUR_SBAT_PASSWORD
    ```

### How it Works
The script authenticates with the SBAT API using your credentials. It then enters an infinite loop, periodically sending requests to the API for each specified exam center to check for available slots. It compares the found slots with those seen in the previous check. If new dates are detected, it triggers a system notification. The check frequency increases during times when new slots are typically released.

### Disclaimer
* This script relies on an unofficial API endpoint (`api.rijbewijs.sbat.be`) used by the SBAT booking system. This API may change without notice, which could break the script.
* Use this script responsibly and ensure compliance with the SBAT website's terms of service.
* The script stores your SBAT credentials in plain text in the `config.ini` file. Ensure this file is kept secure.

---

## Nederlands

### Beschrijving
Dit Python-script controleert automatisch het SBAT-boekingssysteem (`api.rijbewijs.sbat.be`) voor beschikbare tijdsloten voor het praktijkexamen rijbewijs Type B (auto) in de regio Oost-Vlaanderen, België. Het monitort specifieke examencentra en geeft de gebruiker een melding via een systeembericht of consolebericht wanneer er nieuwe data beschikbaar komen.

### Functies
* Controleert periodiek op beschikbare praktijkexamen-slots voor Type B (E2) vanaf de volgende dag.
* Monitort de volgende examencentra in Oost-Vlaanderen: Brakel, Sint-Niklaas, St-Denijs, Erembodegem, Eeklo.
* Gebruikt inloggegevens uit een `config.ini`-bestand voor authenticatie.
* Vraagt de gebruiker om inloggegevens in te voeren als het configuratiebestand of de gegevens ontbreken, en slaat deze op.
* Toont een dialoog wanneer nieuwe, nog niet eerder geziene data worden gevonden.


### Releases / Gecompileerde Versies
Voor gebruikers die liever geen Python installeren of dependencies beheren, zijn voorgecompileerde versies voor macOS en Windows beschikbaar.

1.  **Downloaden:** Ga naar de [**Releases**](https://github.com/fre-db/sbat-exam-check/releases) pagina van deze GitHub repository.
    * **Windows:** Download het `sbat-windows.exe`-bestand
    * **macOS:** Download het `sbat-mac` bestand. 
2.  **Uitvoeren:**
    * **Windows:** Dubbelklik op het `.exe`-bestand. U krijgt mogelijk een Windows SmartScreen-waarschuwing omdat de applicatie niet is ondertekend. Klik op "Meer informatie" en vervolgens op "Toch uitvoeren".
    * **macOS:** Dubbelklik op het bestand. U krijgt mogelijk een beveiligingswaarschuwing omdat de applicatie van een onbekende ontwikkelaar afkomstig is. Klik met de rechtermuisknop (of Control-klik) op het app-pictogram, kies "Open" en klik vervolgens op "Open" in het dialoogvenster. Dit hoeft u alleen de eerste keer te doen.
3.  **Eerste gebruik:** Wanneer u het voor de eerste keer uitvoert, zoekt het naar `config.ini` in *dezelfde map*. Als het bestand niet wordt gevonden, wordt u gevraagd uw inloggegevens in te voeren en wordt het `config.ini`-bestand aangemaakt.
4.  **Werking:** De applicatie draait op de achtergrond (opent waarschijnlijk een terminal/console-venster op Windows, of draait zonder zichtbaar venster na de eerste toestemming op macOS). Het toont systeemmeldingen wanneer nieuwe examen-slots worden gevonden. Om te stoppen, sluit u het terminal/console-venster of gebruikt u de Activiteitenweergave (macOS) / Taakbeheer (Windows) om het proces te beëindigen.

### Script gebruik
1.  Zorg ervoor dat Python en de vereiste bibliotheken zijn geïnstalleerd (`pip install requests pytz`).
2.  Plaats het `sbat.py`-script in een map.
3.  Voer het script uit vanaf uw terminal: `python sbat.py`
4.  Als `config.ini` niet bestaat, volg dan de instructies om uw inloggegevens in te voeren.
5.  Het script draait continu op de achtergrond, controleert op beschikbare slots en toont meldingen wanneer er nieuwe worden gevonden.


### Configuratie
1.  Het script gebruikt een `config.ini`-bestand in dezelfde map als het script (of de map van het uitvoerbare bestand indien verpakt).
2.  Als het bestand niet bestaat of geen inloggegevens bevat, zal het script vragen om uw SBAT-gebruikersnaam en -wachtwoord in te voeren, die het vervolgens opslaat in `config.ini`.
3.  De bestandsstructuur moet er als volgt uitzien:
    ```ini
    [Credentials]
    username = UW_SBAT_GEBRUIKERSNAAM
    password = UW_SBAT_WACHTWOORD
    ```

### Hoe het Werkt
Het script authenticeert bij de SBAT API met uw inloggegevens. Vervolgens gaat het een oneindige lus in, waarbij het periodiek verzoeken naar de API stuurt voor elk opgegeven examencentrum om te controleren op beschikbare slots. Het vergelijkt de gevonden slots met die van de vorige controle. Als er nieuwe data worden gedetecteerd, activeert het een systeemmelding. De controlefrequentie neemt toe tijdens de uren waarop doorgaans nieuwe slots worden vrijgegeven.

### Disclaimer
* Dit script maakt gebruik van een onofficieel API-eindpunt (`api.rijbewijs.sbat.be`) dat wordt gebruikt door het SBAT-boekingssysteem. Deze API kan zonder kennisgeving wijzigen, wat het script onbruikbaar kan maken.
* Gebruik dit script op verantwoorde wijze en zorg ervoor dat u voldoet aan de gebruiksvoorwaarden van de SBAT-website.
* Het script slaat uw SBAT-inloggegevens in platte tekst op in het `config.ini`-bestand. Zorg ervoor dat dit bestand veilig wordt bewaard.
