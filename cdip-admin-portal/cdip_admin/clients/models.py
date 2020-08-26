import uuid
from django.db import models
from integrations.models import InboundIntegrationType


# Create your models here.
class ClientProfile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=200)
    client_id = models.CharField(max_length=200)
    type = models.ForeignKey(InboundIntegrationType, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.name}"
