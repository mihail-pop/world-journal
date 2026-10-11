import json
import re
import unicodedata
from functools import lru_cache
from urllib.parse import urlsplit

from django.conf import settings
from django.core.exceptions import ValidationError
from django.template.loader import render_to_string
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from markdown_it import MarkdownIt
from markdown_it.token import Token

from .validators import parse_youtube_reference


YOUTUBE_URL = re.compile(r"(?<![\w./@-])(?:https?://)?(?:(?:www|m|music)\.)?(?:youtube\.com|youtube-nocookie\.com|youtu\.be)/[^\s<>]+", re.IGNORECASE)


def video_token(url, title=""):
    if not YOUTUBE_URL.fullmatch(url):
        return None
    try:
        video_id, seconds = parse_youtube_reference(url if urlsplit(url).scheme else "https://" + url)
    except ValidationError:
        return None
    token = Token("youtube_video", "span", 0)
    token.meta = {"id": video_id, "seconds": seconds or 0, "title": title if title and title != url else "YouTube video"}
    return token


def youtube_links(state):
    """Convert validated text/Markdown links, leaving code and other links alone."""
    for block in state.tokens:
        if block.type != "inline" or not block.children:
            continue
        children, result, index, link_depth = block.children, [], 0, 0
        while index < len(children):
            token = children[index]
            if token.type == "link_open":
                end = index + 1
                while end < len(children) and children[end].type != "link_close":
                    end += 1
                title = "".join(child.content for child in children[index + 1:end] if child.type in {"text", "code_inline"})
                video = video_token(token.attrGet("href") or "", title)
                if video and end < len(children):
                    result.append(video)
                    index = end + 1
                    continue
                link_depth += 1
            elif token.type == "link_close":
                link_depth -= 1
            if token.type == "text" and not link_depth:
                offset = 0
                for match in YOUTUBE_URL.finditer(token.content):
                    url = match.group().rstrip(".,;:!?)]}")
                    video = video_token(url)
                    if not video:
                        continue
                    if match.start() > offset:
                        text = Token("text", "", 0)
                        text.content = token.content[offset:match.start()]
                        result.append(text)
                    result.append(video)
                    offset = match.start() + len(url)
                if offset:
                    if offset < len(token.content):
                        text = Token("text", "", 0)
                        text.content = token.content[offset:]
                        result.append(text)
                    index += 1
                    continue
            result.append(token)
            index += 1
        block.children = result


def render_video(tokens, index, options, env):
    video = tokens[index].meta
    # Only a validated ID and bounded timestamp reach the shell player. No
    # iframe or embed HTML supplied in the Markdown is ever accepted.
    return str(format_html(
        '<span class="journal-inline-video"><span class="journal-inline-video-heading">{}</span>'
        '<span class="journal-inline-video-actions"><button type="button" class="journal-button" data-journal-play '
        'data-video-id="{}" data-video-title="{}" data-video-channel="YouTube" data-video-start="{}">'
        '{}Play video</button>'
        '<a href="https://www.youtube.com/watch?v={}&amp;t={}s" target="_blank" rel="noopener noreferrer">Open on YouTube</a></span></span>',
        video["title"], video["id"], video["title"], video["seconds"], mark_safe(render_to_string("core/partials/icon.html", {"name": "play"})), video["id"], video["seconds"],
    ))


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
    renderer.core.ruler.after("inline", "youtube_links", youtube_links)
    renderer.renderer.rules["youtube_video"] = render_video
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
