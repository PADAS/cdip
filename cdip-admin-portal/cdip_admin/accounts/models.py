import uuid
from django.db import models

from organizations.models import Organization


class AccountProfileOrganization(models.Model):
    accountprofile = models.ForeignKey('AccountProfile', on_delete=models.CASCADE)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    role = models.CharField(max_length=200, default='viewer')


# Create your models here.
class AccountProfile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    user_id = models.CharField(max_length=200)
    organizations = models.ManyToManyField(Organization, through=AccountProfileOrganization)



