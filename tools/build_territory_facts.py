"""Refresh reviewed non-ISO state facts without changing the ISO snapshot."""
import json
from datetime import UTC, datetime
from pathlib import Path

from build_country_facts import normalize, query_batch

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "data/territory_facts.json"


def main():
    definitions = json.loads((ROOT / "data/custom_territories.json").read_text(encoding="utf-8"))["territories"]
    mapping = {row["code"]: {"iso3": "", "qid": row["qid"], "scope_note": "Figures refer to the named territory entity; map boundaries follow the bundled Natural Earth snapshot."} for row in definitions if row.get("facts_enabled")}
    rows = query_batch(list(mapping.items()), verify_iso=False)
    now = datetime.now(UTC)
    records = normalize(rows, mapping, now)
    if not all(record["identity_verified"] for record in records.values()):
        raise ValueError("A reviewed Wikidata territory identity did not return; existing facts were not replaced")
    for record in records.values():
        record["identity_method"] = "reviewed_non_iso_entity"
    data = {"schema_version": 1, "source": {"name": "Wikidata", "license": "CC0", "retrieved_at": now.isoformat(), "identity_mapping_source": "Reviewed Kosovo, Northern Cyprus and Somaliland QIDs; no claim of ISO membership"}, "countries": records}
    temporary = OUTPUT.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(OUTPUT)
    print("Saved reviewed facts for", ", ".join(mapping), flush=True)


if __name__ == "__main__":
    main()
