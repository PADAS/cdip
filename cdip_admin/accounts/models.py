import uuid
from django.contrib.auth.models import User
from django.db import models, transaction
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from core.enums import RoleChoices
from core.models import UUIDAbstractModel, TimestampedModel
from organizations.models import Organization


class AccountProfileOrganization(models.Model):
    accountprofile = models.ForeignKey("AccountProfile", on_delete=models.CASCADE)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    role = models.CharField(
        max_length=200,
        choices=[(tag.value, tag.value) for tag in RoleChoices],
        default=RoleChoices.VIEWER,
    )


class AccountProfile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    user = models.OneToOneField(User, on_delete=models.CASCADE, unique=True)
    organizations = models.ManyToManyField(
        Organization, through=AccountProfileOrganization
    )
    accepted_eula = models.BooleanField(default=False)

    def __str__(self):
        return self.user.username


class UserAgreement(UUIDAbstractModel, TimestampedModel):
    user = models.ForeignKey(get_user_model(), related_name="userterms", on_delete=models.CASCADE)
    eula = models.ForeignKey("EULA", related_name="userterms", on_delete=models.CASCADE)
    date_accepted = models.DateTimeField(auto_now_add=True, verbose_name=_("Date Accepted"))
    accept = models.BooleanField(default=False)

    class Meta:
        unique_together = ("user", "eula")

    def save(self, *args, **kwargs):
        self.accept = True
        return super(UserAgreement, self).save(*args, **kwargs)


class EULAManager(models.Manager):
    def get_active_eula(self):
        return self.get_queryset().get(active=True)

    def get_users_that_have_accepted_the_latest_eula(self):
        active_eula = self.get_queryset().get(active=True)
        return active_eula.users.all()

    def get_users_that_have_not_accepted_latest_eula(self):
        accepted_users = self.get_users_that_have_accepted_the_latest_eula()
        return get_user_model().objects.exclude(id__in=[user.id for user in accepted_users])

    def accept_eula(self, user):
        active_eula = self.get_queryset().get(active=True)
        UserAgreement.objects.create(user=user, eula=active_eula, accept=True)


class EULA(UUIDAbstractModel, TimestampedModel):
    users = models.ManyToManyField(get_user_model(), through=UserAgreement, blank=True)
    version = models.CharField(max_length=30, unique=True)
    eula_url = models.URLField(null=False, blank=False)
    active = models.BooleanField(null=True, default=None)

    objects = EULAManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['active'], name='unique_active_eula'
            )
        ]

    def save(self, *args, **kwargs):
        # Check if a new EULA was Created
        if self._state.adding:
            # Ensure only the latest EULA is active
            self.active = True
            with transaction.atomic():
                EULA.objects.filter(active=True).update(active=None)
                return super(EULA, self).save(*args, **kwargs)
        else:
            return super(EULA, self).save(*args, **kwargs)

    def __str__(self):
        return self.version
