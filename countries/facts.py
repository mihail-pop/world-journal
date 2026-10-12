"""Country facts are served from a bundled Wikidata snapshot, never a live API."""
import json
from decimal import Decimal
from functools import lru_cache

from django.conf import settings
from django.utils.dateparse import parse_datetime
from .models import TerritoryDetails


@lru_cache(maxsize=1)
def _bundled_catalog():
    metadata = json.loads((settings.BASE_DIR / "data/countries.json").read_text(encoding="utf-8"))
    return {row["iso_a2"]: row for row in metadata["countries"]}, metadata["source"]


def bundled_catalog():
    catalog, source = _bundled_catalog()
    names = dict(TerritoryDetails.objects.values_list("country_id", "name"))
    return {code: {**row, "name": names.get(code, row["name"])} for code, row in catalog.items()}, source


@lru_cache(maxsize=2)
def _snapshot(path, modified, size):
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or not isinstance(data.get("countries"), dict):
        raise ValueError("Unsupported country facts snapshot")
    return data


def local_snapshot():
    path = settings.COUNTRY_FACTS_PATH
    stat = path.stat()
    snapshot = _snapshot(path, stat.st_mtime_ns, stat.st_size)
    records = dict(snapshot["countries"])
    territory_path = settings.BASE_DIR / "data" / "territory_facts.json"
    if territory_path.exists():
        territory_stat = territory_path.stat()
        records.update(_snapshot(territory_path, territory_stat.st_mtime_ns, territory_stat.st_size)["countries"])
    for details in TerritoryDetails.objects.all():
        record = dict(records.get(details.country_id, {}))
        for field in ("population", "area"):
            value = getattr(details, field)
            if value is not None:
                record[field] = [{"amount": str(value), "local": True}]
        for field, target in (("capital", "capitals"), ("languages", "languages"), ("currency", "currencies"), ("government", "government")):
            value = getattr(details, field)
            if value:
                record[target] = [{"name": name.strip()} for name in value.split(",") if name.strip()]
        record["notes"] = details.notes
        records[details.country_id] = record
    return {**snapshot, "countries": records}


def quantity_values(record, field):
    values = []
    for item in record.get(field, []):
        number = Decimal(item["amount"])
        display = f"{number:,.0f}" if field == "population" else f"{number:,.2f}".rstrip("0").rstrip(".")
        values.append({**item, "display": display})
    return values


def demographic_groups(record, field):
    groups = {}
    for item in record.get(field, []):
        key = (item.get("scope", ""), item.get("date"))
        group = groups.setdefault(key, {"year": item.get("year"), "scope_name": item.get("scope_name", ""), "items": [], "category_counts": {}})
        percentage = Decimal(item["proportion"]) * 100
        display = format(percentage, "f")
        if "." in display:
            display = display.rstrip("0").rstrip(".")
        group["items"].append({**item, "percentage": display})
        group["category_counts"][item["id"]] = group["category_counts"].get(item["id"], 0) + 1
    for group in groups.values():
        group["conflicting"] = any(count > 1 for count in group.pop("category_counts").values())
    return list(groups.values())


def bundled_facts(code):
    countries, identity_source = bundled_catalog()
    snapshot = local_snapshot()
    record = snapshot["countries"].get(code, {})
    source = snapshot["source"]
    verified = record.get("identity_verified", False)
    return {
        "country": countries[code], "identity_source": identity_source,
        "source": source, "retrieved_at": parse_datetime(source["retrieved_at"]),
        "identity_verified": verified,
        "scope_note": record.get("scope_note", ""),
        "source_url": f"https://www.wikidata.org/wiki/{record['qid']}" if verified else "",
        "wikipedia_url": record.get("wikipedia_url", "") if verified else "",
        "population": quantity_values(record, "population"), "area": quantity_values(record, "area"),
        "capitals": record.get("capitals", []), "currencies": record.get("currencies", []), "languages": record.get("languages", []),
        "government": record.get("government", []),
        "ethnic_groups": demographic_groups(record, "ethnic_groups"),
        "religions": demographic_groups(record, "religions"),
        "notes": record.get("notes", ""),
    }
