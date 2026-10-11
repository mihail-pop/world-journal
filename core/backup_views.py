import json
import logging
import re
import time
import uuid
from pathlib import Path

from django import forms
from django.conf import settings
from django.contrib import messages
from django.db import DatabaseError
from django.http import FileResponse, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from .backups import BackupError, export_archive, import_archive, import_plan, plan_summary, read_backup
from .views import render_page


TOKEN = re.compile(r"[0-9a-f]{32}\Z")
PREVIEW_TTL = 24 * 60 * 60


class UploadBackupForm(forms.Form):
    archive = forms.FileField(label="World Journal backup ZIP", widget=forms.FileInput(attrs={"accept": ".zip,application/zip"}))

    def clean_archive(self):
        archive = self.cleaned_data["archive"]
        if archive.size > settings.BACKUP_MAX_BYTES:
            raise forms.ValidationError(f"Choose a backup no larger than {settings.BACKUP_MAX_BYTES // (1024 * 1024)} MB.")
        return archive


class ConfirmImportForm(forms.Form):
    token = forms.RegexField(regex=TOKEN, widget=forms.HiddenInput())
    confirm = forms.BooleanField(label="Import the new records shown above, keeping existing content.")


def _staging_directory():
    # Private staging lives outside media so uploaded backups cannot be served.
    directory = Path(settings.BACKUP_STAGING_ROOT)
    directory.mkdir(parents=True, exist_ok=True)
    for path in directory.glob("*.zip"):
        try:
            if TOKEN.fullmatch(path.stem) and path.is_file() and path.stat().st_mtime < time.time() - PREVIEW_TTL:
                path.unlink(missing_ok=True)
        except FileNotFoundError:
            pass
    return directory


def _preview_path(request):
    token = request.session.get("backup_preview_token", "")
    if not isinstance(token, str) or not TOKEN.fullmatch(token):
        return None
    path = _staging_directory() / f"{token}.zip"
    if not path.is_file():
        request.session.pop("backup_preview_token", None)
        return None
    return path


def _discard(request):
    path = _preview_path(request)
    if path:
        path.unlink(missing_ok=True)
    request.session.pop("backup_preview_token", None)


def _navigate(request):
    url = reverse("core:backups")
    if request.headers.get("HX-Request") == "true":
        response = HttpResponse()
        response.headers["HX-Location"] = json.dumps({"path": url, "target": "#app-content", "swap": "innerHTML show:top"})
        return response
    return redirect(url)


@never_cache
@require_http_methods(["GET", "POST"])
def backups(request):
    upload = UploadBackupForm()
    confirmation = ConfirmImportForm()
    summary = None
    page_error = ""
    path = _preview_path(request)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "cancel":
            _discard(request)
            messages.info(request, "Import preview discarded. No data was imported.")
            return _navigate(request)
        if action == "preview":
            upload = UploadBackupForm(request.POST, request.FILES)
            if upload.is_valid():
                _discard(request)
                token = uuid.uuid4().hex
                path = _staging_directory() / f"{token}.zip"
                try:
                    with path.open("xb") as destination:
                        for chunk in upload.cleaned_data["archive"].chunks():
                            destination.write(chunk)
                    data, _tags = read_backup(path)
                    summary = plan_summary(import_plan(data)[0])
                    request.session["backup_preview_token"] = token
                    confirmation = ConfirmImportForm(initial={"token": token})
                except (BackupError, OSError) as error:
                    path.unlink(missing_ok=True)
                    upload.add_error("archive", str(error) if isinstance(error, BackupError) else "The backup could not be staged on disk. Check available space and folder access.")
                    path = None
        elif action == "confirm":
            confirmation = ConfirmImportForm(request.POST)
            valid = confirmation.is_valid()
            if path is None:
                confirmation.add_error(None, "This preview expired. Upload the backup again.")
            elif valid:
                if confirmation.cleaned_data["token"] != request.session.get("backup_preview_token"):
                    confirmation.add_error(None, "This preview expired. Upload the backup again.")
                else:
                    try:
                        results = import_archive(path)
                    except (BackupError, DatabaseError, OSError) as error:
                        message = str(error) if isinstance(error, BackupError) else "Import could not finish. Database changes were rolled back. Check available space and try again."
                        confirmation.add_error(None, message)
                        logging.getLogger(__name__).warning("A backup import was rejected or rolled back (%s).", type(error).__name__)
                    else:
                        _discard(request)
                        messages.success(request, f"Import complete: {sum(row['add'] for row in results)} records added; {sum(row['skip'] + row['reuse'] for row in results)} existing or conflicting records kept.")
                        return _navigate(request)
        else:
            page_error = "Choose Preview or Confirm import."
    if path and summary is None:
        try:
            data, _tags = read_backup(path)
            summary = plan_summary(import_plan(data)[0])
            if not confirmation.is_bound:
                confirmation = ConfirmImportForm(initial={"token": request.session["backup_preview_token"]})
        except BackupError as error:
            _discard(request)
            page_error = str(error)
    return render_page(request, "settings", page_template="core/backups.html", context={
        "upload_form": upload, "confirmation_form": confirmation, "summary": summary,
        "backup_limit_mb": settings.BACKUP_MAX_BYTES // (1024 * 1024),
        "page_error": page_error,
    })


@never_cache
@require_http_methods(["GET"])
def export_backup(request):
    try:
        archive = export_archive()
    except (BackupError, OSError, DatabaseError) as error:
        messages.error(request, str(error) if isinstance(error, BackupError) else "Backup could not be created. Check disk space and local file access.")
        return redirect("core:backups")
    filename = f"world-journal-{timezone.now():%Y%m%d-%H%M%S}.zip"
    return FileResponse(archive, as_attachment=True, filename=filename, content_type="application/zip")
