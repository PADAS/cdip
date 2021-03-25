from rest_framework import permissions


class IsGlobalAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.groups.values_list('name', flat=True).filter(name='GlobalAdmin').exists()


class IsOrganizationAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.groups.values_list('name', flat=True).filter(name='OrganizationAdmin').exists()

