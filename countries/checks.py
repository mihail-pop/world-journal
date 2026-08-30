from django.core import checks

from .data import CountryDataError, load_capital_data, load_country_data


@checks.register(checks.Tags.staticfiles)
def check_country_data(app_configs, **kwargs):
    try:
        metadata, _geometry = load_country_data()
        load_capital_data(metadata)
    except CountryDataError as error:
        return [
            checks.Error(
                str(error),
                hint="Run tools/build_country_data.py and review docs/country-data.md.",
                id="countries.E001",
            )
        ]
    return []