"""Display flags independently of the catalogue's stable territory identities."""
import json
from functools import lru_cache

from django.conf import settings
from django.templatetags.static import static

# Bundled public-domain SVG originals:
# https://commons.wikimedia.org/wiki/File:Flag_of_Somaliland.svg
# https://commons.wikimedia.org/wiki/File:Flag_of_the_Turkish_Republic_of_Northern_Cyprus.svg


@lru_cache(maxsize=1)
def _territories():
    definitions = json.loads((settings.BASE_DIR / "data/custom_territories.json").read_text(encoding="utf-8"))
    return {row["code"]: row for row in definitions["territories"]}


def flag_details(country):
    custom = country.get("is_custom", False)
    definition = _territories().get(country["iso_a2"], {}) if custom else {}
    code = definition.get("flag_code") if custom else country["iso_a2"]
    asset = definition.get("flag_asset")
    url = ""
    if asset:
        url = static(f"vendor/flags/{asset}")
    elif code:
        url = f"https://flagcdn.com/{code.lower()}.svg"
    emoji = "".join(chr(0x1F1E6 + ord(letter) - ord("A")) for letter in code) if code else ""
    return {
        "flag": emoji,
        "flag_url": url,
        "flag_label": definition.get("flag_label", f"{country['name']} flag" if url else ""),
    }
