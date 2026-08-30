from django.core.checks import Error, Tags, register

from .registry import SourceConfigurationError, load_source_registry


@register(Tags.files)
def check_news_sources(app_configs, **kwargs):
    try:
        load_source_registry()
    except SourceConfigurationError as error:
        return [Error(str(error), id="news.E001")]
    return []