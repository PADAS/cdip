import uuid
from django.contrib.auth.models import User
from django.db import models
from core.enums import RoleChoices
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

    def __str__(self):
        return self.user.username
