import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError


@pytest.mark.django_db
def test_seed_dev_admin_creates_superuser(settings):
    settings.DEBUG = True
    call_command("seed_dev_admin")
    user = get_user_model().objects.get(email="dev@local.dev")
    assert user.username == "dev"
    assert user.is_superuser
    assert user.is_staff


@pytest.mark.django_db
def test_seed_dev_admin_is_idempotent(settings):
    settings.DEBUG = True
    call_command("seed_dev_admin")
    call_command("seed_dev_admin")
    User = get_user_model()
    assert User.objects.filter(email="dev@local.dev").count() == 1
    assert User.objects.get(email="dev@local.dev").is_superuser


@pytest.mark.django_db
def test_seed_dev_admin_elevates_existing_user(settings):
    settings.DEBUG = True
    User = get_user_model()
    User.objects.create(
        username="dev", email="dev@local.dev", is_superuser=False, is_staff=False
    )
    call_command("seed_dev_admin")
    user = User.objects.get(email="dev@local.dev")
    assert user.is_superuser
    assert user.is_staff


@pytest.mark.django_db
def test_seed_dev_admin_refuses_when_not_debug(settings):
    settings.DEBUG = False
    with pytest.raises(CommandError, match="refuses to run"):
        call_command("seed_dev_admin")
    assert not get_user_model().objects.filter(email="dev@local.dev").exists()
