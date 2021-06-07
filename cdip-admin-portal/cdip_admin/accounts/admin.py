from django.contrib import admin
from accounts.models import AccountProfile


class OrganzationMemberInline(admin.TabularInline):
    model = AccountProfile.organizations.through

@admin.register(AccountProfile)
class AccountProfile(admin.ModelAdmin):

    list_display = ('username',)

    inlines = [
        OrganzationMemberInline,
    ]

    def username(self, obj):
        return obj.user.username
    username.short_description = 'Username'
    search_fields = ('user__username', 'organizations__name',)

    fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (('user',))
        }
        ),

    )
