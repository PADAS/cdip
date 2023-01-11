import uuid

from django.db import models
from django.contrib.auth.models import User
from django.db.models import ManyToManyField

from core.models import TimestampedModel

from phonenumber_field.modelfields import PhoneNumberField


# Create your models here.
class Organization(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=200, verbose_name="Name", unique=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ('name',)

    @property
    def owner(self):
        return self

    def __str__(self):
        return f"{self.name}"

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("organizations_detail", kwargs={"module_id": self.pk})


class OrganizationGroup(TimestampedModel):
    name = models.CharField(max_length=200)
    organizations: ManyToManyField = models.ManyToManyField(Organization)
    description = models.TextField(blank=True)

    def __str__(self):
        return f"{self.name}"


class UserProfile(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="user_profiles",
        related_query_name="user_profile",
    )
    organizations = models.ManyToManyField(
        Organization, related_name="user_profiles", related_query_name="user_profile"
    )
    phone_number = PhoneNumberField(blank=True)

    def __str__(self):
        return f"{self.user.last_name, self.user.first_name}"
