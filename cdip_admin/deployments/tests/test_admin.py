import pytest
from django.contrib import admin as django_admin
from django.contrib.admin.widgets import AutocompleteSelect

from deployments.admin import DispatcherDeploymentForm
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


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("", {}),  # emptied editor -> {} (column is NOT NULL, default=dict)
        ("[]", []),  # falsy but valid JSON must be preserved as-is
        ("0", 0),
        ("false", False),
        ('{"a": 1}', {"a": 1}),
    ],
)
def test_configuration_cleaning_preserves_falsy_json(raw, expected):
    form = DispatcherDeploymentForm(data={"configuration": raw})
    form.is_valid()
    assert "configuration" not in form.errors
    assert form.cleaned_data["configuration"] == expected
