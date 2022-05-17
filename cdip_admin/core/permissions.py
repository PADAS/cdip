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

        # TODO: Change this to not rely on name string.
        # Consider changing this to be driven by a single custom permission that is
        # applied with Global Admin  group.
        if not request.user.groups:
            return False
        val = request.user.groups.filter(name=DjangoGroups.GLOBAL_ADMIN.value).exists()
        return val

    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view)


class IsServiceAccount(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.session and "client_id" in request.session

    def has_object_permission(self, request, view, obj):
        client_id = IsServiceAccount.get_client_id(request)
        return IsServiceAccount.is_object_owner(client_id, obj)

    @staticmethod
    def get_client_id(request):
        """
        Returns the client id if one exists in the session

        request: request to pull client_id off of
        """
        try:
            client_id = request.session["client_id"]
            return client_id
        except:
            pass

    @staticmethod
    def get_client_profile(client_id):
        """
        Returns the client profile

        client_id: key to client profile
        """
        try:
            profile = ClientProfile.objects.get(client_id=client_id)
            return profile
        except ClientProfile.DoesNotExist:
            pass

    @staticmethod
    def is_object_owner(client_id, obj):
        """
        Returns the client profile

        client_id: key to client profile
        """
        try:
            obj.__getattribute__("type")
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
        if not request.user.groups:
            return False
        return request.user.groups.filter(
            name=DjangoGroups.ORGANIZATION_MEMBER.value
        ).exists()

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return IsOrganizationMember.is_object_viewer(request.user, obj)
        else:
            return IsOrganizationMember.is_object_owner(request.user, obj)

    @staticmethod
    def get_organizations_for_user(user, admin_only):
        """
        Returns the organizations a user is mapped to

        user: user whose roles we filter against
        admin_only: specifies whether we filter the qs down to admin roles only
        """
        organizations = []
        try:
            account_profile_id = (
                AccountProfile.objects.only("id").get(user__id=user.id).id
            )
        except AccountProfile.DoesNotExist:
            return organizations
        if admin_only:
            account_organizations = AccountProfileOrganization.objects.filter(
                accountprofile_id=account_profile_id, role=RoleChoices.ADMIN.value
            )
        else:
            account_organizations = AccountProfileOrganization.objects.filter(
                accountprofile_id=account_profile_id
            )
        for account in account_organizations:
            organizations.append(account.organization.name)
        return organizations

    @staticmethod
    def filter_queryset_for_user(qs, user, name_path, admin_only=False):
        """
        Filters a queryset based on a users organization role mapping

        qs: the queryset to filter
        user: user whose roles we filter against
        name_path: the accessor path to the name property on the Organization model
        admin_only: specifies whether we filter the qs down to admin roles only
        """
        filter_string = name_path + "__in"
        organizations = IsOrganizationMember.get_organizations_for_user(
            user, admin_only
        )
        return qs.filter(**{filter_string: organizations})

    @staticmethod
    def is_object_owner(user, obj):
        """
        Determines if the passed in user has write permission on the passed in object

        user: user whose roles we filter against
        obj: object to inspect, requires "owner" property
        """
        try:
            obj.__getattribute__("owner")
        except AttributeError:
            # return true for objects that dont have owners
            return True
        organizations = IsOrganizationMember.get_organizations_for_user(
            user, admin_only=True
        )
        return organizations.__contains__(obj.owner.name)

    @staticmethod
    def is_object_viewer(user, obj):
        """
        Determines if the passed in user has read permission on the passed in object

        user: user whose roles we filter against
        obj: object to inspect, requires "owner" property
        """
        try:
            obj.__getattribute__("owner")
        except AttributeError:
            # return true for objects that dont have owners
            return True
        organizations = IsOrganizationMember.get_organizations_for_user(
            user, admin_only=False
        )
        return organizations.__contains__(obj.owner.name)
