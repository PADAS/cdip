from core.models import UUIDAbstractModel, TimestampedModel
from django.db import models
from .tasks import deploy_serverless_dispatcher


class DispatcherDeployment(UUIDAbstractModel, TimestampedModel):
    class Status(models.TextChoices):
        SCHEDULED = "sch", "Deployment Scheduled"  # Value, Display
        IN_PROGRESS = "pro", "Deployment In Progress"
        ERROR = "err", "Deployment Failed"
        COMPLETE = "com", "Deployment Complete"
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.SCHEDULED
    )
    name = models.CharField(
        max_length=63,
        blank=True,
        null=True
    )
    legacy_integration = models.OneToOneField(
        "integrations.OutboundIntegrationConfiguration",
        blank=True,
        null=True,
        on_delete=models.PROTECT,
        related_name="dispatcher_by_outbound",
        verbose_name="Destination Integration",
    )
    integration = models.OneToOneField(
        "integrations.Integration",
        blank=True,
        null=True,
        on_delete=models.PROTECT,
        related_name="dispatcher_by_integration",
        verbose_name="Destination Integration",
    )
    configuration = models.JSONField(
        blank=True,
        default=dict,
        verbose_name="JSON Configuration",
    )

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.name}"

    def _pre_save(self, *args, **kwargs):
        pass

    def _post_save(self, *args, **kwargs):
        # Trigger the deployment of a dispatcher
        if self.status == DispatcherDeployment.Status.SCHEDULED:
            deploy_serverless_dispatcher.delay(deployment_id=self.id, model_version="v2")

    def save(self, *args, **kwargs):
        self._pre_save(self, *args, **kwargs)
        super().save(*args, **kwargs)
        self._post_save(self, *args, **kwargs)
