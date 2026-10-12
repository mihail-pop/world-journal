# Setup for Windows

1. Download and install [Python 3.13](https://www.python.org/downloads/).

    During installation, enable **Add Python to PATH**.

2. Install [Git for Windows](https://git-scm.com/install/windows), then open PowerShell inside the folder where you want to keep the app.

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

7. Start World Journal:

    ```powershell
    .\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
    ```

8. Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser.

The terminal window must remain open while the app is running. Press `Ctrl+C` in that terminal when you want to stop it.

## Updating

Stop the server, open PowerShell in the project folder and run:

```powershell
git pull
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py createcachetable world_journal_cache
```

Start the server again and use `Ctrl+F5` in the browser so updated static files are loaded.

> **Note:** Export a backup from **Settings > Backup** before a major update. The app keeps personal data in `db.sqlite3` and uploaded journal images in `media/`.
