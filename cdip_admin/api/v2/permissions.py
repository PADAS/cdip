from rest_framework import permissions
from core.enums import RoleChoices
from accounts.models import AccountProfileOrganization


def get_user_role_in_org(user_id, org_id):
    """
    Helper function to check which is the role of a user in a given org.
    return one of core.enums.RoleChoices
    """
    org_profiles = AccountProfileOrganization.objects.filter(accountprofile__user__id=user_id, organization__id=org_id)
    return org_profiles.last().role if org_profiles else None


class IsSuperuser(permissions.BasePermission):
    """
    Superusers can see everything and edit or delete anything.
    """
    def has_permission(self, request, view):
        return request.user.is_superuser

    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view)


class IsOrgAdmin(permissions.BasePermission):
    """
    Organization admin can do anything within the organizations they belong.
    But they cannot create or delete organizations
    """

    org_admin_allowed_actions = {
        "organizations": ["list", "retrieve", "update"],
        "members": ["list", "invite", "retrieve", "update", "remove"],
        "integrations": ["list", "create", "retrieve", "update", "destroy"],
        "routes": ["list", "create", "retrieve", "update", "destroy"]
    }

    def has_permission(self, request, view):
        # Check that the user is an admin in this organization
        context = request.parser_context["kwargs"]
        if view.basename == "organizations":
            org_id = context.get("pk")
        elif view.basename == "members":
            org_id = context.get("organization_pk")
        elif view.basename == "integrations":
            org_id = request.data.get("owner")
        else:  # Can't relate this user with an organization
            return False
        # Get the user role within the organization
        role = get_user_role_in_org(user_id=request.user.id, org_id=org_id)
        if role != RoleChoices.ADMIN.value:
            return False  # It's not an admin in this org

        return view.action in self.org_admin_allowed_actions.get(view.basename, [])

    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view)


class IsOrgViewer(permissions.BasePermission):
    """
    Viewers can only do read operations (list, get details, options..)
    """
    def has_permission(self, request, view):
        # Check that the user is a viewer in this organization
        context = request.parser_context["kwargs"]
        if org_id := context.get("organization_pk") or context.get("pk"):
            role = get_user_role_in_org(user_id=request.user.id, org_id=org_id)
            if role != RoleChoices.VIEWER.value:
                return False
        # Can do read only operations
        return request.method in permissions.SAFE_METHODS

    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view)
