import io

from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils.text import slugify
from django.views.decorators.http import require_GET
from django.views.decorators.cache import never_cache

from core.preferences import preferences_snapshot

from .documents import validate_document
from .models import Entry


FONT_NAMES = {"inter": "Inter", "overpass": "Overpass", "roboto": "Roboto", "segoe": "Segoe UI", "os": "Arial"}


def content_document(content):
    if content.body_format == "richtext":
        return validate_document(content.body)
    return {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": line}]} if line else {"type": "paragraph"} for line in content.body.splitlines()]}


def word_document(entry, *, font="Inter"):
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.opc.constants import RELATIONSHIP_TYPE as RT
    from docx.shared import Mm, Pt, RGBColor

    output = Document()
    output.core_properties.title = entry.title
    output.core_properties.author = ""
    section = output.sections[0]
    section.page_width, section.page_height = Mm(210), Mm(297)
    section.top_margin = section.bottom_margin = section.left_margin = section.right_margin = Mm(20)
    width = section.page_width - section.left_margin - section.right_margin
    normal = output.styles["Normal"]
    normal.font.name, normal.font.size = font, Pt(11)
    normal.paragraph_format.space_after = Pt(7)
    normal.paragraph_format.widow_control = True
    for name in ("Title", "Heading 1", "Heading 2", "Heading 3"):
        output.styles[name].font.name = font
        output.styles[name].font.color.rgb = RGBColor(0, 0, 0)
        output.styles[name].paragraph_format.keep_with_next = True
    images = {str(image.pk): image for image in entry.attachments.all()}

    def inline(paragraph, node):
        kind = node["type"]
        if kind == "hardBreak":
            paragraph.add_run().add_break()
            return
        run = paragraph.add_run(node["text"])
        for mark in node.get("marks", []):
            name, attrs = mark["type"], mark.get("attrs", {})
            if name in {"bold", "italic", "underline"}:
                setattr(run, name, True)
            elif name == "strike":
                run.font.strike = True
            elif name == "code":
                run.font.name = "Consolas"
            elif name == "textStyle":
                if color := attrs.get("color"):
                    color = color.lstrip("#")
                    if len(color) == 3:
                        color = "".join(char * 2 for char in color)
                    run.font.color.rgb = RGBColor.from_string(color.upper())
                if family := attrs.get("fontFamily"):
                    run.font.name = "Consolas" if family == "monospace" else family
                if size := attrs.get("fontSize"):
                    run.font.size = Pt(float(size[:-2]) * (.75 if size.endswith("px") else 1))
                if height := attrs.get("lineHeight"):
                    paragraph.paragraph_format.line_spacing = float(height)
                if background := attrs.get("backgroundColor"):
                    background = background.lstrip("#")
                    if len(background) == 3:
                        background = "".join(char * 2 for char in background)
                    shading = OxmlElement("w:shd")
                    shading.set(qn("w:fill"), background)
                    run._r.get_or_add_rPr().append(shading)
            elif name == "link":
                link = OxmlElement("w:hyperlink")
                link.set(qn("r:id"), paragraph.part.relate_to(attrs["href"], RT.HYPERLINK, is_external=True))
                run.underline = True
                link.append(run._r)
                paragraph._p.append(link)

    def paragraph(container, node, style=None, prefix=""):
        result = container.add_paragraph(style=style)
        alignment = node.get("attrs", {}).get("textAlign")
        if alignment:
            result.alignment = {"left": WD_ALIGN_PARAGRAPH.LEFT, "right": WD_ALIGN_PARAGRAPH.RIGHT, "center": WD_ALIGN_PARAGRAPH.CENTER, "justify": WD_ALIGN_PARAGRAPH.JUSTIFY}[alignment]
        if prefix:
            result.add_run(prefix)
        for child in node.get("content", []):
            inline(result, child)
        return result

    def table(container, node):
        occupied, placements, columns = set(), [], 1
        rows = node["content"]
        for y, row in enumerate(rows):
            x = 0
            for cell in row["content"]:
                while (y, x) in occupied:
                    x += 1
                colspan, rowspan = cell["attrs"]["colspan"], min(cell["attrs"]["rowspan"], len(rows) - y)
                placements.append((y, x, rowspan, colspan, cell))
                occupied.update((yy, xx) for yy in range(y, y + rowspan) for xx in range(x, x + colspan))
                x += colspan
                columns = max(columns, x)
        if columns > 60:
            raise ValueError("This table is too wide to export.")
        result = container.add_table(rows=len(rows), cols=columns)
        result.style = "Table Grid"
        result.autofit = False
        for column in result.columns:
            column.width = int(width / columns)
        for y, x, rowspan, colspan, node in placements:
            cell = result.cell(y, x)
            if rowspan > 1 or colspan > 1:
                cell = cell.merge(result.cell(y + rowspan - 1, x + colspan - 1))
            cell.text = ""
            blocks(cell, node.get("content", []))
            if len(cell.paragraphs) > 1 and not cell.paragraphs[0].text:
                first = cell.paragraphs[0]._p
                first.getparent().remove(first)
            if node["type"] == "tableHeader":
                for text in cell.paragraphs:
                    for run in text.runs:
                        run.bold = True
        for index, row in enumerate(rows):
            if all(cell["type"] == "tableHeader" for cell in row["content"]):
                result.rows[index]._tr.get_or_add_trPr().append(OxmlElement("w:tblHeader"))

    def blocks(container, children, *, list_style=None, depth=0):
        for node in children:
            kind, attrs = node["type"], node.get("attrs", {})
            if kind in {"paragraph", "heading"}:
                style = f'Heading {attrs["level"]}' if kind == "heading" else list_style
                result = paragraph(container, node, style)
                if depth:
                    result.paragraph_format.left_indent = Mm(5 * depth)
                list_style = None
            elif kind in {"bulletList", "orderedList", "taskList"}:
                for index, item in enumerate(node["content"], attrs.get("start", 1)):
                    content = item.get("content", [])
                    if kind == "taskList":
                        if content:
                            paragraph(container, content[0], prefix="☑ " if item["attrs"]["checked"] else "☐ ")
                            blocks(container, content[1:], depth=depth + 1)
                    else:
                        # Explicit numbers preserve separate lists and their starting value.
                        if content:
                            result = paragraph(container, content[0], "List Bullet" if kind == "bulletList" else None, prefix=f"{index}. " if kind == "orderedList" else "")
                            result.paragraph_format.left_indent = Mm(5 * (depth + 1))
                            blocks(container, content[1:], depth=depth + 1)
            elif kind == "blockquote":
                blocks(container, node.get("content", []), depth=depth + 1)
            elif kind == "codeBlock":
                result = paragraph(container, node)
                for run in result.runs:
                    run.font.name = "Consolas"
                    run.font.size = Pt(10)
            elif kind == "horizontalRule":
                result = container.add_paragraph()
                borders = OxmlElement("w:pBdr")
                border = OxmlElement("w:bottom")
                for key, value in {"val": "single", "sz": "4", "color": "AAAAAA"}.items():
                    border.set(qn("w:" + key), value)
                borders.append(border)
                result._p.get_or_add_pPr().append(borders)
            elif kind == "table":
                table(container, node)
            elif kind == "image":
                image = images.get(attrs["attachmentId"])
                if not image:
                    raise ValueError("A document image is missing.")
                target_width = min(width, int(Pt(attrs.get("width", image.width) * .75)))
                target_width = min(target_width, int(Mm(230) * image.width / image.height))
                with image.file.open("rb") as file:
                    # Pillow also normalizes formats that Word cannot embed (e.g. WebP).
                    from PIL import Image
                    with Image.open(file) as picture:
                        picture.seek(0)
                        converted = io.BytesIO()
                        picture.convert("RGBA").save(converted, format="PNG")
                        converted.seek(0)
                    container.add_paragraph().add_run().add_picture(converted, width=target_width)

    def add_content(content):
        blocks(output, content_document(content).get("content", []))
        if content.source_url:
            reference = output.add_paragraph()
            inline(reference, {"type": "text", "text": content.source_name or content.source_url, "marks": [{"type": "link", "attrs": {"href": content.source_url}}]})

    output.add_heading(entry.title, 0)
    add_content(entry)
    for subsection in entry.sections.all():
        output.add_heading(subsection.title, 1)
        add_content(subsection)
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    page = OxmlElement("w:fldSimple")
    page.set(qn("w:instr"), "PAGE")
    footer._p.append(page)
    stream = io.BytesIO()
    output.save(stream)
    stream.seek(0)
    return stream


@never_cache
@require_GET
def export_document(request, pk, format):
    if format not in {"pdf", "docx"}:
        raise Http404
    entry = get_object_or_404(Entry.objects.prefetch_related("sections", "attachments"), pk=pk)
    preferences = preferences_snapshot()
    if format == "pdf":
        return render(request, "journal/print.html", {"entry": entry, "app_font": preferences["font"]})
    try:
        stream = word_document(entry, font=FONT_NAMES.get(preferences["font"], "Inter"))
    except (OSError, ValueError) as error:
        return HttpResponse(f"Word export could not be completed: {error}", status=422, content_type="text/plain")
    return FileResponse(stream, as_attachment=True, filename=(slugify(entry.title)[:100] or "journal") + ".docx", content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
