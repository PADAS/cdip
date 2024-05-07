from django.contrib import admin
from accounts.models import AccountProfile, EULA, UserAgreement


class OrganzationMemberInline(admin.TabularInline):
    model = AccountProfile.organizations.through


@admin.register(AccountProfile)
class AccountProfile(admin.ModelAdmin):

    list_display = ("username",)

    inlines = [
        OrganzationMemberInline,
    ]

    def username(self, obj):
        return obj.user.username

    username.short_description = "Username"
    search_fields = (
        "user__username",
        "organizations__name",
    )

    fieldsets = ((None, {"classes": ("wide",), "fields": (("user",))}),)


@admin.register(EULA)
class EULAAdmin(admin.ModelAdmin):
    list_display = ("version", "active", "eula_url", "created_at", )
    search_fields = (
        "version",
        "active",
    )
    list_filter = ("active", )

    def get_readonly_fields(self, request, obj=None):
        if not obj:  # New EULAs are always added as active
            return ['active']
        return []


@admin.register(UserAgreement)
class UserAgreementAdmin(admin.ModelAdmin):
    list_display = ("user", "eula", "accept", "date_accepted", )
    search_fields = (
        "user__username",
        "eula__version",
    )
    list_filter = ("accept", "eula", )
