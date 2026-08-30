from django.core.checks import Error, Tags, register

from .registry import SourceConfigurationError, load_source_registry
from .services.country_matcher import AliasConfigurationError, _load_alias_config


@register(Tags.files)
def check_news_sources(app_configs, **kwargs):
    errors = []
    try:
        load_source_registry()
    except SourceConfigurationError as error:
        errors.append(Error(str(error), id="news.E001"))
    try:
        _load_alias_config()
    except AliasConfigurationError as error:
        errors.append(Error(str(error), id="news.E002"))
    return errors