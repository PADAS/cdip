import logging
from crum import get_current_user
from .models import ActivityLog
from .core import ActivityActions

logger = logging.getLogger(__name__)


class ChangeLogMixin:
    activity_excluded_fields = ["created_at", "updated_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:  # Error logging activity shouldn't affect the usage of the model
            self._original_values = self._get_original_values()
            self._original_integration = self._get_related_integration()
        except Exception as e:
            logger.warning(f"Activity Log > Initialization Error: '{e}'.")
            self._original_values = {}
            self._original_integration = None

    def _get_fields(self):
        return self._meta.fields

    def _get_original_values(self):
        original_values = {}
        for field in self._get_fields():
            field_name = field.attname
            if field_name not in self.activity_excluded_fields:
                value = str(getattr(self, field.attname))
                original_values[field.attname] = value
        return original_values

    def get_changes(self, original_values):
        changes = {}
        for field in self._get_fields():
            field_name = field.attname
            if field_name not in self.activity_excluded_fields:
                value = str(getattr(self, field.attname))
                if value != original_values.get(field_name):
                    changes[field_name] = value
        return changes

    def log_activity(self, integration, action, changes, is_reversible, revert_data=None, user=None):
        model_name = self.__class__.__name__
        value = f"{model_name.lower()}_{action.lower()}"
        title = f"{model_name} {action} by {user}"
        ActivityLog.objects.create(
            log_level=ActivityLog.LogLevels.INFO,
            log_type=ActivityLog.LogTypes.DATA_CHANGE,
            origin=ActivityLog.Origin.PORTAL,
            integration=integration,
            value=value,
            title=title,
            created_by=user,
            details={
                "model_name": model_name,
                "instance_pk": str(self.pk),
                "action": action,
                "changes": changes
            },
            is_reversible=is_reversible,
            revert_data=revert_data or {}
        )

    def save(self, *args, **kwargs):
        created = self._state.adding
        super().save(*args, **kwargs)
        try:  # Error logging activity shouldn't affect the operation
            action = ActivityActions.CREATED.value if created else ActivityActions.UPDATED.value
            changes = self.get_changes(original_values=self._original_values)
            if changes:
                self.log_activity(
                    integration=self._original_integration or self._get_related_integration(),
                    action=action,
                    changes=changes,
                    is_reversible=True,
                    revert_data=self.get_revert_data(action=action, fields=changes.keys()),
                    user=self.get_user()
                )
        except Exception as e:
            logger.warning(f"Activity Log > Error recording activity for {self}: '{e}'.")

    def delete(self, *args, **kwargs):
        try:  # Error logging activity shouldn't affect the operation
            self.log_activity(
                integration=self._get_related_integration(),
                action=ActivityActions.DELETED.value,
                changes=self._original_values,
                is_reversible=False,
                user=self.get_user()
            )
        except Exception as e:
            logger.warning(f"Activity Log > Error recording activity for {self}: '{e}'.")
        super().delete(*args, **kwargs)

    def _get_related_integration(self):
        from integrations.models import Integration
        integration = None
        # Look for an attribute specifying the integration field
        if hasattr(self, "integration_field"):
            integration_field = self.integration_field.lower().strip()
        elif hasattr(self, "integration"):
            integration_field = "integration"
        else:
            integration_field = ""
        try:  # Try to get the related integration
            fields = integration_field.split("__") if integration_field else []
            integration = self
            while fields:  # Follow relationships
                field = fields.pop(0)
                integration = getattr(integration, field)
        except Exception as e:
            # ToDo: log error
            logger.warning(f"Activity Log > ERROR resolving integration for {self}: {e}")
            pass
        # Safeguard in case the integration field isn't set properly
        if not isinstance(integration, Integration):
            logger.warning(f"Activity Log: '{integration}' isn't an instance of Integration. Integration left empty.")
            integration = None
        return integration

    def get_user(self):
        return get_current_user()

    def get_revert_data(self, action, fields):
        if action == ActivityActions.CREATED.value:
            return {
                'model_name': self.__class__.__name__,
                'instance_pk': str(self.pk),
            }
        elif action == ActivityActions.UPDATED.value:
            return {
                'model_name': self.__class__.__name__,
                'instance_pk': str(self.pk),
                'original_values': {
                    field: self._original_values[field]
                    for field in fields
                },
            }
        else:
            logger.warning(f"Activity Log: Error resolving revert_data for {self}. Unknown action {action}.")
            return {}
