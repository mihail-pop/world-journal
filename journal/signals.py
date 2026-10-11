import logging

from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import Attachment


@receiver(post_delete, sender=Attachment)
def remove_attachment_file(sender, instance, **kwargs):
    if not instance.file:
        return
    storage, name = instance.file.storage, instance.file.name
    def remove():
        try:
            storage.delete(name)
        except OSError:
            logging.getLogger(__name__).warning("A deleted journal attachment could not be removed from local media.")
    transaction.on_commit(remove)
