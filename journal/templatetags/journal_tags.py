from django import template

from journal.formatting import render_body

register = template.Library()


@register.filter
def journal_body(content):
    return render_body(content.body, content.body_format)


@register.filter
def journal_markdown(text):
    return render_body(text)
