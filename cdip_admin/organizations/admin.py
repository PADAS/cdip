from django.contrib import admin

from accounts.models import AccountProfile
from organizations.models import Organization


class OrganzationMemberInline(admin.TabularInline):

    model = AccountProfile.organizations.through

    fields = ('accountprofile',
              'role',)


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    inlines = [
        OrganzationMemberInline,
    ]

    fields = ('name', 'description',)

