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

7. Start World Journal:

    ```sh
    .venv/bin/python manage.py runserver 127.0.0.1:8000
    ```

8. Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser.

The Terminal window must remain open while the app is running. Press `Control+C` in that window when you want to stop it.

## Updating

Stop the server, open Terminal in the project folder and run:

```sh
git pull
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py createcachetable world_journal_cache
```

Start the server again and perform a hard refresh in the browser so updated static files are loaded.

> **Note:** Export a backup from **Settings > Backup** before a major update. The app keeps personal data in `db.sqlite3` and uploaded journal images in `media/`.
