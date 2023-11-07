from crum import get_current_user
from .models import ActivityLog



class ChangeLogMixin:
    reversible_actions = ["created", "updated"]
    exclude_fields = ["created_at", "updated_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_values = self._get_original_values()
        self._original_integration = self._get_related_integration()

    def _get_fields(self):
        return self._meta.fields

    def _get_original_values(self):
        original_values = {}
        for field in self._get_fields():
            field_name = field.attname
            if field_name not in self.exclude_fields:
                value = str(getattr(self, field.attname))
                original_values[field.attname] = value
        return original_values

    def get_changes(self, original_values):
        changes = {}
        for field in self._get_fields():
            field_name = field.attname
            if field_name not in self.exclude_fields:
                value = str(getattr(self, field.attname))
                if value != original_values.get(field_name):
                    changes[field_name] = value
        return changes

    def log_activity(self, integration, action, changes, is_reversible, revert_data=None, user=None):
        model_name = self.__class__.__name__
        value = f"{model_name.lower()}_{action}"
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
        action = "created" if created else "updated"
        changes = self.get_changes(original_values=self._original_values)
        if changes:
            self.log_activity(
                integration=self._original_integration,
                action=action,
                changes=changes,
                is_reversible=True,
                revert_data=self.get_revert_data(action=action, fields=changes.keys()),
                user=self.get_user()
            )

    def delete(self, *args, **kwargs):
        action = "deleted"
        self.log_activity(
            integration=self._get_related_integration(),
            action=action,
            changes=self._original_values,
            is_reversible=False,
            user=self.get_user()
        )
        super().delete(*args, **kwargs)

    def _get_related_integration(self):
        from integrations.models import Integration
        integration = None
        # Look for an attribute specifying the integration field
        if hasattr(self, "integration_field"):
            integration_field = self.integration_field
        elif hasattr(self, "integration"):
            integration_field = "integration"
        else:
            integration_field = ""
        try:  # Try to get the related integration
            fields = integration_field.lower().strip().split("__")
            integration = self
            while fields:  # Follow relationships
                field = fields.pop(0)
                integration = getattr(integration, field)
        except Exception as e:
            # ToDo: log error
            print(f"ERROR getting integration for Activity Log {e}")
            pass
        # Safeguard in case the integration field isn't set properly
        if not isinstance(integration, Integration):
            print(f"Warning: integration retrieved for Activity Log isn't an instance of Integration")
            integration = None
        return integration

    def get_user(self):
        return get_current_user()

    def get_revert_data(self, action, fields):
        if action == 'created':
            return {
                'model_name': self.__class__.__name__,
                'instance_pk': str(self.pk),
            }
        elif action == 'updated':
            return {
                'model_name': self.__class__.__name__,
                'instance_pk': str(self.pk),
                'original_values': {
                    field: self._original_values[field]
                    for field in fields
                },
            }
        else:
            return {}


