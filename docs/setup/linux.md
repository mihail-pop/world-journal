# Setup for Linux (Ubuntu/Debian)

1. Install Python, virtual environment support and Git:

    ```sh
    sudo apt update
    sudo apt install python3 python3-pip python3-venv git
    ```

2. Navigate to the folder where you want to keep the app, then clone the repository:

    ```sh
    git clone https://github.com/mihail-pop/world-journal.git
    cd world-journal
    ```

3. Create the virtual environment:

    ```sh
    python3 -m venv .venv
    ```

4. Install the dependencies:

    ```sh
    .venv/bin/python -m pip install -r requirements.txt
    ```

5. Create the database and news cache table:

    ```sh
    .venv/bin/python manage.py migrate
    .venv/bin/python manage.py createcachetable world_journal_cache
    ```

6. Collect the static files used by both runserver and Waitress:

    ```sh
    .venv/bin/python manage.py collectstatic --noinput
    ```

7. Start World Journal with your IANA timezone:

    ```sh
    TZ=Europe/Bucharest .venv/bin/python manage.py runserver 0.0.0.0:8000 --noreload
    ```

    Or use Waitress for a machine that will keep the app running:

    ```sh
    TZ=Europe/Bucharest .venv/bin/python -m waitress --listen=0.0.0.0:8000 --threads=8 config.wsgi:application
    ```

8. Open [http://localhost:8000](http://localhost:8000).

The terminal must remain open while the app is running. Press `Ctrl+C` when you want to stop it.

## Access from Other Devices

Find the host computer's IP address:

```sh
hostname -I
```

A device on the same trusted network can open an address such as `http://192.168.1.15:8000`. Everyone who can reach the server can access the shared app unless [Authentication](../configuration/authentication.md) is enabled.

## Run Automatically on Boot

Create `/etc/systemd/system/worldjournal.service` and replace the username and project path:

```ini
[Unit]
Description=World Journal Waitress Server
After=network.target

[Service]
User=YOUR_LINUX_USERNAME
WorkingDirectory=/PATH/TO/YOUR/world-journal
Environment="TZ=Europe/Bucharest"
ExecStart=/PATH/TO/YOUR/world-journal/.venv/bin/python -m waitress --listen=0.0.0.0:8000 --threads=8 config.wsgi:application
Restart=always

[Install]
WantedBy=multi-user.target
```

Activate it:

```sh
sudo systemctl daemon-reload
sudo systemctl start worldjournal
sudo systemctl enable worldjournal
```

Use `sudo systemctl status worldjournal` to inspect its state.

## Updating

Stop the server, open a terminal in the project folder and run:

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
