# Authentication

By default World Journal does not require a login. This is convenient for local use on one computer or a trusted home network.

If you expose the app to the internet, enable the whole-app login gate. It protects every app page and uploaded journal image. There is no registration page. You create the administrator account yourself in the terminal.

The data is still shared. Authentication controls who can enter the app, but it does not create separate journals for different accounts.

## Step 1: Create an Account

=== "Docker"

	```sh
	docker exec -it world-journal python manage.py createsuperuser
	```

=== "Windows"

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

Start the app with `REQUIRE_LOGIN=True`.

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

	**PowerShell:**

	```powershell
	$env:REQUIRE_LOGIN="True"
	.\.venv\Scripts\python.exe manage.py runserver 0.0.0.0:8000 --noreload
	```

	**Command Prompt or a `.bat` file:**

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
