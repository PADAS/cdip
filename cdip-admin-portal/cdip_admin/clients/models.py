import uuid
from django.db import models

from core.models import TimestampedModel
from integrations.models import InboundIntegrationType, OutboundIntegrationType

from organizations.models import Organization


# Create your models here.
class ClientProfile(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    client_id = models.CharField(max_length=200)
    type = models.ForeignKey(InboundIntegrationType, on_delete=models.CASCADE)
    organizations = models.ManyToManyField(Organization, blank=True)

    def __str__(self):
        return f"{self.name}"


class ClientScope(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    scope = models.CharField(max_length=200)

    def __str__(self):
        return f"{self.scope}"


class InboundClientResource(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    type = models.ForeignKey(InboundIntegrationType, on_delete=models.CASCADE)
    resource = models.CharField(max_length=200)
    scopes = models.ManyToManyField(ClientScope)

    def __str__(self):
        return f"{self.type.name + ' - ' + self.resource}"


class OutboundClientResource(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    type = models.ForeignKey(OutboundIntegrationType, on_delete=models.CASCADE)
    resource = models.CharField(max_length=200)
    scopes = models.ManyToManyField(ClientScope)

    def __str__(self):
        return f"{self.type.name + ' - ' + self.resource}"
