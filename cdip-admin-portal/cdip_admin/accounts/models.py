import uuid

from django.contrib.auth.models import User
from django.db import models

from core.enums import RoleChoices
from organizations.models import Organization

class AccountProfileOrganization(models.Model):
    accountprofile = models.ForeignKey('AccountProfile', on_delete=models.CASCADE)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    role = models.CharField(max_length=200, choices=[(tag.value, tag.value) for tag in RoleChoices], default='viewer')


# Create your models here.
class AccountProfile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    user_username = models.CharField(max_length=200)
    organizations = models.ManyToManyField(Organization, through=AccountProfileOrganization)



