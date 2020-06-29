from django.contrib import admin
from organizations.models import Organization, OrganizationGroup, UserProfile

# Register your models here.
admin.site.register(Organization)
admin.site.register(OrganizationGroup)
admin.site.register(UserProfile)
