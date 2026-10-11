# Offline country overview

The country drawer has Overview, Articles, Videos and Notes. Articles remain the default. Overview displays bundled facts, with no external facts request. `/?country=RO&section=overview` opens it directly. News and videos retain their existing independent feed providers.

## Source and storage

`data/country_facts.json` is a real, dated Wikidata snapshot containing population, reported area, capitals, official languages, currencies, basic government forms and available sourced ethnic/religious percentages. It includes source links, statement identifiers for quantities, observation dates when supplied and an English Wikipedia link when available. Wikidata structured data is CC0. Missing values remain explicitly missing; no fabricated fallback figures are used.

Natural Earth remains the source for map geometry, the canonical ISO catalog, regions and subregions. See `docs/country-data.md` for geographic policy. Facts are associated through Natural Earth's pinned `WIKIDATAID` mapping and verified against both Wikidata ISO alpha-2 (`P297`) and alpha-3 (`P298`) properties.

Three reviewed exceptions use the current ISO entity instead of Natural Earth's polygon-level entity:

- NL/NLD: [Kingdom of the Netherlands, Q29999](https://www.wikidata.org/wiki/Q29999). The Netherlands constituent-country entity Q55 explicitly deprecates its ISO claims in favour of Q29999. The overview explains that the facts cover the Kingdom, including Caribbean constituent countries.
- PS/PSE: [Palestine, Q219060](https://www.wikidata.org/wiki/Q219060), rather than the geographic-region entity Q23792.
- SH/SHN: [Saint Helena, Ascension and Tristan da Cunha, Q192184](https://www.wikidata.org/wiki/Q192184), rather than Saint Helena island Q34497. The overview explains the combined coverage.

These mappings do not change map boundaries or country routing. Refreshes revalidate all ISO identities before replacing the snapshot.

The shipped snapshot verifies all 238 catalog identities and provides population for 237, area for 236, capitals for 232, currencies for 236 and official languages for 236. The added fields cover government forms for 168 countries/territories, sourced ethnic percentages for 50 and sourced religious percentages for 10. Coverage describes this download, not a guarantee about future upstream data.

## Selection policy and limitations

The builder selects nondeprecated statements, excludes future observations and statements outside their supplied start/end interval, prefers preferred rank, then selects the newest supplied date for population and area. Equally ranked quantities with the same latest date are retained and shown as conflicting figures. Undated values are labelled "date not specified"; the download date is never presented as an observation year.

Population uses `P1082`, accepting integral counts. Area uses `P2046`, converting explicitly supported square metres, square kilometres, hectares and square miles to km2. Part-specific quantity claims (`P518`) are excluded, except area explicitly qualified as the whole (`Q16868672`) or as both land (`Q11081619`) and sea (`Q165`). A land-only or sea-only figure is not silently substituted for total reported area. "Reported area" is deliberately used because Wikidata figures can have different definitions; they are not necessarily equivalent to the former World Bank surface-area indicator or to the map polygon's area. Capitals (`P36`), currencies (`P38`) and official languages (`P37`) preserve multiple selected values and link to their Wikidata records. Rank selection for these entity values is performed within each territorial scope, so a value preferred for one constituent territory cannot hide a current value for another. Labels use English when present, then Wikidata's shared multilingual (`mul`) label, which includes the euro. Values without either label remain omitted.

Wikidata is community maintained. Preferred rank and a recent date do not guarantee accuracy, complete coverage or an up-to-date census. The snapshot fixes availability during browsing, not the quality of every upstream claim. Some countries and territories lack particular values. Source links and observation dates let users inspect them.

- [Wikidata data access](https://www.wikidata.org/wiki/Wikidata:Data_access)
- [Statement ranking](https://www.wikidata.org/wiki/Help:Ranking)
- [Wikimedia API etiquette](https://www.mediawiki.org/wiki/API:Etiquette)

## Updating the snapshot

Run from the project folder when a source refresh is wanted:

```powershell
.\.venv\Scripts\python.exe tools\build_country_facts.py
```

The standalone standard-library builder downloads and hash-checks the pinned Natural Earth DBF, then requests Wikidata in small serial batches. Downloads have bounded size, timeouts and retries. An optional `--user-agent` accepts a descriptive agent containing your real contact URL/email. Wikimedia services have usage policies and limits; there is no claim of unlimited API access.

The old snapshot remains in place until all requests finish, all identities match and field coverage has not unexpectedly dropped by more than 10%. The complete file is then replaced atomically. The builder records its retrieval time, mapping source/hash, exceptions and selection policy. The application rereads a changed snapshot automatically; no scheduled jobs, API keys, new dependencies or migrations are required.

The earlier per-country World Bank requests and their runtime cache path have been removed. Ignored database cache rows from that version are untouched and unused. Those rows showed failed area fetches for Romania and Poland but did not retain an error reason, so the precise network failure cannot be diagnosed from them.

## Loading behaviour

Opening Overview fetches only the application's local HTML partial. Returning to an already loaded Overview tab does not refetch it. Country changes, drawer closure and fully discarding a map instance abort pending requests and invalidate result identifiers. Section navigation now retains the Map workspace and its loaded Overview; see [Page memory](page-memory.md). Responses carry the country code so another country's late result cannot replace the selected country's content. Facts remain accessible without internet when the local server is running; online basemaps, news, videos and external source links have their own network requirements.

## Manual acceptance

No automated tests or browser checks were added or run, at the user's request. Start the app:

```powershell
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

Open `http://127.0.0.1:8000/` and hard-refresh to load the changed JavaScript.

1. Select Romania or Poland: Articles stays the default. Open Overview: population and reported area appear immediately with their supplied date or an explicit undated label, plus capitals, languages, currencies and source links.
2. Switch repeatedly between countries, close/reopen the drawer and use back/forward. Facts must correspond to the selected country. Returning to an already loaded Overview tab should retain its content.
3. Disconnect internet while leaving the local server running: Overview should still show facts, including for a previously unopened country. Other online features can fail independently.
4. Check Netherlands and Saint Helena: the coverage note should explain which territory the figures describe. Missing or conflicting values should be described plainly.
5. Check dark/light/brown and a 390px window. Facts and links should wrap; all four tabs should fit. Existing news, personal notes and persistent video playback should continue to work across Map/Journal/Settings navigation.

Current officeholders, cabinet formation and other descriptive fields remain deferred; basic government form is included. News-source Settings, backups and statistics are subsequent application phases.

## Government and demographic percentages

Wikidata is structured data, not a copy of the Wikipedia infobox or article. Wikipedia can contain census tables and percentages that the associated Wikidata item does not contain. These additions keep the same offline snapshot and introduce no runtime API requests or dependencies.

- Government forms use [P122](https://www.wikidata.org/wiki/Property:P122). Multiple selected forms are preserved. Observation year or start year is shown when supplied; otherwise the UI states that the date is unspecified. Expired historical forms are excluded, subject to the source having supplied end dates. This is a source classification, not a claim about current cabinet members or government legitimacy.
- Ethnic categories use country-level [P172](https://www.wikidata.org/wiki/Property:P172); religious categories use country-level [P140](https://www.wikidata.org/wiki/Property:P140). Only statements with an explicit, valid [P1107 proportion](https://www.wikidata.org/wiki/Property:P1107) and an upstream reference are included. Unitless shares from 0 to 1 are converted to percentages, including zero. An absent share is never converted to zero or estimated from another population count.
- Demographics select the newest nonfuture observation date within each territorial scope, then rank within each category. This retains minority categories without mixing older figures into a newer dated cohort. Undated records are retained only when that scope has no dated records. Scope labels are displayed when supplied. Equal-ranked conflicting percentages are retained visibly.
- Reference identifiers and statement identifiers are preserved in the snapshot, with links to the country property and category. References may be Wikimedia imports or other source material: their presence does not itself prove accuracy. Source links expose the underlying qualifiers, references and survey definitions.
- [P3075 official religion](https://www.wikidata.org/wiki/Property:P3075) is not a population breakdown and is not substituted for one. Names without a valid sourced share are omitted. Empty sections say there is no sourced percentage breakdown in the snapshot, not that the country has no ethnic groups or religion.

Lists are explicitly partial. Categories can overlap, use different survey definitions or have exclusions; totals are not summed, normalized to 100%, or filled with an invented Other category. Dates can be old, and Wikidata coverage can be much thinner than Wikipedia. No Wikipedia scraping or extra data provider was added to fill gaps.

Additional manual checks: Poland's Overview should show dated ethnic percentages (for example, Poles 96.9% in the source's 2011 cohort); Romania should show its government classifications and an explicit missing percentage-breakdown message. India should show the sourced religious shares available in its record, with an undated observation warning. Follow Source links to inspect definitions and references. Check long group names and multiple rows on a narrow screen. No tests or browser checks were performed.
