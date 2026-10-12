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

6. Start World Journal:

    ```sh
    .venv/bin/python manage.py runserver 127.0.0.1:8000
    ```

7. Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser.

The terminal must remain open while the app is running. Press `Ctrl+C` when you want to stop it.

## Updating

Stop the server, open a terminal in the project folder and run:

```sh
git pull
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py createcachetable world_journal_cache
```

Start the server again and perform a hard refresh in the browser so updated static files are loaded.

> **Note:** Export a backup from **Settings > Backup** before a major update. The app keeps personal data in `db.sqlite3` and uploaded journal images in `media/`.
