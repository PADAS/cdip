import uuid
from django.db import models

from organizations.models import Organization


# Create your models here.
class AccountProfile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    user_id = models.CharField(max_length=200)
    organizations = models.ManyToManyField(Organization)

    def __str__(self):
        return f"{self.user.last_name, self.user.first_name}"
