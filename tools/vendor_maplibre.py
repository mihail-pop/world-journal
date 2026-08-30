"""Vendor the pinned MapLibre GL JS no-bundler distribution."""

from __future__ import annotations

import hashlib
import io
import tarfile
import urllib.request
from pathlib import Path


VERSION = "6.6.0"
TARBALL_URL = f"https://registry.npmjs.org/maplibre-gl/-/maplibre-gl-{VERSION}.tgz"
EXPECTED_TARBALL_SHA256 = "d329c597381ab52589260d89914c80fb53ef32ba07647e9f2c71f58fdf7b606e"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DESTINATION = PROJECT_ROOT / "static" / "vendor" / "maplibre-gl"
FILES = {
    "package/dist/maplibre-gl.mjs": "maplibre-gl.mjs",
    "package/dist/maplibre-gl-shared.mjs": "maplibre-gl-shared.mjs",
    "package/dist/maplibre-gl-worker.mjs": "maplibre-gl-worker.mjs",
    "package/dist/maplibre-gl.css": "maplibre-gl.css",
    "package/LICENSE.txt": "LICENSE.txt",
}


def main() -> None:
    request = urllib.request.Request(
        TARBALL_URL, headers={"User-Agent": "world-journal-maplibre-vendor/1.0"}
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        tarball = response.read()
    digest = hashlib.sha256(tarball).hexdigest()
    if digest != EXPECTED_TARBALL_SHA256:
        raise ValueError(f"MapLibre tarball hash mismatch: {digest}")

    DESTINATION.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(tarball), mode="r:gz") as archive:
        for source_name, destination_name in FILES.items():
            source = archive.extractfile(source_name)
            if source is None:
                raise ValueError(f"MapLibre package is missing {source_name}")
            destination = DESTINATION / destination_name
            destination.write_bytes(source.read())
            print(f"Wrote {destination.relative_to(PROJECT_ROOT)} ({destination.stat().st_size:,} bytes)")
    (DESTINATION / "VERSION.txt").write_text(f"{VERSION}\n", encoding="ascii")
    print(f"Wrote {(DESTINATION / 'VERSION.txt').relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()