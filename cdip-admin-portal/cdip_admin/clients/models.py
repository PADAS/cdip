import uuid
from django.db import models
from integrations.models import InboundIntegrationType

from organizations.models import Organization


# Create your models here.
class ClientProfile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    client_id = models.CharField(max_length=200)
    type = models.ForeignKey(InboundIntegrationType, on_delete=models.CASCADE)
    organizations = models.ManyToManyField(Organization, blank=True)

    def __str__(self):
        return f"{self.name}"
