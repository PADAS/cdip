from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

DEV_EMAIL = "dev@local.dev"      # matches the cdip-dev Keycloak realm user
DEV_USERNAME = "dev"             # matches the realm 'username' claim


class Command(BaseCommand):
    help = "Seed the local 'dev' Keycloak user as a Django superuser (local dev only)."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                "seed_dev_admin refuses to run when DEBUG is False (local dev only)."
            )
        User = get_user_model()
        user, created = User.objects.get_or_create(
            email=DEV_EMAIL, defaults={"username": DEV_USERNAME}
        )
        if not (user.is_superuser and user.is_staff):
            user.is_superuser = True
            user.is_staff = True
            user.save(update_fields=["is_superuser", "is_staff"])
        self.stdout.write(
            self.style.SUCCESS(
                f"dev admin ready: {user.username} <{user.email}> (created={created})"
            )
        )
