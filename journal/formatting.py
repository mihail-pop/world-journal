import json
import unicodedata
from functools import lru_cache
from urllib.parse import urlsplit

from django.conf import settings
from django.utils.safestring import mark_safe
from markdown_it import MarkdownIt


def normalize_name(value):
    return unicodedata.normalize("NFC", " ".join(value.split())).casefold()


@lru_cache(maxsize=1)
def country_aliases():
    metadata = json.loads((settings.BASE_DIR / "data/countries.json").read_text(encoding="utf-8"))
    config = json.loads(settings.NEWS_COUNTRY_ALIASES_PATH.read_text(encoding="utf-8"))
    aliases = {}
    for country in metadata["countries"]:
        code = country["iso_a2"]
        # Explicit [[...]] references allow names that are ambiguous in ordinary news.
        names = [country["name"], code, *config["countries"].get(code, {}).get("name_aliases", [])]
        for name in names:
            key = normalize_name(name)
            aliases.setdefault(key, set()).add(code)
    return {name: next(iter(codes)) for name, codes in aliases.items() if len(codes) == 1}


def country_reference(state, silent):
    if state.linkLevel or not state.src.startswith("[[", state.pos):
        return False
    end = state.src.find("]]", state.pos + 2)
    if end == -1:
        return False
    label = state.src[state.pos + 2:end]
    code = country_aliases().get(normalize_name(label))
    if not code:
        return False
    if not silent:
        token = state.push("link_open", "a", 1)
        token.attrs = {"href": f"/?country={code}", "class": "journal-country-link"}
        state.push("text", "", 0).content = label
        state.push("link_close", "a", -1)
        state.env.setdefault("country_codes", set()).add(code)
    state.pos = end + 2
    return True


@lru_cache(maxsize=1)
def markdown_renderer():
    renderer = MarkdownIt("commonmark", {"html": False, "breaks": True}).enable(["table", "strikethrough"]).disable("image")
    renderer.inline.ruler.before("link", "country_reference", country_reference)
    def valid_link(url):
        try:
            return urlsplit(url).scheme.lower() in {"", "http", "https"} and not url.startswith("//")
        except ValueError:
            return False
    renderer.validateLink = valid_link
    default_link = renderer.renderer.rules.get("link_open")
    def link_open(tokens, index, options, env):
        token = tokens[index]
        if urlsplit(token.attrGet("href") or "").scheme:
            token.attrSet("target", "_blank")
            token.attrSet("rel", "noopener noreferrer")
        if default_link:
            return default_link(tokens, index, options, env)
        return renderer.renderer.renderToken(tokens, index, options, env)
    renderer.renderer.rules["link_open"] = link_open
    return renderer


def render_body(body, body_format="markdown"):
    # Raw HTML and remote images are disabled; only parser-generated HTML is trusted.
    return mark_safe(markdown_renderer().render(body))


def referenced_countries(body, body_format):
    env = {}
    markdown_renderer().parse(body, env)
    return env.get("country_codes", set())
