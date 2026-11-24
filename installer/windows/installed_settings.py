"""Installer settings: persistent user data stays outside application releases."""
import json
import os
from pathlib import Path

_install_root = Path(os.environ["WORLD_JOURNAL_INSTALL_ROOT"]).resolve(strict=True)
with (_install_root / "config.json").open(encoding="utf-8-sig") as _config_file:
    _configuration = json.load(_config_file)

# Configure writable paths before the app's settings create the database folder.
# BASE_DIR must keep pointing at the release: maps, country data, templates and
# source definitions are bundled with the code and are read-only for the service.
os.environ["WORLD_JOURNAL_DATA_DIR"] = str(_install_root / "library" / "database")
if not os.environ.get("TZ", "").strip() and _configuration.get("timezone"):
    os.environ["TZ"] = _configuration["timezone"]

from config.settings import *  # noqa: E402,F403


DATABASE_ROOT = _install_root / "library" / "database"
DATABASES = {name: dict(database) for name, database in DATABASES.items()}  # noqa: F405
DATABASES["default"]["NAME"] = DATABASE_ROOT / "db.sqlite3"
MEDIA_ROOT = _install_root / "library" / "media"
BACKUP_STAGING_ROOT = DATABASE_ROOT / ".backup-imports"
STATIC_ROOT = Path(os.environ["WORLD_JOURNAL_STATIC_ROOT"])
SECRET_KEY = _configuration["secret_key"]
DEBUG = False
STORAGES = {**STORAGES, "staticfiles": {  # noqa: F405
    "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
}}

_origins = os.environ.get("CSRF_TRUSTED_ORIGINS", _configuration.get("csrf_trusted_origins", ""))
CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in _origins.split(",") if origin.strip()]
REQUIRE_LOGIN = str(os.environ.get("REQUIRE_LOGIN", _configuration.get("require_login", False))).lower() in (
    "true", "1", "t",
)
