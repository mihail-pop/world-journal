"""Shared Preferences values and partial updates to the AppSettings singleton."""
import uuid

from countries.models import Country, MapPreset

from .database import write_transaction
from .models import AppSettings


PREFERENCE_FIELDS = {
    "theme": "theme", "font": "font", "mapType": "map_type",
    "homeCountry": "home_country_id", "activePreset": "active_preset_id",
    "countryNames": "country_names", "capitalNames": "capital_names",
    "cityNames": "city_names", "regionNames": "region_names",
    "smallCountryMarkers": "small_country_markers", "protectedAreas": "protected_areas",
    "vegetation": "vegetation", "relief": "relief", "water": "water",
    "transport": "transport", "buildings": "buildings", "landUse": "land_use",
    "administrativeBorders": "administrative_borders", "pointsOfInterest": "points_of_interest",
    "allOtherText": "all_other_text",
}


def preferences_snapshot(instance=None):
    if instance is None:
        instance = AppSettings.objects.filter(pk=1).first() or AppSettings(pk=1)
    data = {key: getattr(instance, field) for key, field in PREFERENCE_FIELDS.items()}
    data["activePreset"] = str(data["activePreset"]) if data["activePreset"] else None
    return {**data, "revision": instance.revision}


def validate_preferences(payload):
    if not isinstance(payload, dict) or not payload or payload.keys() - PREFERENCE_FIELDS.keys():
        raise ValueError("Choose available Preferences settings.")
    values = {}
    choices = {"theme": AppSettings.Theme.values, "font": AppSettings.Font.values, "mapType": AppSettings.MapType.values}
    for key, value in payload.items():
        if key in choices:
            if not isinstance(value, str) or value not in choices[key]:
                raise ValueError(f"Choose an available {key}.")
        elif key == "homeCountry":
            if value is not None and (not isinstance(value, str) or len(value) != 2 or not Country.objects.filter(pk=value).exists()):
                raise ValueError("Choose an available home country.")
        elif key == "activePreset":
            if value is not None:
                try:
                    value = uuid.UUID(value) if isinstance(value, str) else None
                except ValueError:
                    value = None
                if value is None or not MapPreset.objects.filter(pk=value).exists():
                    raise ValueError("Choose an available color preset.")
        elif type(value) is not bool:
            raise ValueError("Map options must be true or false.")
        values[PREFERENCE_FIELDS[key]] = value
    return values


def save_preferences(values):
    # Read and update inside one queued transaction. Each request changes only
    # its own fields, so another tab cannot overwrite unrelated newer choices.
    with write_transaction():
        instance = AppSettings.objects.filter(pk=1).first() or AppSettings(pk=1)
        for name, value in values.items():
            setattr(instance, name, value)
        instance.revision += 1
        instance.save()
        return instance
