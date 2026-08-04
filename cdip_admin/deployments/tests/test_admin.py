from django.contrib import admin as django_admin
from django.contrib.admin.widgets import AutocompleteSelect

from deployments.models import DispatcherDeployment


def test_change_form_uses_autocomplete_for_integration_fks():
    """The change form must not render plain selects for the integration FKs.

    A plain select loads every Integration/OutboundIntegrationConfiguration
    and calls __str__ on each (which dereferences owner and type without
    select_related), making the page unusably slow in production.
    """
    model_admin = django_admin.site._registry[DispatcherDeployment]
    for field_name in ("integration", "legacy_integration"):
        formfield = model_admin.formfield_for_foreignkey(
            DispatcherDeployment._meta.get_field(field_name), request=None
        )
        assert isinstance(formfield.widget, AutocompleteSelect)
