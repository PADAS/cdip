from rest_framework import permissions
from rest_framework.permissions import SAFE_METHODS

from accounts.models import AccountProfile, AccountProfileOrganization


class IsGlobalAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.groups.values_list('name', flat=True).filter(name='GlobalAdmin').exists()


class IsOrganizationMember(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        account_profile_id = AccountProfile.objects.only('id').get(user_id=request.user.username).id
        account_organizations = AccountProfileOrganization.objects.filter(accountprofile_id=account_profile_id)
        role = account_organizations.only('role').get(organization_id=obj.id).role
        if request.method in SAFE_METHODS and role in ('admin', 'viewer'):
            return True
        elif request.method not in SAFE_METHODS and role == 'admin':
            return True
        return False

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
                                                                              role='admin')
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

