from django.db.models import Q
from django.urls import reverse

from .models import Entry


def bookmark_details(entry):
    return {
        "entry_id": str(entry.pk),
        "edit_url": reverse("journal:edit", args=[entry.pk]),
        "delete_url": reverse("journal:delete", args=[entry.pk]),
    }


def bookmark_states(videos=(), urls=()):
    videos, urls = set(videos), set(urls)
    states = {**{f"video:{value}": None for value in videos}, **{f"article:{value}": None for value in urls}}
    if not states:
        return states
    entries = Entry.objects.filter(Q(youtube_video_id__in=videos) | Q(source_url__in=urls)).only("pk", "youtube_video_id", "source_url")
    for entry in entries:
        for key in (f"video:{entry.youtube_video_id}", f"article:{entry.source_url}"):
            if key in states and states[key] is None:
                states[key] = bookmark_details(entry)
    return states
