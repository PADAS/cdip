import uuid
from django.db import models


# Create your models here.
class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    def light_save(self, *args, **kwargs):
        super().save(*args, **kwargs)


class Task(models.Model):
    class Meta:
        permissions = [
            ("admin", "Admin Role"),
            ("viewer", "Viewer Role"),
        ]


class UUIDAbstractModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True
