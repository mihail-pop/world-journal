"""Validated rich-text documents, local image references and HTML rendering."""

import json
import re
from copy import deepcopy
from html import escape
from urllib.parse import urlsplit
from uuid import UUID

from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils.safestring import mark_safe


EMPTY_DOCUMENT = {"type": "doc", "content": [{"type": "paragraph"}]}
BLOCKS = {"paragraph", "heading", "blockquote", "codeBlock", "bulletList", "orderedList", "taskList", "table", "image", "horizontalRule"}
CHILDREN = {
    "doc": BLOCKS, "paragraph": {"text", "hardBreak"}, "heading": {"text", "hardBreak"},
    "codeBlock": {"text"}, "blockquote": BLOCKS, "bulletList": {"listItem"},
    "orderedList": {"listItem"}, "taskList": {"taskItem"}, "listItem": BLOCKS,
    "taskItem": BLOCKS, "table": {"tableRow"}, "tableRow": {"tableCell", "tableHeader"},
    "tableCell": BLOCKS, "tableHeader": BLOCKS,
}
FONTS = {"Inter", "Overpass", "Roboto", "Segoe UI", "Georgia", "Arial", "monospace"}
COLOR = re.compile(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?\Z")


def text_color(value):
    if not isinstance(value, str):
        return None
    if COLOR.fullmatch(value):
        return value
    match = re.fullmatch(r"rgb\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)", value)
    if match and all(int(component) <= 255 for component in match.groups()):
        return "#" + "".join(f"{int(component):02x}" for component in match.groups())
    return None


def highlight_ink(value):
    color = text_color(value)
    if not color:
        return None
    color = color.lstrip("#")
    if len(color) == 3:
        color = "".join(char * 2 for char in color)
    red, green, blue = (int(color[start:start + 2], 16) for start in (0, 2, 4))
    return "dark" if red * .299 + green * .587 + blue * .114 >= 140 else "light"


def image_url(attachment_id):
    return reverse("journal:image", args=[attachment_id])


def safe_link(value):
    if not isinstance(value, str) or len(value) > 2048 or any(ord(char) < 32 for char in value) or "\\" in value:
        return ""
    try:
        parts = urlsplit(value)
        if parts.scheme.lower() in {"https", "http"} and parts.netloc:
            return value
        if not parts.scheme and not parts.netloc and value.startswith(("/", "#")) and not value.startswith("//"):
            return value
    except ValueError:
        pass
    return ""


def validate_document(value):
    """Normalize the supported schema; arbitrary HTML/CSS never reaches readers."""
    if not value:
        return deepcopy(EMPTY_DOCUMENT)
    if isinstance(value, str):
        if len(value.encode("utf-8")) > 1_000_000:
            raise ValidationError("This document is too large. Split it into sections.")
        try:
            value = json.loads(value)
        except (ValueError, RecursionError) as error:
            raise ValidationError("The document could not be read. Reload the editor and try again.") from error
    remaining = 30000

    def number(value, minimum, maximum, default):
        return value if type(value) is int and minimum <= value <= maximum else default

    def marks(values):
        if not isinstance(values, list) or len(values) > 12:
            raise ValidationError("The document contains invalid text formatting.")
        result = []
        for mark in values:
            if not isinstance(mark, dict):
                raise ValidationError("The document contains invalid text formatting.")
            kind, attrs = mark.get("type"), mark.get("attrs") or {}
            if not isinstance(kind, str) or not isinstance(attrs, dict):
                raise ValidationError("The document contains invalid text formatting.")
            if kind in {"bold", "italic", "underline", "strike", "code"}:
                result.append({"type": kind})
            elif kind == "link":
                href = safe_link(attrs.get("href"))
                if not href:
                    raise ValidationError("Use an http or https link.")
                result.append({"type": kind, "attrs": {"href": href, "target": "_blank" if urlsplit(href).scheme else None, "rel": "noopener noreferrer"}})
            elif kind == "textStyle":
                styles = {}
                for key in ("color", "backgroundColor"):
                    color = text_color(attrs.get(key))
                    if color:
                        styles[key] = color
                size = str(attrs.get("fontSize") or "")
                if re.fullmatch(r"(?:[8-9]|[1-6][0-9]|7[0-2])(?:px|pt)", size):
                    styles["fontSize"] = size
                if isinstance(attrs.get("fontFamily"), str) and attrs["fontFamily"] in FONTS:
                    styles["fontFamily"] = attrs["fontFamily"]
                if str(attrs.get("lineHeight")) in {"1", "1.15", "1.5", "1.75", "2"}:
                    styles["lineHeight"] = str(attrs["lineHeight"])
                if styles:
                    result.append({"type": kind, "attrs": styles})
            else:
                raise ValidationError("The document contains unsupported text formatting.")
        return result

    def visit(node, depth=0):
        nonlocal remaining
        remaining -= 1
        if depth > 40 or remaining < 0 or not isinstance(node, dict):
            raise ValidationError("The document is too complex. Split it into sections.")
        kind = node.get("type")
        if not isinstance(kind, str) or kind not in {*CHILDREN, "text", "hardBreak", "image", "horizontalRule"}:
            raise ValidationError("The document contains unsupported content.")
        result = {"type": kind}
        attrs = node.get("attrs") or {}
        if not isinstance(attrs, dict):
            raise ValidationError("The document contains invalid content.")
        cleaned = {}
        if kind == "text":
            if not isinstance(node.get("text"), str) or not node["text"]:
                raise ValidationError("The document contains invalid text.")
            result["text"] = node["text"]
            if node.get("marks"):
                result["marks"] = marks(node["marks"])
        if kind in {"paragraph", "heading"}:
            if isinstance(attrs.get("textAlign"), str) and attrs["textAlign"] in {"left", "center", "right", "justify"}:
                cleaned["textAlign"] = attrs["textAlign"]
        if kind == "heading":
            cleaned["level"] = number(attrs.get("level"), 1, 3, 2)
        if kind == "orderedList":
            cleaned["start"] = number(attrs.get("start"), 1, 100000, 1)
        if kind == "taskItem":
            cleaned["checked"] = attrs.get("checked") is True
        if kind in {"tableCell", "tableHeader"}:
            for key in ("colspan", "rowspan"):
                cleaned[key] = number(attrs.get(key), 1, 30, 1)
            widths = attrs.get("colwidth")
            if isinstance(widths, list) and len(widths) <= 30 and all(type(width) is int and 0 <= width <= 2000 for width in widths):
                cleaned["colwidth"] = widths
            else:
                cleaned["colwidth"] = None
        if kind == "image":
            try:
                attachment_id = str(UUID(str(attrs.get("attachmentId"))))
            except ValueError as error:
                raise ValidationError("An image is still uploading or is not a local journal image.") from error
            cleaned = {"attachmentId": attachment_id, "src": image_url(attachment_id), "alt": str(attrs.get("alt") or "")[:255]}
            alignment = attrs.get("alignment")
            if isinstance(alignment, str) and alignment in {"left", "center", "right"}:
                cleaned["alignment"] = alignment
            for key in ("width", "height"):
                dimension = attrs.get(key)
                if isinstance(dimension, str) and len(dimension) <= 5 and dimension.isdigit():
                    dimension = int(dimension)
                if type(dimension) is float and 20 <= dimension <= 10000:
                    dimension = round(dimension)
                if type(dimension) is int and 20 <= dimension <= 10000:
                    cleaned[key] = dimension
        if cleaned:
            result["attrs"] = cleaned
        if kind in CHILDREN:
            children = node.get("content", [])
            if not isinstance(children, list):
                raise ValidationError("The document contains invalid content.")
            content = [visit(child, depth + 1) for child in children]
            if any(child["type"] not in CHILDREN[kind] for child in content):
                raise ValidationError("The document contains misplaced content.")
            if kind in {"doc", "blockquote", "listItem", "taskItem", "tableCell", "tableHeader"} and not content:
                content = [{"type": "paragraph"}]
            if kind in {"listItem", "taskItem"} and content[0]["type"] != "paragraph":
                raise ValidationError("A list item must start with a paragraph.")
            if kind in {"table", "tableRow", "bulletList", "orderedList", "taskList"} and not content:
                raise ValidationError("The document contains an empty table or list.")
            if content:
                result["content"] = content
        return result

    document = visit(value)
    if document["type"] != "doc":
        raise ValidationError("The document must have a document root.")
    return document


def nodes(document):
    yield document
    for child in document.get("content", []):
        yield from nodes(child)


def image_ids(document):
    return {UUID(node["attrs"]["attachmentId"]) for node in nodes(document) if node["type"] == "image"}


def document_text(document):
    def text(node):
        kind = node["type"]
        if kind == "text":
            return node["text"]
        if kind == "hardBreak":
            return "\n"
        if kind == "image":
            return ""
        separator = "" if kind in {"paragraph", "heading", "codeBlock"} else "\n"
        return separator.join(text(child) for child in node.get("content", []))
    return text(document).strip()


def serialize_document(document):
    return json.dumps(document, ensure_ascii=False, separators=(",", ":"))


def render_document(document, *, limit=None):
    remaining = limit

    def render(node):
        nonlocal remaining
        kind, attrs = node["type"], node.get("attrs", {})
        if remaining is not None and remaining <= 0:
            return ""
        if kind == "text":
            text = node["text"] if remaining is None else node["text"][:remaining]
            if remaining is not None:
                remaining -= len(text)
            html = escape(text)
            for mark in node.get("marks", []):
                tag = {"bold": "strong", "italic": "em", "underline": "u", "strike": "s", "code": "code"}.get(mark["type"])
                if tag:
                    html = f"<{tag}>{html}</{tag}>"
                elif mark["type"] == "textStyle":
                    properties = {"color": "color", "backgroundColor": "background-color", "fontSize": "font-size", "fontFamily": "font-family", "lineHeight": "line-height"}
                    style = ";".join(f"{properties[key]}:{value}" for key, value in mark["attrs"].items())
                    ink = highlight_ink(mark["attrs"].get("backgroundColor")) if not mark["attrs"].get("color") else None
                    contrast = f' data-highlight-ink="{ink}"' if ink else ""
                    html = f'<span style="{escape(style, quote=True)}"{contrast}>{html}</span>'
                elif mark["type"] == "link":
                    href = mark["attrs"]["href"]
                    extra = ' target="_blank" rel="noopener noreferrer"' if urlsplit(href).scheme else ' class="journal-country-link"'
                    html = f'<a href="{escape(href, quote=True)}"{extra}>{html}</a>'
            return html
        if kind == "hardBreak":
            return "<br>"
        if kind == "horizontalRule":
            return "<hr>"
        if kind == "image":
            if limit is not None:
                return ""
            size = "".join(f' {key}="{attrs[key]}"' for key in ("width", "height") if key in attrs)
            return f'<img src="{escape(attrs["src"], quote=True)}" alt="{escape(attrs["alt"], quote=True)}" data-image-align="{attrs.get("alignment", "left")}"{size} loading="lazy">'
        if kind == "table":
            children = node.get("content", [])
            header = children and all(cell["type"] == "tableHeader" for cell in children[0].get("content", []))
            heading = f"<thead>{render(children[0])}</thead>" if header else ""
            start = 1 if header else 0
            content = heading + "<tbody>" + "".join(render(child) for child in children[start:]) + "</tbody>"
        else:
            content = "".join(render(child) for child in node.get("content", []))
        if kind == "doc":
            return content
        if kind == "codeBlock":
            return f"<pre><code>{content}</code></pre>"
        tag = {"paragraph": "p", "heading": f'h{attrs.get("level", 2)}', "blockquote": "blockquote", "bulletList": "ul", "orderedList": "ol", "listItem": "li", "taskList": "ul", "taskItem": "li", "table": "table", "tableRow": "tr", "tableCell": "td", "tableHeader": "th"}[kind]
        attributes = ""
        if attrs.get("textAlign"):
            attributes += f' style="text-align:{attrs["textAlign"]}"'
        if kind == "orderedList":
            attributes += f' start="{attrs.get("start", 1)}"'
        if kind in {"tableCell", "tableHeader"}:
            attributes += f' colspan="{attrs["colspan"]}" rowspan="{attrs["rowspan"]}"'
            if attrs.get("colwidth"):
                attributes += f' style="width:{sum(attrs["colwidth"])}px"'
        if kind == "taskList":
            attributes += ' data-type="taskList"'
        if kind == "taskItem":
            attributes += f' data-type="taskItem" data-checked="{str(attrs["checked"]).lower()}"'
            content = f'<span class="journal-task-check" aria-label="{"Checked" if attrs["checked"] else "Unchecked"}">{"☑" if attrs["checked"] else "☐"}</span><div>{content}</div>'
        return f"<{tag}{attributes}>{content}</{tag}>"

    return mark_safe(render(document))
