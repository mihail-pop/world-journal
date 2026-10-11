"""Versioned portable data archives; feed caches and browser preferences are excluded."""

import hashlib
import io
import json
import logging
import re
import tempfile
import uuid
import zipfile
from collections import Counter
from datetime import date, datetime
from pathlib import PurePosixPath

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models, transaction
from django.utils import timezone
from PIL import Image

from countries.models import Country, CountryFavorite, CountryProfile, MapPersonalState, MapPreset, PresetColorGroup, PresetCountry
from journal.models import Attachment, Collection, Entry, EntrySection
from news.models import CustomSource, NewsPreferences, SourcePreference


FORMAT = "world-journal-backup"
VERSION = 4
MANIFEST_LIMIT = 32 * 1024 * 1024
RECORD_LIMIT = 100_000
IMAGE_TYPES = {"image/jpeg": (".jpg", "JPEG"), "image/png": (".png", "PNG"), "image/webp": (".webp", "WEBP"), "image/gif": (".gif", "GIF")}
MEDIA_PATH = re.compile(r"media/[0-9a-f]{32}\.(jpg|png|webp|gif)\Z")

# Order keeps parents before children during import. Registry and country catalog
# definitions ship with the application rather than coming from an archive.
DATASETS = {
    "collections": Collection, "presets": MapPreset, "entries": Entry,
    "sections": EntrySection, "attachments": Attachment,
    "favorites": CountryFavorite, "preset_groups": PresetColorGroup, "preset_colors": PresetCountry,
    "country_profiles": CountryProfile, "custom_sources": CustomSource, "source_preferences": SourcePreference,
    "news_preferences": NewsPreferences, "map_state": MapPersonalState,
}
LABELS = {
    "collections": "Collections", "presets": "Map presets", "entries": "Journal entries",
    "sections": "Subsections", "attachments": "Images", "favorites": "Country favorites",
    "preset_colors": "Preset country colors", "country_profiles": "Country overview notes",
    "preset_groups": "Preset color groups",
    "source_preferences": "Source choices", "news_preferences": "News preferences",
    "map_state": "Active map preset",
    "custom_sources": "Custom news sources",
}

# Freeze archive fields independently of future optional model fields.
# Version 2 adds preset_groups; all version 1 datasets remain unchanged.
# Version 3 adds custom_sources; older archives import with no custom sources.
# Version 4 adds parent_id for grouped custom article feeds.
# New backup versions must retain a reader for older archive versions.
CONTENT_FIELDS = "title body body_format entry_type source_url source_name source_published_at youtube_video_id youtube_start_seconds"
SCHEMA_FIELDS = {
    Collection: "id name description position created_at updated_at",
    MapPreset: "id name description default_color created_at updated_at",
    Entry: f"id {CONTENT_FIELDS} collection_id event_date is_favorite is_pinned created_at updated_at",
    EntrySection: f"id {CONTENT_FIELDS} entry_id position created_at updated_at",
    Attachment: "id entry_id section_id file original_name caption content_type byte_size width height position created_at",
    CountryFavorite: "country_id created_at",
    PresetCountry: "preset_id country_id color",
    PresetColorGroup: "id preset_id color title position",
    CountryProfile: "country_id entry_id updated_at",
    SourcePreference: "source_id enabled updated_at",
    NewsPreferences: "id freshness_minutes updated_at",
    MapPersonalState: "id active_preset_id",
    CustomSource: "id parent_id kind name url feed_format channel_id verified_at last_checked_at last_error created_at updated_at",
}


class BackupError(ValueError):
    pass


def _fields(model):
    fields = {field.attname: field for field in model._meta.concrete_fields}
    return [fields[name] for name in SCHEMA_FIELDS[model].split()]


def _record(instance):
    values = {field.attname: getattr(instance, field.attname) for field in _fields(type(instance))}
    return {name: value.isoformat() if isinstance(value, (date, datetime)) else value for name, value in values.items()}


