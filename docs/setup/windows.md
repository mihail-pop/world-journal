# Setup for Windows

## Windows Installer

On Windows 11, download `WorldJournalSetup.exe` from [GitHub Releases](https://github.com/mihail-pop/world-journal/releases) and run it. Setup installs its own Python and dependencies.

Choose the installation folder, port and startup mode. You can start World Journal manually, when you sign in to Windows, or when Windows starts. Starting before sign-in uses a service and requires administrator approval. Enable **Allow access from other devices on this network** if you want to connect over your local network.

Open **World Journal** from the Start menu or the optional desktop shortcut. The Start menu also has **Stop World Journal** and **Update World Journal**. An update keeps your library. The uninstaller keeps it unless you choose to remove it.

The default installation folder is `%USERPROFILE%\WorldJournal`. Within it, the database is at `library/database/db.sqlite3` and uploaded images are in `library/media/`. See [Authentication](../configuration/authentication.md) to set up a login for an installed copy.

## Manual Setup

1. Download and install [Python 3.13](https://www.python.org/downloads/). During installation enable **Add Python to PATH**.

2. Install [Git for Windows](https://git-scm.com/install/windows), then open PowerShell in the folder where you want the app installed.

3. Clone the repository and enter the project folder:

    ```powershell
    git clone https://github.com/mihail-pop/world-journal.git
    cd world-journal
    ```

4. Create the virtual environment:

    ```powershell
    python -m venv .venv
    ```

5. Install the dependencies:

    ```powershell
    .\.venv\Scripts\python.exe -m pip install -r requirements.txt
    ```

6. Create the database and news cache table:

    ```powershell
    .\.venv\Scripts\python.exe manage.py migrate
    .\.venv\Scripts\python.exe manage.py createcachetable world_journal_cache
    ```

7. Collect the static files used by both runserver and Waitress:

    ```powershell
    .\.venv\Scripts\python.exe manage.py collectstatic --noinput
    ```

8. World Journal detects your Windows timezone automatically. To override it for this terminal, set `TZ` to your IANA timezone:

    ```powershell
    $env:TZ="Europe/Bucharest"
    ```

    Dates, times and date filters use this timezone, including daylight-saving changes. Restart the server after changing the timezone.

9. Start World Journal with Django:

    ```powershell
    .\.venv\Scripts\python.exe manage.py runserver 0.0.0.0:8000 --noreload
    ```

    Or use Waitress for a machine that will keep the app running:

    ```powershell
    .\.venv\Scripts\python.exe -m waitress --listen=0.0.0.0:8000 --threads=8 config.wsgi:application
    ```

10. Open [http://localhost:8000](http://localhost:8000).

The terminal window must remain open while the app is running. Press `Ctrl+C` in that terminal when you want to stop it.

### Access from Other Devices

Run `ipconfig` and find the host computer's IPv4 address. A device on the same trusted network can then open an address such as `http://192.168.1.15:8000`.

Everyone who can reach the server can access the shared app unless [Authentication](../configuration/authentication.md) is enabled.

### Run Automatically on Startup

Create `run_world_journal.bat` in the project folder and update the path:

```bat
@echo off
cd /d "C:\path\to\world-journal"
set TZ=Europe/Bucharest
set PY=.venv\Scripts\python.exe
%PY% manage.py migrate
%PY% manage.py createcachetable world_journal_cache
%PY% manage.py collectstatic --noinput
%PY% -m waitress --listen=0.0.0.0:8000 --threads=8 config.wsgi:application
```

Press `Win+R`, enter `shell:startup` and create a `world_journal.vbs` file there:

```vbs
Set WshShell = CreateObject("WScript.Shell")
WshShell.Run """C:\path\to\world-journal\run_world_journal.bat""", 0
Set WshShell = Nothing
```

This starts the app after you log into Windows without leaving a terminal window open.

### Run Automatically on Boot

To start World Journal before login, install the batch file as a Windows service with a service manager such as NSSM:

```powershell
winget install nssm
nssm install WorldJournal
```

Select `run_world_journal.bat` as the application path, install the service and start it with:

```powershell
nssm start WorldJournal
```

### Updating

Stop the server, open PowerShell in the project folder and run:

```powershell
git pull
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py createcachetable world_journal_cache
.\.venv\Scripts\python.exe manage.py collectstatic --noinput
```

Start the server again and use `Ctrl+F5` in the browser so updated static files are loaded.

> **Note:** Export a backup from **Settings > Backup** before a major update. A manual install keeps the database in `database/db.sqlite3` and uploaded journal images in `media/`.

<div markdown="1" style="display: flex; justify-content: center; gap: 15px; flex-wrap: wrap;">

[Read the Remote Access Guide](../configuration/remote-access.md){ .md-button }
[Read the Authentication Guide](../configuration/authentication.md){ .md-button }

</div>
