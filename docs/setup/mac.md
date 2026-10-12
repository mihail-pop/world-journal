# Setup for Mac

1. Download and install [Python 3.13](https://www.python.org/downloads/).

    After installation, open the **Python 3.13** folder in Applications and run `Install Certificates.command`.

2. Open Terminal inside the folder where you want to keep the app.

3. Clone the repository and enter the project folder:

    ```sh
    git clone https://github.com/mihail-pop/world-journal.git
    cd world-journal
    ```

    If Git is not installed, macOS will offer to install the Command Line Developer Tools. Install them and run the command again.

4. Create the virtual environment:

    ```sh
    python3 -m venv .venv
    ```

5. Install the dependencies:

    ```sh
    .venv/bin/python -m pip install -r requirements.txt
    ```

6. Create the database and news cache table:

    ```sh
    .venv/bin/python manage.py migrate
    .venv/bin/python manage.py createcachetable world_journal_cache
    ```

7. Collect the static files used by both runserver and Waitress:

    ```sh
    .venv/bin/python manage.py collectstatic --noinput
    ```

8. Start World Journal with your IANA timezone:

    ```sh
    TZ=Europe/Bucharest .venv/bin/python manage.py runserver 0.0.0.0:8000 --noreload
    ```

    Or use Waitress for a machine that will keep the app running:

    ```sh
    TZ=Europe/Bucharest .venv/bin/python -m waitress --listen=0.0.0.0:8000 --threads=8 config.wsgi:application
    ```

9. Open [http://localhost:8000](http://localhost:8000).

The Terminal window must remain open while the app is running. Press `Control+C` in that window when you want to stop it.

## Access from Other Devices

Hold `Option` and click the Wi-Fi icon to find the Mac's IP address. A device on the same trusted network can open an address such as `http://192.168.1.15:8000`.

Everyone who can reach the server can access the shared app unless [Authentication](../configuration/authentication.md) is enabled.

## Run Automatically on Startup

Create `~/Library/LaunchAgents/com.worldjournal.plist` and replace `/PATH/TO/YOUR/` with the real project path:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.worldjournal</string>
    <key>WorkingDirectory</key>
    <string>/PATH/TO/YOUR/world-journal</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>TZ</key>
        <string>Europe/Bucharest</string>
    </dict>
    <key>ProgramArguments</key>
    <array>
        <string>/PATH/TO/YOUR/world-journal/.venv/bin/python</string>
        <string>-m</string>
        <string>waitress</string>
        <string>--listen=0.0.0.0:8000</string>
        <string>--threads=8</string>
        <string>config.wsgi:application</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
```

Load the service:

```sh
launchctl load ~/Library/LaunchAgents/com.worldjournal.plist
```

Use `launchctl unload` with the same path to stop automatic startup.

## Run Automatically on Boot

The same service can run before login from `/Library/LaunchDaemons/`, but system daemons require ownership and permission changes. Use the login LaunchAgent unless the Mac is a dedicated server and you are comfortable managing launchd services.

## Updating

Stop the server, open Terminal in the project folder and run:

```sh
git pull
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py createcachetable world_journal_cache
.venv/bin/python manage.py collectstatic --noinput
```

Start the server again and perform a hard refresh in the browser so updated static files are loaded.

> **Note:** Export a backup from **Settings > Backup** before a major update. The app keeps personal data in `db.sqlite3` and uploaded journal images in `media/`.

<div markdown="1" style="display: flex; justify-content: center; gap: 15px; flex-wrap: wrap;">

[Read the Remote Access Guide](../configuration/remote-access.md){ .md-button }
[Read the Authentication Guide](../configuration/authentication.md){ .md-button }

</div>
