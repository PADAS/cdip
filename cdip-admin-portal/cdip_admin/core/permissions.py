from django.core.exceptions import ObjectDoesNotExist
from rest_framework import permissions
from rest_framework.permissions import SAFE_METHODS

from accounts.models import AccountProfile, AccountProfileOrganization
from core.enums import RoleChoices, DjangoGroups
from integrations.models import InboundIntegrationConfiguration, OutboundIntegrationConfiguration
from organizations.models import Organization


class IsGlobalAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.groups.filter(name=DjangoGroups.GLOBAL_ADMIN.value).exists()

    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view)


class IsOrganizationMember(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.groups.filter(name=DjangoGroups.ORGANIZATION_MEMBER.value).exists()

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return self.is_object_viewer(request.user, obj)
        else:
            return self.is_object_owner(request.user, obj)

    '''
    Returns the organizations a user is mapped to

    user: user whose roles we filter against
    admin_only: specifies whether we filter the qs down to admin roles only
    '''
    @staticmethod
    def get_organizations_for_user(user, admin_only):
        organizations = []
        try:
            account_profile_id = AccountProfile.objects.only('id').get(user_id=user.username).id
        except AccountProfile.DoesNotExist:
            return organizations
        if admin_only:
            account_organizations = AccountProfileOrganization.objects.filter(accountprofile_id=account_profile_id,
                                                                              role=RoleChoices.ADMIN.value)
        else:
            account_organizations = AccountProfileOrganization.objects.filter(accountprofile_id=account_profile_id)
        for account in account_organizations:
            organizations.append(account.organization.name)
        return organizations

    '''
    Filters a queryset based on a users organization role mapping
    
    qs: the queryset to filter
    user: user whose roles we filter against
    name_path: the accessor path to the name property on the Organization model
    admin_only: specifies whether we filter the qs down to admin roles only
    '''
    @staticmethod
    def filter_queryset_for_user(qs, user, name_path, admin_only=False):
        filter_string = name_path + '__in'
        organizations = IsOrganizationMember.get_organizations_for_user(user, admin_only)
        return qs.filter(**{filter_string: organizations})

    '''
    Determines if the passed in user has write permission on the passed in object

    user: user whose roles we filter against
    obj: object to inspect, requires "owner" property
    '''
    @staticmethod
    def is_object_owner(user, obj):
        if not obj.__getattribute__('owner'):
            return False
        organizations = IsOrganizationMember.get_organizations_for_user(user, admin_only=True)
        return organizations.__contains__(obj.owner.name)

    '''
    Determines if the passed in user has read permission on the passed in object

    user: user whose roles we filter against
    obj: object to inspect, requires "owner" property
    '''
    @staticmethod
    def is_object_viewer(user, obj):
        if not obj.__getattribute__('owner'):
            return False
        organizations = IsOrganizationMember.get_organizations_for_user(user, admin_only=False)
        return organizations.__contains__(obj.owner.name)