def export_archive():
    """Return a seekable temporary ZIP. Missing media makes export fail explicitly."""
    output = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024)
    try:
        with transaction.atomic():
            records = {name: [_record(obj) for obj in model.objects.all()] for name, model in DATASETS.items()}
            # A list per entry preserves multi-country associations.
            tags = {}
            for entry_id, code in Entry.objects.values_list("pk", "countries__pk"):
                if code:
                    tags.setdefault(entry_id, []).append(code)
            for record in records["entries"]:
                record["countries"] = sorted(tags.get(record["id"], []))
            attachments = list(Attachment.objects.all())
        media = {}
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
            by_id = {record["id"]: record for record in records["attachments"]}
            for attachment in attachments:
                if attachment.content_type not in IMAGE_TYPES:
                    raise BackupError(f"Image {attachment.id} has an unsupported format.")
                path = f"media/{attachment.id.hex}{IMAGE_TYPES[attachment.content_type][0]}"
                digest = hashlib.sha256()
                size = 0
                try:
                    with attachment.file.open("rb") as source, archive.open(path, "w") as destination:
                        while chunk := source.read(64 * 1024):
                            destination.write(chunk)
                            digest.update(chunk)
                            size += len(chunk)
                except OSError as error:
                    raise BackupError(f"Image {attachment.id} could not be read. Restore its local file before exporting.") from error
                if size != attachment.byte_size:
                    raise BackupError(f"Image {attachment.id} has changed size. Repair this attachment before exporting.")
                by_id[attachment.id]["file"] = path
                media[path] = {"sha256": digest.hexdigest()}
            manifest = {"format": FORMAT, "version": VERSION, "exported_at": timezone.now(), "records": records, "media": media}
            archive.writestr("manifest.json", json.dumps(manifest, cls=DjangoJSONEncoder, ensure_ascii=False), compress_type=zipfile.ZIP_DEFLATED)
        output.seek(0)
        return output
    except Exception:
        output.close()
        raise


def _read_archive(archive):
    members = archive.infolist()
    names = [member.filename for member in members]
    if len(names) != len(set(names)) or "manifest.json" not in names:
        raise BackupError("The archive must contain one manifest and no duplicate file paths.")
    total = 0
    for member in members:
        path = PurePosixPath(member.filename)
        if path.is_absolute() or ".." in path.parts or "\\" in member.filename or ":" in member.filename:
            raise BackupError("The archive contains an unsafe file path.")
        if member.filename != "manifest.json" and not MEDIA_PATH.fullmatch(member.filename):
            raise BackupError("The archive contains an unrecognized file path.")
        limit = MANIFEST_LIMIT if member.filename == "manifest.json" else settings.JOURNAL_IMAGE_MAX_BYTES
        if member.file_size > limit or member.flag_bits & 1:
            raise BackupError("An archive file is too large or encrypted.")
        total += member.file_size
    if total > settings.BACKUP_MAX_BYTES:
        raise BackupError("The expanded backup exceeds the configured size limit.")
    manifest = json.loads(archive.read("manifest.json"))
    if not isinstance(manifest, dict) or manifest.get("format") != FORMAT or type(manifest.get("version")) is not int or manifest["version"] not in {1, 2, 3, VERSION}:
        raise BackupError("Unsupported backup format or version. Use a World Journal version 1–4 archive.")
    records, media = manifest.get("records"), manifest.get("media")
    expected_datasets = set(DATASETS) - ({"preset_groups"} if manifest["version"] == 1 else set()) - ({"custom_sources"} if manifest["version"] < 3 else set())
    if not isinstance(records, dict) or set(records) != expected_datasets or not isinstance(media, dict):
        raise BackupError("The backup manifest has missing or unrecognized datasets.")
    if manifest["version"] == 1:
        records["preset_groups"] = []
    if manifest["version"] < 3:
        records["custom_sources"] = []
    if set(names) != {"manifest.json", *media}:
        raise BackupError("The attachment list does not match the files in the archive.")
    if any(not isinstance(items, list) for items in records.values()) or sum(map(len, records.values())) > RECORD_LIMIT:
        raise BackupError("The backup has invalid datasets or too many records.")
    if manifest["version"] == 3:
        for record in records["custom_sources"]:
            if not isinstance(record, dict) or "parent_id" in record:
                raise BackupError("The custom source fields do not match version 3.")
            record["parent_id"] = None
    return records, media


