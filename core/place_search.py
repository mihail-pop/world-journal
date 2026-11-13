"""Local place search; no geocoding requests or user-data writes."""
import json
import re
import unicodedata
from functools import lru_cache
from urllib.parse import urlencode

from django.conf import settings
from django.urls import reverse

from countries.facts import bundled_catalog


COUNTRY_ALIASES = {
    "GB": ("UK", "Britain", "Great Britain"),
    "US": ("USA", "United States of America", "America"),
    "KR": ("South Korea", "Republic of Korea"), "KP": ("North Korea",),
    "CD": ("DR Congo", "DRC", "Democratic Republic of the Congo"),
    "CG": ("Republic of the Congo", "Congo Brazzaville"),
    "CI": ("Ivory Coast",), "CZ": ("Czech Republic",),
    "SZ": ("Swaziland",), "MM": ("Burma",), "CV": ("Cape Verde",),
    "TL": ("East Timor",), "TR": ("Turkey", "Türkiye"),
}


def normalize(value):
    value = unicodedata.normalize("NFKD", value.casefold())
    value = "".join(char for char in value if not unicodedata.combining(char))
    return " ".join(re.findall(r"[^\W_]+", value, flags=re.UNICODE))


@lru_cache(maxsize=1)
def _places():
    data = json.loads((settings.BASE_DIR / "data/place_search.json").read_text(encoding="utf-8"))
    if data["schema_version"] != 1:
        raise ValueError("Unsupported place-search index")
    places = {}
    for place in data["places"]:
        names = tuple(dict.fromkeys(normalize(name) for name in [place["name"], *place["aliases"]]))
        places[place["id"]] = {**place, "names": names, "search_text": "\n".join(names)}
    return places


def map_search_target(place_id, country_code):
    place = _places().get(place_id) if place_id else None
    if not place or place["country"] != country_code.strip().upper():
        return {}
    return {key: place[key] for key in ("id", "name", "country", "coordinates")}


def _match(query, names, qualifiers=(), search_text=None):
    """Favor place names over country/region qualifiers and partial matches."""
    tokens = query.split()
    if search_text is not None and not any(token in search_text for token in tokens):
        return None
    if query in names:
        return 0
    if any(name.startswith(query) for name in names):
        return 1
    if any(all(any(word.startswith(token) for word in name.split()) for token in tokens) for name in names):
        return 2
    if any(query in name for name in names):
        return 3
    # A country alone should return its own result, not every city inside it.
    if any(any(word.startswith(token) for name in names for word in name.split()) for token in tokens):
        combined = " ".join((*names, *qualifiers)).split()
        if all(any(word.startswith(token) for word in combined) for token in tokens):
            return 4
    return None


def search_places(query, category="all", limit=24):
    query = normalize(query[:160])
    if not query:
        return []
    catalog, _ = bundled_catalog()
    country_names = {
        code: tuple(dict.fromkeys(normalize(name) for name in (
            country["name"], code, country["iso_a3"], *COUNTRY_ALIASES.get(code, ()),
        ) if name))
        for code, country in catalog.items()
    }
    matches = []
    map_url = reverse("core:map")
    if category in {"all", "countries"}:
        for code, country in catalog.items():
            score = _match(query, country_names[code])
            if score is not None:
                matches.append(((score, 0, 0, country["name"], code), {
                    "id": f"country-{code}", "name": country["name"], "label": country["name"],
                    "country": code, "kind": "country", "region": "", "flag": country["flag"],
                    "url": map_url + "?" + urlencode({"country": code}),
                }))
    if category in {"all", "capitals", "cities"}:
        for place in _places().values():
            if category == "capitals" and place["kind"] != "capital":
                continue
            # Capitals are also cities; All lists each place only once.
            code = place["country"]
            if code not in catalog:
                continue
            score = _match(query, place["names"], (*country_names[code], normalize(place["region"])), place["search_text"])
            if score is not None:
                country = catalog[code]
                matches.append(((score, 1 if place["kind"] == "capital" else 2, -place["population"], place["name"], place["id"]), {
                    "id": place["id"], "name": place["name"], "label": f"{place['name']}, {country['name']}",
                    "country": code, "kind": place["kind"], "region": place["region"], "flag": country["flag"],
                    "url": map_url + "?" + urlencode({"country": code, "place": place["id"]}),
                }))
    matches.sort(key=lambda match: match[0])
    return [result for _, result in matches[:limit]]
