# Remote Access

To access World Journal away from home, you have two main options.

## Option 1: Private Access with Tailscale

[Tailscale](https://tailscale.com/) creates an encrypted private connection between your devices. Install it on the machine running World Journal and on each device that needs access.

- **Pros:** Private, simple and does not require opening a public port.
- **Cons:** Tailscale must be installed on every device.

Authentication is still recommended if more than one person or device can reach the server.

## Option 2: Public Access with a Tunnel

A service such as [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/get-started/create-local-tunnel/) can expose the app through an HTTPS domain without forwarding a router port.

Before doing this:

1. enable [Authentication](authentication.md);
2. set a unique `SECRET_KEY`;
3. configure `CSRF_TRUSTED_ORIGINS` with the public HTTPS address;
4. use Waitress rather than Django's development server.

## Configuring a Domain

`CSRF_TRUSTED_ORIGINS` accepts one or more comma-separated origins. Include the `https://` prefix.

=== "Docker"

	```yaml
	environment:
	  - REQUIRE_LOGIN=True
	  - SECRET_KEY=replace-this-with-a-long-random-value
	  - CSRF_TRUSTED_ORIGINS=https://your-domain.com
	```

	```sh
	docker compose up -d
	```

=== "Windows"

	**PowerShell:**

	```powershell
	$env:REQUIRE_LOGIN="True"
	$env:SECRET_KEY="replace-this-with-a-long-random-value"
	$env:CSRF_TRUSTED_ORIGINS="https://your-domain.com"
	.\.venv\Scripts\python.exe -m waitress --listen=0.0.0.0:8000 --threads=8 config.wsgi:application
	```

	**Command Prompt or a `.bat` file:**

	```bat
	set REQUIRE_LOGIN=True
	set SECRET_KEY=replace-this-with-a-long-random-value
	set CSRF_TRUSTED_ORIGINS=https://your-domain.com
	.venv\Scripts\python.exe -m waitress --listen=0.0.0.0:8000 --threads=8 config.wsgi:application
	```

=== "Mac"

	```sh
	export REQUIRE_LOGIN=True
	export SECRET_KEY=replace-this-with-a-long-random-value
	export CSRF_TRUSTED_ORIGINS=https://your-domain.com
	.venv/bin/python -m waitress --listen=0.0.0.0:8000 --threads=8 config.wsgi:application
	```

=== "Linux"

	Add the variables to the systemd service:

	```ini
	Environment="REQUIRE_LOGIN=True"
	Environment="SECRET_KEY=replace-this-with-a-long-random-value"
	Environment="CSRF_TRUSTED_ORIGINS=https://your-domain.com"
	```

	Then restart it:

	```sh
	sudo systemctl daemon-reload
	sudo systemctl restart worldjournal
	```

World Journal does not provide HTTPS itself. The tunnel or reverse proxy must terminate HTTPS before forwarding requests to Waitress.
