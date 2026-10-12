# Setup for Docker

> **New to Docker?** If you have not used Docker before and plan to run the app on your personal computer, check the native Windows, Mac or Linux guides instead.

1. Clone the repository:

		```sh
		git clone https://github.com/mihail-pop/world-journal.git
		cd world-journal
		```

2. Open `docker-compose.yml` in a text editor. Uncomment and update the `TZ` variable with your timezone.

		```yaml
		environment:
			- TZ=Europe/Bucharest
		```

		Use an IANA timezone such as `Europe/London`, `Europe/Bucharest` or `America/New_York`. If it is omitted, World Journal uses UTC.

3. Build and start the app:

		```sh
		docker compose up -d --build
		```

4. Open [http://localhost:8091](http://localhost:8091).

World Journal uses port `8091` on the host so it can run next to Media Journal, which uses `8090`. The container still listens on port `8000` internally.

Personal data is stored in `runtime/` and uploaded images in `media/`. Both folders remain on the host when the container is replaced.

## Updating

From the project folder run:

```sh
git pull
docker compose up -d --build
```

The container applies migrations, creates the database cache table and collects static files before Waitress starts.

## Authentication

If you expose the app outside a trusted local network, enable authentication by uncommenting this line in `docker-compose.yml`:

```yaml
environment:
	- REQUIRE_LOGIN=True
```

Create the administrator account used to log in:

```sh
docker exec -it world-journal python manage.py createsuperuser
```

[Read the Authentication Guide](../configuration/authentication.md){ .md-button style="margin: 0 auto; display: block; width: fit-content;" }

## Remote Access

For a custom domain, also set a unique `SECRET_KEY` and add the HTTPS origin:

```yaml
environment:
	- SECRET_KEY=replace-this-with-a-long-random-value
	- CSRF_TRUSTED_ORIGINS=https://your-domain.com
```

[Read the Remote Access Guide](../configuration/remote-access.md){ .md-button style="margin: 0 auto; display: block; width: fit-content;" }
