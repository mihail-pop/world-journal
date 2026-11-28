# Authentication

By default World Journal does not require a login. This is convenient for local use on one computer or a trusted home network.

If you expose the app to the internet, enable the login gate. It protects app pages, CSS, JavaScript, map files and uploaded journal images. The login page includes its own styling and icon. Create the administrator account in the terminal.

The data is still shared. Authentication controls who can enter the app, but it does not create separate journals for different accounts.

## Step 1: Create an Account

=== "Docker"

	```sh
	docker exec -it world-journal python manage.py createsuperuser
	```

=== "Windows"

	**Windows installer**

	Open PowerShell in your installation folder, usually `%USERPROFILE%\WorldJournal`, and run:

	```powershell
	$journalRoot = (Get-Location).Path
	$journalState = Get-Content -LiteralPath .\install-state.json -Raw | ConvertFrom-Json
	$journalRelease = Join-Path $journalRoot ("releases\" + $journalState.active_release)
	$env:DJANGO_SETTINGS_MODULE = "installed_settings"
	$env:WORLD_JOURNAL_INSTALL_ROOT = $journalRoot
	$env:WORLD_JOURNAL_STATIC_ROOT = Join-Path $journalRelease "staticfiles"
	$env:PYTHONPATH = "$journalRoot\support;$journalRelease\application"
	& "$journalRelease\env\Scripts\python.exe" "$journalRelease\application\manage.py" createsuperuser
	```

	You can close this PowerShell window when you finish.

	**Manual install**

	```powershell
	.\.venv\Scripts\python.exe manage.py createsuperuser
	```

=== "Mac"

	```sh
	.venv/bin/python manage.py createsuperuser
	```

=== "Linux"

	```sh
	.venv/bin/python manage.py createsuperuser
	```

Django asks for a username, optional email and password. Nothing appears while the password is being typed.

## Step 2: Enable the Login Screen

Enable the login gate for your installation.

=== "Docker"

	Uncomment the variable in `docker-compose.yml`:

	```yaml
	environment:
	  - REQUIRE_LOGIN=True
	```

	Restart the container:

	```sh
	docker compose up -d
	```

=== "Windows"

	**Windows installer**

	Open `config.json` in your installation folder and set `require_login` to `true`. Use **Stop World Journal** in the Start menu, then open **World Journal** again.

	**Manual install in PowerShell**

	```powershell
	$env:REQUIRE_LOGIN="True"
	.\.venv\Scripts\python.exe manage.py runserver 0.0.0.0:8000 --noreload
	```

	**Manual install in Command Prompt or a `.bat` file**

	```bat
	set REQUIRE_LOGIN=True
	.venv\Scripts\python.exe manage.py runserver 0.0.0.0:8000 --noreload
	```

=== "Mac"

	```sh
	export REQUIRE_LOGIN=True
	.venv/bin/python manage.py runserver 0.0.0.0:8000 --noreload
	```

	For a LaunchAgent, add it to `EnvironmentVariables`:

	```xml
	<key>REQUIRE_LOGIN</key>
	<string>True</string>
	```

=== "Linux"

	```sh
	export REQUIRE_LOGIN=True
	.venv/bin/python manage.py runserver 0.0.0.0:8000 --noreload
	```

	For systemd, add it under `[Service]`:

	```ini
	Environment="REQUIRE_LOGIN=True"
	```

When the setting is enabled, unauthenticated requests are redirected to `/login/`. Log out from the persistent header. When the setting is disabled, the login route returns to the Map and the app works without an account.
