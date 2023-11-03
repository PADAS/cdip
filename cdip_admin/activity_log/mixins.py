from django.db import models
from .models import ActivityLog


class ChangeLogMixin:
    reversible_actions = ["created", "updated"]
    exclude_fields = ["created_at", "updated_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_values = self._get_original_values()

    def _get_original_values(self):
        original_values = {}
        for field in self._meta.fields:
            field_name = field.attname
            if field_name not in self.exclude_fields:
                original_values[field.attname] = str(getattr(self, field.attname))
        return original_values

    def get_changes(self, original_values):
        changes = {}
        for field in self._meta.fields:
            field_name = field.attname
            if field_name not in self.exclude_fields and str(getattr(self, field_name)) != original_values.get(field_name):
                changes[field_name] = str(getattr(self, field_name))
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
        self.log_activity(
            integration=self.get_integration(),
            action=action,
            changes=changes,
            is_reversible=True,
            revert_data=self.get_revert_data(action=action, fields=changes.keys()),
            user=self.get_user()
        )

    def delete(self, *args, **kwargs):
        action = "deleted"
        self.log_activity(
            integration=self.get_integration(),
            action=action,
            changes=self._original_values,
            is_reversible=False,
            user=self.get_user()
        )
        super().delete(*args, **kwargs)

    def get_integration(self):
        # ToDo: Solve how to get this in a generic way
        # Some changes are related to more than one. i.e. Editing a Route.
        # Not every change is related to an integration. Do we log only the ones that are?
        return None

    def get_user(self):
        # ToDo: Solve how to get this in a generic way
        # Check django-crum
        # https://github.com/ninemoreminutes/django-crum/
        return None

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
