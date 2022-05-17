from django.db import models


# Create your models here.
class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Task(models.Model):
    class Meta:
        permissions = [
            ("admin", "Admin Role"),
            ("viewer", "Viewer Role"),
        ]
