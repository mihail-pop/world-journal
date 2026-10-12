# Troubleshooting

---

### The Page Has No Styling

**The Problem:**

The app loads through runserver or Waitress but CSS, JavaScript or map assets return errors.

**The Cause:**

Static files were not collected after installation or an update.

**The Solution:**

=== "Windows"

    ```powershell
    .\.venv\Scripts\python.exe manage.py collectstatic --noinput
    ```

=== "Mac and Linux"

    ```sh
    .venv/bin/python manage.py collectstatic --noinput
    ```

Restart the server and hard refresh the browser.

---

### Login Keeps Rejecting the Account

**The Problem:**

Authentication is enabled but the login page rejects the username or password.

**The Cause:**

The administrator account may not exist in the same SQLite database used by the running process. This is common when `createsuperuser` was run outside the container or with a different `WORLD_JOURNAL_DATA_DIR`.

**The Solution:**

For Docker, create the account inside the running container:

```sh
docker exec -it world-journal python manage.py createsuperuser
```

For a native install, use the project's `.venv` interpreter from the project folder. Confirm that the server and the command use the same environment variables.

---

### The Cache Table Does Not Exist

**The Problem:**

The app reports an error mentioning `world_journal_cache` when trying to read or refresh news.

**The Cause:**

The one-time database cache setup was skipped.

**The Solution:**

Stop the server and run:

=== "Windows"

    ```powershell
    .\.venv\Scripts\python.exe manage.py createcachetable world_journal_cache
    ```

=== "Mac and Linux"

    ```sh
    .venv/bin/python manage.py createcachetable world_journal_cache
    ```

Run the command again after replacing the database with a fresh empty one.

---

### Static Changes Do Not Appear

**The Problem:**

The server restarted but the map, styles or controls still look unchanged.

**The Cause:**

The browser is using cached CSS or JavaScript.

**The Solution:**

Restart Django and use a hard refresh. On Windows and Linux press `Ctrl+F5`. On Mac use `Command+Shift+R`.

---

### News Is Empty or Stale

**The Problem:**

A country has no recent articles or shows a refresh warning.

**The Cause:**

A publisher feed may be unavailable, rate limited or waiting for its next scheduled refresh. The scheduler only runs while Django is running.

**The Solution:**

Open **Settings > Sources** and inspect the source health. Use the manual refresh action once, then allow the background queue time to work. Repeatedly pressing refresh does not bypass provider limits.

Cached stories may remain visible after a failure. A failure from one source should not hide successful results from another source.

---

### The Map Is Blank or Incomplete

**The Problem:**

The map canvas is blank, or Terrain does not show provider detail.

**The Cause:**

Simple and Adventure use bundled country geometry, but Terrain and map labels can depend on external map resources. A stale browser cache can also keep an old module loaded.

**The Solution:**

Try Simple or Adventure first, then hard refresh. Check that the machine has internet access before using Terrain. If bundled map files are missing, update the repository rather than generating new geometry during ordinary setup.

---

### A YouTube Video Will Not Play

**The Problem:**

The player reports that the video is unavailable or embedding is disabled.

**The Cause:**

Publishers can disable embedded playback, remove a video or restrict it by region. World Journal cannot override those choices.

**The Solution:**

Use **Open on YouTube** in the player. Saving the video to the Journal still keeps its title, link and timestamp even when the embed cannot play.

---

### An Image Will Not Upload

**The Problem:**

A Journal image is rejected.

**The Cause:**

Images are checked by their real file content, size and dimensions. Renaming an unsupported file extension does not turn it into a valid image.

**The Solution:**

Use a valid JPEG, PNG, WebP or GIF no larger than 10 MiB. Re-export unusually large or damaged images before uploading them again.

---

### A Journal Draft Looks Unsaved

**The Problem:**

The editor status does not say Saved.

**The Cause:**

Autosave runs approximately once per minute and can fail because of validation or a lost connection.

**The Solution:**

Keep the editor open, correct any visible form errors and press Save. Do not refresh or close the tab until the status confirms the entry was saved.

---

### An Import Cannot Be Confirmed

**The Problem:**

A backup import stops during preview or reports an invalid archive.

**The Cause:**

World Journal validates the backup version, paths, manifest and attachment checksums before writing data.

**The Solution:**

Use the original ZIP created by World Journal. Do not extract and rebuild it with renamed files. Keep the existing database and media folder until a restore has completed successfully.
