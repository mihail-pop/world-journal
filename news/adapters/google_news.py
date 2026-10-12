from urllib.parse import urlencode

from news.types import NewsSource, SourceKind


QUERY_OVERRIDES = {
    "XI": '"Siachen Glacier" OR "Siachen"',
    "XP": '"Southern Patagonian Ice Field"',
    "XD": '"Dhekelia"',
    "XA": '"Akrotiri" "Cyprus"',
    "XG": '"Guantanamo Bay"',
    "CI": '"Ivory Coast" OR "Cote d\'Ivoire"',
    "CZ": '"Czech Republic" OR "Czechia"',
    "GE": '"Georgia" country',
    "JO": '"Jordan" country',
    "KR": '"South Korea" OR "Republic of Korea"',
    "KP": '"North Korea" OR "Democratic People\'s Republic of Korea"',
    "PS": '"Palestine" OR "Palestinian territories"',
    "TD": '"Chad" country',
    "TR": '"Turkey" OR "Turkiye"',
    "US": '"United States" OR "United States of America"',
}


def build_country_query(country: dict) -> str:
    return QUERY_OVERRIDES.get(country["iso_a2"], f'"{country["name"]}"')


def build_feed_url(source: NewsSource, country: dict) -> str:
    if source.kind is not SourceKind.DYNAMIC_COUNTRY_RSS or not source.feed_host:
        raise ValueError("Google News requires a dynamic country RSS source")
    if country["iso_a2"] == "WORLD":
        return f"https://{source.feed_host}/rss/headlines/section/topic/WORLD?{urlencode(source.edition_parameters)}"
    parameters = {"q": build_country_query(country), **source.edition_parameters}
    return f"https://{source.feed_host}/rss/search?{urlencode(parameters)}"