def _decode_records(records):
    decoded, tags = {}, {}
    for name, model in DATASETS.items():
        decoded[name] = []
        fields = _fields(model)
        expected = {field.attname for field in fields} | ({"countries"} if model is Entry else set())
        seen = set()
        for record in records[name]:
            if not isinstance(record, dict) or set(record) != expected:
                raise BackupError(f"{LABELS[name]} contain missing or unrecognized fields.")
            values = {}
            for field in fields:
                raw = record[field.attname]
                if raw is None and not field.null:
                    raise BackupError(f"{LABELS[name]} contain a missing required value.")
                if isinstance(field, models.BooleanField) and type(raw) is not bool:
                    raise BackupError(f"{LABELS[name]} contain an invalid checkbox value.")
                if isinstance(field, (models.IntegerField, models.BigIntegerField)) and raw is not None and type(raw) is not int:
                    raise BackupError(f"{LABELS[name]} contain an invalid number.")
                if not isinstance(field, (models.BooleanField, models.IntegerField, models.BigIntegerField)) and raw is not None and not isinstance(raw, str):
                    raise BackupError(f"{LABELS[name]} contain an invalid field value.")
                values[field.attname] = field.to_python(raw)
                if isinstance(field, models.DateTimeField) and values[field.attname] is not None and timezone.is_naive(values[field.attname]):
                    raise BackupError("Backup timestamps must include a timezone.")
            if model in (Entry, EntrySection) and values.get("entry_type") == "mixed":
                values["entry_type"] = "note"
            if model is NewsPreferences and type(values.get("freshness_minutes")) is int and 5 <= values["freshness_minutes"] <= 120:
                # Older backups retain their source choices with the new cadence.
                values["freshness_minutes"] = 720
            obj = model(**values)
            foreign_keys = [field.name for field in fields if isinstance(field, models.ForeignKey)]
            obj.clean_fields(exclude=foreign_keys)
            if model is not Attachment:
                obj.clean()
            if obj.pk is None and not isinstance(model._meta.pk, models.AutoField):
                raise BackupError("A backup record has no identifier.")
            if model is PresetCountry:
                key = (obj.preset_id, obj.country_id)
            elif model is PresetColorGroup:
                key = (obj.preset_id, obj.color.lower())
            else:
                key = obj.pk
            if key in seen or (model is PresetColorGroup and obj.pk in seen):
                raise BackupError(f"{LABELS[name]} contain duplicate identifiers.")
            seen.add(key)
            if model is PresetColorGroup:
                obj.color = obj.color.lower()
                seen.add(obj.pk)
            if model in (MapPersonalState, NewsPreferences) and obj.pk != 1:
                raise BackupError("Shared preferences must use their singleton identifier.")
            if model is Entry:
                codes = record["countries"]
                if not isinstance(codes, list) or any(not isinstance(code, str) for code in codes) or len(codes) != len(set(codes)):
                    raise BackupError("An entry has an invalid country list.")
                tags[obj.pk] = codes
            decoded[name].append(obj)
    return decoded, tags


def _validate_relationships(data, tags):
    countries = set(Country.objects.values_list("pk", flat=True))
    tables = {model: {obj.pk for obj in data[name]} for name, model in DATASETS.items()}
    sections = {obj.pk: obj for obj in data["sections"]}
    for name, objects in data.items():
        for obj in objects:
            for field in _fields(type(obj)):
                if not isinstance(field, models.ForeignKey):
                    continue
                value = getattr(obj, field.attname)
                if value is None and field.null:
                    continue
                valid = countries if field.related_model is Country else tables[field.related_model]
                if value not in valid:
                    raise BackupError(f"{LABELS[name]} reference a missing parent or unknown country.")
            if isinstance(obj, Attachment) and obj.section_id and sections[obj.section_id].entry_id != obj.entry_id:
                raise BackupError("An image's subsection belongs to another entry.")
            if isinstance(obj, CustomSource) and obj.parent_id:
                parent = next(item for item in data["custom_sources"] if item.pk == obj.parent_id)
                if parent.kind != CustomSource.Kind.RSS or parent.parent_id:
                    raise BackupError("Additional feeds must belong directly to an article publisher.")
    if any(code not in countries for codes in tags.values() for code in codes):
        raise BackupError("An entry references an unknown country code.")
    for name in ("collections", "presets"):
        names = [obj.name for obj in data[name]]
        if len(names) != len(set(names)):
            raise BackupError(f"{LABELS[name]} contain duplicate names.")
    profile_entries = [obj.entry_id for obj in data["country_profiles"] if obj.entry_id]
    if len(profile_entries) != len(set(profile_entries)):
        raise BackupError("One journal entry cannot be the overview for multiple countries.")
    source_urls = [obj.url for obj in data["custom_sources"]]
    if len(source_urls) != len(set(source_urls)):
        raise BackupError("Custom sources contain duplicate feed URLs.")


def _validate_media(archive, data, media):
    used = set()
    for attachment in data["attachments"]:
        path = str(attachment.file)
        if attachment.content_type not in IMAGE_TYPES:
            raise BackupError("An attachment has an unsupported image type.")
        suffix, image_format = IMAGE_TYPES[attachment.content_type]
        if path != f"media/{attachment.id.hex}{suffix}" or path not in media:
            raise BackupError("An attachment has an invalid archive path.")
        used.add(path)
        raw = archive.read(path)
        metadata = media[path]
        if not isinstance(metadata, dict) or metadata.get("sha256") != hashlib.sha256(raw).hexdigest() or len(raw) != attachment.byte_size:
            raise BackupError(f"Image {attachment.id} is damaged or has an incorrect size.")
        with Image.open(io.BytesIO(raw)) as image:
            if image.format != image_format or image.size != (attachment.width, attachment.height) or image.width * image.height > 40_000_000:
                raise BackupError(f"Image {attachment.id} does not match its metadata or is too large.")
            image.verify()
    if used != set(media):
        raise BackupError("The archive contains images with no attachment record.")


