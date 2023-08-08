from core.models import UUIDAbstractModel, TimestampedModel
from django.db import models, transaction
from model_utils import FieldTracker
from .tasks import deploy_serverless_dispatcher


class DispatcherDeployment(UUIDAbstractModel, TimestampedModel):
    class Status(models.TextChoices):
        SCHEDULED = "sch", "Deployment Scheduled"  # Value, Display
        IN_PROGRESS = "pro", "Deployment In Progress"
        ERROR = "err", "Deployment Failed"
        COMPLETE = "com", "Deployment Complete"
        DELETING = "del", "Deleting"
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.SCHEDULED
    )
    status_details = models.CharField(
        max_length=500,
        default="",
        blank=True,
        null=True
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
        on_delete=models.SET_NULL,
        related_name="dispatcher_by_outbound",
        verbose_name="Legacy Outbound Integration",
    )
    integration = models.OneToOneField(
        "integrations.Integration",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="dispatcher_by_integration",
        verbose_name="Destination Integration",
    )
    configuration = models.JSONField(
        blank=True,
        default=dict,
        verbose_name="JSON Configuration",
    )

    tracker = FieldTracker()

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.name}"

    def _pre_save(self, *args, **kwargs):
        pass

    def _post_save(self, *args, **kwargs):
        # Trigger the deployment of a dispatcher.
        # https://django-model-utils.readthedocs.io/en/latest/utilities.html#field-tracker
        config_changed = self.tracker.has_changed("configuration")
        if self.status == DispatcherDeployment.Status.SCHEDULED or config_changed:
            transaction.on_commit(
                lambda: deploy_serverless_dispatcher.delay(deployment_id=self.id)
            )

    def save(self, *args, **kwargs):
        with self.tracker:
            self._pre_save(self, *args, **kwargs)
            super().save(*args, **kwargs)
            self._post_save(self, *args, **kwargs)
