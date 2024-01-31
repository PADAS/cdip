from rest_framework import permissions

from activity_log.models import ActivityLog
from core.enums import RoleChoices
from accounts.models import AccountProfileOrganization
from integrations.models import Integration, Route


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
        return request.user.is_superuser if request.user else False

    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view)


def get_user_org(request, view) -> str:
    context = request.parser_context["kwargs"]
    if view.basename == "organizations":
        org_id = context.get("pk")
    elif view.basename == "members":
        org_id = context.get("organization_pk")
    elif view.basename == "integrations":
        if "owner" in request.data:  # New integration
            org_id = request.data.get("owner")
        elif integration_id := request.parser_context.get("kwargs", {}).get("pk"):  # Updating existent integration
            org_id = str(Integration.objects.get(id=integration_id).owner.id)
        else:
            org_id = None
    elif view.basename == "connections":
        integration_id = request.data.get("pk")
        org_id = str(Integration.objects.get(id=integration_id).owner.id) if integration_id else None
    elif view.basename == "sources":
        integration_id = request.data.get("provider")
        org_id = str(Integration.objects.get(id=integration_id).owner.id) if integration_id else None
    elif view.basename == "routes":
        if view.action in ["retrieve", "update", "partial_update", "destroy"]:
            route_id = context.get("pk")
            org_id = str(Route.objects.get(id=route_id).owner.id)
        elif request.data.get("owner"):
            org_id = request.data.get("owner")  # Create or Update
        else:
            org_id = None
    elif view.basename == "logs":
        log_id = context.get("pk")
        log = ActivityLog.objects.get(id=log_id)
        org_id = str(log.integration.owner.id) if log.integration else None
    else:  # Can't relate this user with an organization
        org_id = None
    return org_id


class IsOrgAdmin(permissions.BasePermission):
    """
    Organization admin can do anything within the organizations they belong.
    But they cannot create or delete organizations
    """

    org_admin_allowed_actions = {
        "organizations": ["list", "retrieve", "update", "partial_update"],
        "members": ["list", "invite", "retrieve", "update", "partial_update", "remove"],
        "integrations": ["list", "create", "retrieve", "update", "partial_update", "destroy"],
        "sources": ["list", "create", "retrieve", "update", "partial_update", "destroy"],
        "routes": ["list", "create", "retrieve", "update", "partial_update", "destroy"],
        "logs": ["list", "retrieve", "revert"]
    }

    def has_permission(self, request, view):
        # Read operations are allowed and scope is limited in the view's queryset
        if request.method in permissions.SAFE_METHODS:
            return True
        # For write operations check that the user is an admin in this organization
        org_id = get_user_org(request, view)
        if not org_id:
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
        org_id = get_user_org(request, view)
        if not org_id:
            return False
        role = get_user_role_in_org(user_id=request.user.id, org_id=org_id)
        if role != RoleChoices.VIEWER.value:
            return False
        # Can do read only operations
        return request.method in permissions.SAFE_METHODS

    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view)