def read_backup(source):
    """Validate everything before a preview or a database write."""
    try:
        with zipfile.ZipFile(source) as archive:
            records, media = _read_archive(archive)
            data, tags = _decode_records(records)
            _validate_relationships(data, tags)
            _validate_media(archive, data, media)
        return data, tags
    except BackupError:
        raise
    except (ValidationError, ValueError, TypeError, KeyError, OSError, EOFError, zipfile.BadZipFile, RuntimeError, NotImplementedError, Image.DecompressionBombError) as error:
        raise BackupError("This backup could not be read. Check its format, fields, and image files.") from error


def import_plan(data):
    """Skip existing identities; reuse named containers without changing them."""
    plan, remap, additions = {}, {}, {}
    for name, model in DATASETS.items():
        existing = set(model.objects.values_list("pk", flat=True))
        by_name = dict(model.objects.values_list("name", "pk")) if model in (Collection, MapPreset) else {}
        by_url = dict(model.objects.values_list("url", "pk")) if model is CustomSource else {}
        colors = set(PresetCountry.objects.values_list("preset_id", "country_id")) if model is PresetCountry else set()
        claimed_profiles = set(CountryProfile.objects.exclude(entry_id=None).values_list("entry_id", flat=True)) if model is CountryProfile else set()
        plan[name] = []
        for obj in data[name]:
            action = "add"
            if model is SourcePreference and obj.source_id.startswith("custom_"):
                identity = obj.source_id.removeprefix("custom_").removesuffix("_feed")
                if re.fullmatch(r"[0-9a-f]{32}", identity):
                    target = remap.get(CustomSource, {}).get(uuid.UUID(hex=identity))
                    if target:
                        obj.source_id = f"custom_{target.hex}" + ("_feed" if obj.source_id.endswith("_feed") else "")
            if model in (Collection, MapPreset):
                target = obj.pk if obj.pk in existing else by_name.get(obj.name, obj.pk)
                remap.setdefault(model, {})[obj.pk] = target
                if target in existing:
                    action = "reuse"
            elif model is CustomSource:
                target = obj.pk if obj.pk in existing else by_url.get(obj.url, obj.pk)
                remap.setdefault(model, {})[obj.pk] = target
                if target in existing:
                    action = "reuse"
            elif obj.pk in existing:
                action = "skip"
            if model in (EntrySection, Attachment) and obj.entry_id not in additions["entries"]:
                action = "skip"
            if model is Attachment and obj.section_id and obj.section_id not in additions["sections"]:
                action = "skip"
            if model in (PresetCountry, PresetColorGroup):
                target = remap[MapPreset][obj.preset_id]
                if target not in additions["presets"] or (model is PresetCountry and (target, obj.country_id) in colors):
                    action = "skip"
            if model is CountryProfile and obj.entry_id in claimed_profiles:
                action = "skip"
            plan[name].append((obj, action))
        additions[name] = {obj.pk for obj, action in plan[name] if action == "add"}
    return plan, remap


def plan_summary(plan):
    rows = []
    for name, items in plan.items():
        counts = Counter(action for obj, action in items)
        rows.append({"label": LABELS[name], "total": len(items), "add": counts["add"], "skip": counts["skip"], "reuse": counts["reuse"]})
    return rows


def import_archive(source):
    data, tags = read_backup(source)
    saved_files = []
    try:
        with transaction.atomic(), zipfile.ZipFile(source) as archive:
            # Recompute conflicts at confirmation time, in case data changed since preview.
            plan, remap = import_plan(data)
            for name, items in plan.items():
                for obj, action in items:
                    if action != "add":
                        continue
                    for field in _fields(type(obj)):
                        if isinstance(field, models.ForeignKey) and field.related_model in remap:
                            value = getattr(obj, field.attname)
                            if value is not None:
                                setattr(obj, field.attname, remap[field.related_model][value])
                    if isinstance(obj, Attachment):
                        archive_path = str(obj.file)
                        obj.file.save(f"image{PurePosixPath(archive_path).suffix}", ContentFile(archive.read(archive_path)), save=False)
                        saved_files.append((obj.file.storage, obj.file.name))
                    dates = {field.attname: getattr(obj, field.attname) for field in _fields(type(obj)) if isinstance(field, models.DateTimeField) and (field.auto_now or field.auto_now_add)}
                    obj.save(force_insert=True)
                    # Preserve original timestamps despite Django's auto_now fields.
                    if dates:
                        type(obj).objects.filter(pk=obj.pk).update(**dates)
                    if isinstance(obj, Entry):
                        obj.countries.set(tags[obj.pk])
            return plan_summary(plan)
    except Exception:
        for storage, name in saved_files:
            try:
                storage.delete(name)
            except OSError:
                logging.getLogger(__name__).warning("A rolled-back import image could not be removed from local media.")
        raise
