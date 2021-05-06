from django.core.exceptions import ObjectDoesNotExist
from rest_framework import permissions
from rest_framework.permissions import SAFE_METHODS

from accounts.models import AccountProfile, AccountProfileOrganization
from clients.models import ClientProfile
from core.enums import RoleChoices, DjangoGroups

import logging
logger = logging.getLogger(__name__)


class IsGlobalAdmin(permissions.BasePermission):
    def has_permission(self, request, view):

        val = request.user.groups.filter(name=DjangoGroups.GLOBAL_ADMIN.value).exists()

        if logger.isEnabledFor(logging.DEBUG):
            group_names = ','.join([group.name for group in request.user.groups.all()])
            logger.debug('IsGlobalAdmin=%s checked for user.username: %s, groups: %s', val, request.user, group_names)

        return val

    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view)


class IsServiceAccount(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.session and 'client_id' in request.session

    def has_object_permission(self, request, view, obj):
        client_id = IsServiceAccount.get_client_id(request)
        return IsServiceAccount.is_object_owner(client_id, obj)

    '''
    Returns the client id if one exists in the session

    request: request to pull client_id off of
    '''
    @staticmethod
    def get_client_id(request):
        try:
            client_id = request.session['client_id']
            return client_id
        except:
            pass

    '''
    Returns the client profile

    client_id: key to client profile
    '''
    @staticmethod
    def get_client_profile(client_id):
        try:
            profile = ClientProfile.objects.get(client_id=client_id)
            return profile
        except ClientProfile.DoesNotExist:
            pass

    '''
    Returns the client profile

    client_id: key to client profile
    '''
    @staticmethod
    def is_object_owner(client_id, obj):
        try:
            obj.__getattribute__('type')
        except AttributeError:
            # can only determine client permissions on objects that have integration types
            return False
        client_profile = IsServiceAccount.get_client_profile(client_id)
        if client_profile:
            return client_profile.type_id == obj.type.id
        else:
            return False


class IsOrganizationMember(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.groups.filter(name=DjangoGroups.ORGANIZATION_MEMBER.value).exists()

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return IsOrganizationMember.is_object_viewer(request.user, obj)
        else:
            return IsOrganizationMember.is_object_owner(request.user, obj)

    '''
    Returns the organizations a user is mapped to

    user: user whose roles we filter against
    admin_only: specifies whether we filter the qs down to admin roles only
    '''
    @staticmethod
    def get_organizations_for_user(user, admin_only):
        organizations = []
        try:
            account_profile_id = AccountProfile.objects.only('id').get(user__id=user.id).id
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
        try:
            obj.__getattribute__('owner')
        except AttributeError:
            # return true for objects that dont have owners
            return True
        organizations = IsOrganizationMember.get_organizations_for_user(user, admin_only=True)
        return organizations.__contains__(obj.owner.name)

    '''
    Determines if the passed in user has read permission on the passed in object

    user: user whose roles we filter against
    obj: object to inspect, requires "owner" property
    '''
    @staticmethod
    def is_object_viewer(user, obj):
        try:
            obj.__getattribute__('owner')
        except AttributeError:
            # return true for objects that dont have owners
            return True
        organizations = IsOrganizationMember.get_organizations_for_user(user, admin_only=False)
        return organizations.__contains__(obj.owner.name)


