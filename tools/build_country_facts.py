"""Build a real Wikidata snapshot; browsing the app never calls a facts API."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from build_country_data import EXPECTED_SOURCE_SHA256, SOURCE_BASE_URL, SOURCE_TAG, choose_metadata_record, is_iso_backed, parse_dbf

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "data/country_facts.json"
USER_AGENT = "WorldJournalCountrySnapshot/1.0 (local self-hosted app; https://www.wikidata.org/wiki/Wikidata:Data_access)"
QID = re.compile(r"Q[1-9][0-9]*\Z")
AREA_UNITS = {"Q712226": Decimal(1), "Q25343": Decimal("0.000001"), "Q35852": Decimal("0.01"), "Q232291": Decimal("2.589988110336")}
PROPERTIES = {"P1082": "population", "P2046": "area", "P36": "capitals", "P38": "currencies", "P37": "languages", "P122": "government", "P172": "ethnic_groups", "P140": "religions"}
DEMOGRAPHIC_PROPERTIES = {"P172", "P140"}
# Reviewed against both current ISO properties, rather than polygon-level entities.
IDENTITY_OVERRIDES = {
    "NL": {"qid": "Q29999", "scope_note": "Figures refer to the Kingdom of the Netherlands, which includes its Caribbean constituent countries."},
    "PS": {"qid": "Q219060", "scope_note": ""},
    "SH": {"qid": "Q192184", "scope_note": "Figures cover Saint Helena, Ascension and Tristan da Cunha together."},
}


def download(url, *, accept="application/json", max_bytes=8 * 1024 * 1024):
    for attempt in range(3):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                body = response.read(max_bytes + 1)
                if len(body) > max_bytes:
                    raise ValueError("Source response exceeded its bounded size")
                return body
        except (urllib.error.URLError, TimeoutError) as error:
            if attempt == 2:
                raise RuntimeError("Source download failed; the existing snapshot was not replaced") from error
            wait = 2 ** (attempt + 1)
            if isinstance(error, urllib.error.HTTPError) and error.code == 429:
                try:
                    wait = min(30, max(wait, int(error.headers.get("Retry-After", wait))))
                except ValueError:
                    pass
            time.sleep(wait)
    raise RuntimeError("Source download failed")


def country_mapping():
    metadata = json.loads((ROOT / "data/countries.json").read_text(encoding="utf-8"))
    body = download(SOURCE_BASE_URL + ".dbf", accept="application/octet-stream")
    if hashlib.sha256(body).hexdigest() != EXPECTED_SOURCE_SHA256[".dbf"]:
        raise ValueError("Pinned Natural Earth identity source hash mismatch")
    grouped = defaultdict(list)
    for row in parse_dbf(body):
        if is_iso_backed(row):
            grouped[row["ISO_A2_EH"]].append(row)
    result = {}
    for country in metadata["countries"]:
        row = choose_metadata_record(grouped[country["iso_a2"]])
        qid = row.get("WIKIDATAID", "")
        result[country["iso_a2"]] = {"iso3": country["iso_a3"], "qid": qid if QID.fullmatch(qid) else None}
        result[country["iso_a2"]].update(IDENTITY_OVERRIDES.get(country["iso_a2"], {}))
    return result


def query_batch(batch):
    values = " ".join(f'(wd:{item["qid"]} "{code}" "{item["iso3"]}")' for code, item in batch)
    query = """SELECT ?item ?iso ?iso3 ?kind ?property ?statement ?rank ?amount ?unit ?date ?start ?end ?related ?label ?part ?partLabel ?share ?shareUnit ?reference ?article WHERE {
      VALUES (?item ?iso ?iso3) { VALUES_HERE }
      ?item wdt:P297 ?iso; wdt:P298 ?iso3.
      OPTIONAL { ?article schema:about ?item; schema:isPartOf <https://en.wikipedia.org/>. }
      { BIND("identity" AS ?kind) }
      UNION {
        VALUES ?property { wd:P1082 wd:P2046 }
        ?property wikibase:claim ?claim; wikibase:statementValue ?valueProperty.
        ?item ?claim ?statement.
        ?statement wikibase:rank ?rank; ?valueProperty ?node.
        ?node wikibase:quantityAmount ?amount; wikibase:quantityUnit ?unit.
        FILTER(?rank != wikibase:DeprecatedRank)
        FILTER NOT EXISTS {
          ?statement pq:P518 ?quantityPart.
          FILTER(?property != wd:P2046 || (
            ?quantityPart != wd:Q16868672 && (
              ?quantityPart NOT IN (wd:Q11081619, wd:Q165) ||
              NOT EXISTS { ?statement pq:P518 wd:Q11081619; pq:P518 wd:Q165. }
            )
          ))
        }
        OPTIONAL { ?statement pq:P585 ?date. }
        OPTIONAL { ?statement pq:P580 ?start. }
        OPTIONAL { ?statement pq:P582 ?end. }
        BIND("quantity" AS ?kind)
      }
      UNION {
        VALUES ?property { wd:P36 wd:P38 wd:P37 wd:P122 wd:P172 wd:P140 }
        ?property wikibase:claim ?claim; wikibase:statementProperty ?valueProperty.
        ?item ?claim ?statement.
        ?statement wikibase:rank ?rank; ?valueProperty ?related.
        FILTER(?rank != wikibase:DeprecatedRank)
        OPTIONAL { ?statement pq:P585 ?date. }
        OPTIONAL { ?statement pq:P580 ?start. }
        OPTIONAL { ?statement pq:P582 ?end. }
        OPTIONAL {
          ?statement pq:P518 ?part.
          OPTIONAL { ?part rdfs:label ?partEnglishLabel. FILTER(LANG(?partEnglishLabel) = "en") }
          OPTIONAL { ?part rdfs:label ?partSharedLabel. FILTER(LANG(?partSharedLabel) = "mul") }
          BIND(COALESCE(?partEnglishLabel, ?partSharedLabel) AS ?partLabel)
        }
        OPTIONAL { ?related rdfs:label ?englishLabel. FILTER(LANG(?englishLabel) = "en") }
        OPTIONAL { ?related rdfs:label ?sharedLabel. FILTER(LANG(?sharedLabel) = "mul") }
        BIND(COALESCE(?englishLabel, ?sharedLabel) AS ?label)
        OPTIONAL {
          FILTER(?property IN (wd:P172, wd:P140))
          ?statement pqv:P1107 ?shareNode.
          ?shareNode wikibase:quantityAmount ?share; wikibase:quantityUnit ?shareUnit.
        }
        OPTIONAL {
          FILTER(?property IN (wd:P172, wd:P140))
          ?statement prov:wasDerivedFrom ?reference.
        }
        BIND("entity" AS ?kind)
      }
    }""".replace("VALUES_HERE", values)
    url = "https://query.wikidata.org/sparql?" + urllib.parse.urlencode({"query": query, "format": "json"})
    payload = json.loads(download(url, accept="application/sparql-results+json"))
    rows = payload.get("results", {}).get("bindings")
    if not isinstance(rows, list):
        raise ValueError("Wikidata did not return the expected query response")
    return rows


def text(row, key):
    return row.get(key, {}).get("value", "")


def date_key(value):
    match = re.match(r"[+]?([0-9]{4})-([0-9]{2})-([0-9]{2})", value)
    return tuple(int(part) for part in match.groups()) if match else None


def active(row, today):
    start, end = date_key(text(row, "start")), date_key(text(row, "end"))
    return not ((start and start > today) or (end and end <= today))


def select_demographics(candidates):
    """Keep one observation date per scope, without hiding minority categories."""
    latest = {}
    for candidate in candidates:
        scope = candidate["scope"]
        latest[scope] = max(latest.get(scope, (0, 0, 0)), date_key(candidate["date"] or "") or (0, 0, 0))
    cohort = [candidate for candidate in candidates if (date_key(candidate["date"] or "") or (0, 0, 0)) == latest[candidate["scope"]]]
    ranks = {}
    for candidate in cohort:
        key = (candidate["scope"], candidate["id"])
        ranks[key] = max(ranks.get(key, 0), candidate["rank"])
    unique = {}
    for candidate in cohort:
        if candidate["rank"] != ranks[(candidate["scope"], candidate["id"])]:
            continue
        key = (candidate["id"], candidate["scope"], candidate["date"], candidate["proportion"])
        if key not in unique:
            unique[key] = {**candidate, "references": set(), "statements": set()}
        unique[key]["references"].add(candidate["reference"])
        unique[key]["statements"].add(candidate["statement"])
    values = []
    for candidate in unique.values():
        candidate.pop("reference")
        candidate.pop("statement")
        candidate["references"] = sorted(candidate["references"])
        candidate["statements"] = sorted(candidate["statements"])
        values.append(candidate)
    return sorted(values, key=lambda candidate: (candidate["scope"], -Decimal(candidate["proportion"]), candidate["name"]))


def normalize(rows, mapping, now):
    records = {code: {"qid": item["qid"], "scope_note": item.get("scope_note", ""), "identity_verified": False, "wikipedia_url": "", **{field: [] for field in PROPERTIES.values()}} for code, item in mapping.items()}
    collected = defaultdict(lambda: defaultdict(list))
    today = (now.year, now.month, now.day)
    for row in rows:
        code = text(row, "iso")
        if code not in mapping:
            raise ValueError("Unexpected country in source response")
        item = mapping[code]
        if text(row, "item").rsplit("/", 1)[-1] != item["qid"] or text(row, "iso3") != item["iso3"]:
            raise ValueError("Source country identity mismatch")
        records[code]["identity_verified"] = True
        article = text(row, "article")
        if article.startswith("https://en.wikipedia.org/wiki/"):
            records[code]["wikipedia_url"] = article
        prop = text(row, "property").rsplit("/", 1)[-1]
        if prop not in PROPERTIES or not active(row, today):
            continue
        date = date_key(text(row, "date"))
        if date and date > today:
            continue
        rank = 1 if text(row, "rank").endswith("PreferredRank") else 0
        statement = text(row, "statement").rsplit("/", 1)[-1]
        source = f'https://www.wikidata.org/wiki/{item["qid"]}#{prop}'
        if prop in {"P1082", "P2046"}:
            try:
                number = Decimal(text(row, "amount"))
                if not number.is_finite() or not 0 <= number <= Decimal("1e15"):
                    continue
                if prop == "P2046":
                    factor = AREA_UNITS.get(text(row, "unit").rsplit("/", 1)[-1])
                    if factor is None:
                        continue
                    number *= factor
                elif number != number.to_integral_value() or text(row, "unit").rsplit("/", 1)[-1] not in {"1", "Q199"}:
                    continue
            except InvalidOperation:
                continue
            collected[code][prop].append({"amount": format(number, "f"), "year": date[0] if date else None, "date": text(row, "date") or None, "rank": rank, "statement": statement, "source_url": source})
        elif prop in DEMOGRAPHIC_PROPERTIES:
            related = text(row, "related").rsplit("/", 1)[-1]
            label, reference = text(row, "label"), text(row, "reference")
            if not QID.fullmatch(related) or not label or not reference:
                continue
            try:
                proportion = Decimal(text(row, "share"))
                # RDF represents a unitless quantity with the entity for 1 (Q199).
                if not proportion.is_finite() or not 0 <= proportion <= 1 or text(row, "shareUnit").rsplit("/", 1)[-1] not in {"1", "Q199"}:
                    continue
            except InvalidOperation:
                continue
            scope = text(row, "part").rsplit("/", 1)[-1]
            if scope and not QID.fullmatch(scope):
                continue
            collected[code][prop].append({"id": related, "name": label, "rank": rank, "scope": scope, "scope_name": text(row, "partLabel") or scope, "proportion": format(proportion, "f"), "date": text(row, "date") or None, "year": date[0] if date else None, "source_url": source, "topic_url": f"https://www.wikidata.org/wiki/{related}", "reference": reference, "statement": statement})
        else:
            related = text(row, "related").rsplit("/", 1)[-1]
            label = text(row, "label")
            if QID.fullmatch(related) and label:
                candidate = {"id": related, "name": label, "rank": rank, "scope": text(row, "part").rsplit("/", 1)[-1], "source_url": f"https://www.wikidata.org/wiki/{related}"}
                if prop == "P122":
                    start = date_key(text(row, "start"))
                    candidate.update({"date": text(row, "date") or None, "year": date[0] if date else None, "start_year": start[0] if start else None, "statement": statement, "statement_source_url": source})
                collected[code][prop].append(candidate)
    for code, properties in collected.items():
        for prop, candidates in properties.items():
            if prop in DEMOGRAPHIC_PROPERTIES:
                records[code][PROPERTIES[prop]] = select_demographics(candidates)
                continue
            if prop in {"P1082", "P2046"}:
                preferred = max(candidate["rank"] for candidate in candidates)
                chosen = [candidate for candidate in candidates if candidate["rank"] == preferred]
                latest = max(date_key(candidate["date"] or "") or (0, 0, 0) for candidate in chosen)
                chosen = [candidate for candidate in chosen if (date_key(candidate["date"] or "") or (0, 0, 0)) == latest]
                unique = {}
                for candidate in sorted(chosen, key=lambda candidate: candidate["statement"]):
                    unique.setdefault(candidate["amount"], candidate)
            else:
                # Preferred statements for one constituent territory must not hide
                # current values for another constituent territory.
                ranks = {}
                for candidate in candidates:
                    ranks[candidate["scope"]] = max(ranks.get(candidate["scope"], 0), candidate["rank"])
                chosen = [candidate for candidate in candidates if candidate["rank"] == ranks[candidate["scope"]]]
                unique = {candidate["id"]: candidate for candidate in chosen}
            records[code][PROPERTIES[prop]] = sorted(unique.values(), key=lambda candidate: candidate.get("name", candidate.get("amount", "")))
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-agent", help="Optional descriptive agent with your real contact URL/email for Wikimedia")
    args = parser.parse_args()
    if args.user_agent:
        global USER_AGENT
        USER_AGENT = args.user_agent
    mapping = country_mapping()
    valid = [(code, item) for code, item in mapping.items() if item["qid"]]
    rows = []
    for offset in range(0, len(valid), 20):
        batch = valid[offset:offset + 20]
        rows.extend(query_batch(batch))
        print(f"Acquired Wikidata facts for batch {offset // 20 + 1}/{(len(valid) + 19) // 20}", flush=True)
        time.sleep(0.5)
    now = datetime.now(UTC)
    records = normalize(rows, mapping, now)
    if not all(record["identity_verified"] for record in records.values()):
        missing = ", ".join(code for code, record in records.items() if not record["identity_verified"])
        raise ValueError(f"ISO identity matches missing ({missing}); the existing snapshot was not replaced")
    previous = json.loads(OUTPUT.read_text(encoding="utf-8"))["countries"] if OUTPUT.exists() else {}
    for field in PROPERTIES.values():
        count = sum(bool(record[field]) for record in records.values())
        previous_count = sum(bool(record.get(field)) for record in previous.values())
        if previous_count and count < previous_count * 0.9:
            raise ValueError(f"Unexpected loss of {field} coverage; the existing snapshot was not replaced")
    source = {"name": "Wikidata", "url": "https://www.wikidata.org/", "license": "CC0", "retrieved_at": now.isoformat(), "identity_mapping_source": f"Natural Earth {SOURCE_TAG} WIKIDATAID with reviewed NL/PS/SH overrides, verified against P297/P298", "identity_mapping_dbf_sha256": EXPECTED_SOURCE_SHA256[".dbf"], "identity_overrides": IDENTITY_OVERRIDES, "query_policy": "Nondeprecated active statements; preferred rank (per territorial scope for entity values), then latest nonfuture date for quantities. Whole-country quantities only, including explicit total-area or combined land/water area. Equal-ranked conflicting quantities are retained.", "demographic_policy": "Referenced P172/P140 statements with explicit unitless P1107 shares in [0,1] only; latest nonfuture observation per territorial scope, then rank per category. Missing categories/shares are never inferred; totals are not normalized. P3075 official religion is not a population breakdown."}
    output = {"schema_version": 1, "source": source, "countries": records}
    temporary = OUTPUT.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(OUTPUT)
    print("Snapshot saved:", OUTPUT, flush=True)
    for field in ("identity_verified", *PROPERTIES.values()):
        print(field, sum(bool(record[field]) for record in records.values()), "/", len(records), flush=True)


if __name__ == "__main__":
    main()
