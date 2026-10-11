from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from django.conf import settings

from countries.data import load_capital_data, load_country_data


class AliasConfigurationError(ValueError):
    pass


class MatchClass(StrEnum):
    HEADLINE_COUNTRY = "headline_country"
    HEADLINE_RELATED = "headline_related"
    SUMMARY_COUNTRY = "summary_country"


@dataclass(frozen=True, slots=True)
class MatchEvidence:
    country_code: str
    alias: str
    match_class: MatchClass


@dataclass(frozen=True, slots=True)
class _Alias:
    country_code: str
    value: str
    normalized: str
    case_sensitive: bool
    related: bool = False
    summary_eligible: bool = True


def _normalize(value: str, *, casefold: bool) -> str:
    value = value.translate(str.maketrans({"’": "'", "‘": "'", "‛": "'", "–": "-", "—": "-"}))
    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(character for character in decomposed if not unicodedata.combining(character))
    normalized = " ".join(re.sub(r"[^\w]+", " ", without_marks, flags=re.UNICODE).split())
    return normalized.casefold() if casefold else normalized


def _load_alias_config(path: Path | None = None) -> dict:
    path = path or settings.NEWS_COUNTRY_ALIASES_PATH
    try:
        with path.open(encoding="utf-8") as alias_file:
            value = json.load(alias_file)
    except (OSError, json.JSONDecodeError) as error:
        raise AliasConfigurationError(f"Could not read valid country news aliases from {path}: {error}") from error
    if not isinstance(value, dict) or set(value) != {"schema_version", "ambiguous_canonical_codes", "countries"} or value["schema_version"] != 2:
        raise AliasConfigurationError("Country news aliases have an unsupported or missing schema")
    metadata, _geometry = load_country_data()
    country_codes = {country["iso_a2"] for country in metadata["countries"]}
    ambiguous = value["ambiguous_canonical_codes"]
    countries = value["countries"]
    if (
        not isinstance(ambiguous, list)
        or len(ambiguous) != len(set(ambiguous))
        or not all(code in country_codes for code in ambiguous)
        or not isinstance(countries, dict)
        or not set(countries).issubset(country_codes)
    ):
        raise AliasConfigurationError("Country news aliases contain unknown or duplicate country codes")
    for code, aliases in countries.items():
        if not isinstance(aliases, dict) or set(aliases) != {"name_aliases", "related_terms", "acronyms"}:
            raise AliasConfigurationError(f"Country {code} has invalid alias fields")
        for field in ("name_aliases", "related_terms", "acronyms"):
            values = aliases[field]
            if not isinstance(values, list) or not all(isinstance(alias, str) and alias.strip() for alias in values):
                raise AliasConfigurationError(f"Country {code} has invalid {field}")
    return value


@lru_cache(maxsize=1)
def _aliases() -> tuple[_Alias, ...]:
    config = _load_alias_config()
    metadata, _geometry = load_country_data()
    ambiguous = set(config["ambiguous_canonical_codes"])
    aliases: list[_Alias] = []
    seen: set[tuple[str, str, bool]] = set()
    for country in metadata["countries"]:
        code = country["iso_a2"]
        values = [] if code in ambiguous else [country["name"]]
        values.extend(config["countries"].get(code, {}).get("name_aliases", []))
        related_values = config["countries"].get(code, {}).get("related_terms", [])
        sensitive_values = config["countries"].get(code, {}).get("acronyms", [])
        for case_sensitive, related, candidates in (
            (False, False, values),
            (False, True, related_values),
            (True, False, sensitive_values),
        ):
            for value in candidates:
                normalized = _normalize(value, casefold=not case_sensitive)
                key = (code, normalized, case_sensitive)
                if normalized and key not in seen:
                    seen.add(key)
                    aliases.append(_Alias(code, value, normalized, case_sensitive, related))
    capital_data = load_capital_data(metadata)
    for feature in capital_data["features"]:
        code = feature["properties"]["iso_a2"]
        value = feature["properties"]["name"]
        normalized = _normalize(value, casefold=True)
        key = (code, normalized, False)
        if normalized and key not in seen:
            seen.add(key)
            aliases.append(_Alias(code, value, normalized, False, True, False))
    return tuple(sorted(
        aliases,
        key=lambda alias: (alias.related, -len(alias.normalized.split()), -len(alias.normalized), alias.country_code),
    ))


def _match(
    value: str,
    aliases: tuple[_Alias, ...],
    match_class: MatchClass,
    candidate_codes: set[str] | frozenset[str] | None,
) -> tuple[MatchEvidence, ...]:
    folded_value = _normalize(value, casefold=True)
    cased_value = _normalize(value, casefold=False)
    occupied: list[tuple[int, int]] = []
    evidence: list[MatchEvidence] = []
    matched_pairs: set[tuple[str, str]] = set()
    for alias in aliases:
        if candidate_codes is not None and alias.country_code not in candidate_codes:
            continue
        haystack = cased_value if alias.case_sensitive else folded_value
        needle = alias.normalized if alias.case_sensitive else alias.normalized.casefold()
        pattern = re.compile(rf"(?<!\w){re.escape(needle)}(?!\w)")
        for match in pattern.finditer(haystack):
            span = match.span()
            if any(span[0] < end and start < span[1] for start, end in occupied):
                continue
            pair = (alias.country_code, alias.value)
            if pair not in matched_pairs:
                matched_pairs.add(pair)
                evidence.append(MatchEvidence(alias.country_code, alias.value, match_class))
            occupied.append(span)
    return tuple(evidence)


@lru_cache(maxsize=8192)
def _cached_country_text(
    title: str,
    summary: str,
    alias_revision: int,
    candidate_codes: frozenset[str] | None,
) -> tuple[MatchEvidence, ...]:
    aliases = _aliases()
    name_aliases = tuple(alias for alias in aliases if not alias.related)
    related_aliases = tuple(alias for alias in aliases if alias.related)
    return (
        *_match(title, name_aliases, MatchClass.HEADLINE_COUNTRY, candidate_codes),
        *_match(title, related_aliases, MatchClass.HEADLINE_RELATED, candidate_codes),
        *_match(
            summary,
            tuple(alias for alias in aliases if alias.summary_eligible),
            MatchClass.SUMMARY_COUNTRY,
            candidate_codes,
        ),
    )


_matching_aliases = None
_matching_revision = 0


def match_country_text(
    title: str,
    summary: str = "",
    candidate_codes: set[str] | frozenset[str] | None = None,
) -> tuple[MatchEvidence, ...]:
    # Shared feed entries are matched once, then reused across country drawers.
    global _matching_aliases, _matching_revision
    aliases = _aliases()
    if aliases is not _matching_aliases:
        _matching_aliases = aliases
        _matching_revision += 1
    return _cached_country_text(title, summary, _matching_revision, None if candidate_codes is None else frozenset(candidate_codes))


def match_title(title: str, candidate_codes: set[str] | frozenset[str] | None = None) -> tuple[MatchEvidence, ...]:
    return tuple(
        evidence
        for evidence in match_country_text(title, candidate_codes=candidate_codes)
        if evidence.match_class is not MatchClass.SUMMARY_COUNTRY
    )


def matched_country_codes(title: str, candidate_codes: set[str] | frozenset[str] | None = None) -> frozenset[str]:
    return frozenset(match.country_code for match in match_title(title, candidate_codes))
