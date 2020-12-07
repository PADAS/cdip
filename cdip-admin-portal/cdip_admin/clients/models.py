import uuid
from django.db import models

from core.models import TimestampedModel
from integrations.models import InboundIntegrationType, OutboundIntegrationType

from organizations.models import Organization


# Create your models here.
class ClientProfile(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    client_id = models.CharField(max_length=200, unique=True)
    type = models.ForeignKey(InboundIntegrationType, on_delete=models.CASCADE)
    organizations = models.ManyToManyField(Organization, blank=True)

    def __str__(self):
        return f"{self.client_id}"


class AuthorizationScope(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    scope = models.CharField(max_length=200)

    def __str__(self):
        return f"{self.scope}"


class ClientAudienceScope(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    scope = models.CharField(max_length=200)

    def __str__(self):
        return f"{self.scope}"


class InboundClientResource(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    type = models.ForeignKey(InboundIntegrationType, on_delete=models.CASCADE)
    resource = models.CharField(max_length=200)
    scopes = models.ManyToManyField(AuthorizationScope)

    def __str__(self):
        return f"{self.type.name + ' - ' + self.resource}"


class InboundClientScope(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    type = models.ForeignKey(InboundIntegrationType, on_delete=models.CASCADE)
    inbound_client_scope = models.ForeignKey(ClientAudienceScope, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.type.name + ' - ' + self.inbound_client_scope.scope}"


class OutboundClientResource(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    type = models.ForeignKey(OutboundIntegrationType, on_delete=models.CASCADE)
    resource = models.CharField(max_length=200)
    scopes = models.ManyToManyField(AuthorizationScope)

    def __str__(self):
        return f"{self.type.name + ' - ' + self.resource}"


class OutboundClientScope(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    type = models.ForeignKey(InboundIntegrationType, on_delete=models.CASCADE)
    outbound_client_scope = models.ForeignKey(ClientAudienceScope, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.type.name + ' - ' + self.outbound_client_scope.scope}"
