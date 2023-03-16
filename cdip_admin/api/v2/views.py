import logging
from organizations.models import Organization
from accounts.models import AccountProfile, AccountProfileOrganization
from accounts.utils import remove_members_from_organization
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework import mixins
from rest_framework.viewsets import GenericViewSet
from rest_framework.response import Response
from . import serializers as v2_serializers


class OrganizationView(viewsets.ModelViewSet):
    """
    A viewset for managing organizations and it's members
    """

    def get_serializer_class(self):
        return v2_serializers.OrganizationSerializer

    def get_queryset(self):
        """
        Return a list with the organizations that the currently authenticated user is allowed to see.
        """
        user = self.request.user
        # Superusers can see all the organizations
        if user.is_superuser:
            return Organization.objects.all()
        # Members can only see the organizations they belong too
        try:
            profile = user.accountprofile
        except AccountProfile.DoesNotExist as e:
            return Organization.objects.none()
        return user.accountprofile.organizations.all()


class MemberViewSet(viewsets.ModelViewSet):
    # ToDo: validate Permissions?
    def get_serializer_class(self):
        if self.action == "invite":
            return v2_serializers.InviteUserSerializer
        if self.action == "remove_members":
            return v2_serializers.RemoveMemberSerializer
        if self.action == "update":
            return v2_serializers.OrganizationMemberUpdateSerializer
        return v2_serializers.OrganizationMemberRetrieveSerializer

    def get_queryset(self):
        return AccountProfileOrganization.objects.filter(organization=self.kwargs['organization_pk'])

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        if getattr(instance, '_prefetched_objects_cache', None):
            # If 'prefetch_related' has been applied to a queryset, we need to
            # forcibly invalidate the prefetch cache on the instance.
            instance._prefetched_objects_cache = {}
        # Return the data which was updated
        return Response(serializer.validated_data)

    @action(detail=False, methods=['post', 'put'])
    def invite(self, request, organization_pk=None):
        """
        Invite members to an Organization
        """
        # ToDo: Check permissions
        # Only superusers or org admins can invite members
        # Validations
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )
        # Create user
        self.perform_create(serializer)
        # ToDo: Analyze new cases when we want to send emails
        # Consider using some third-party email service
        return Response({'status': 'User invited successfully'})

    @action(detail=False, methods=['post', 'put', 'patch'], url_path="remove-members")
    def remove(self, request, organization_pk=None):
        requester = self.request.user
        # ToDo: validate Permissions?
        serializer = self.get_serializer(
            data=request.data
        )
        serializer.is_valid(raise_exception=True)
        # Remove members from organization
        removed_qty = remove_members_from_organization(org_id=organization_pk, profile_ids=serializer.validated_data["member_ids"])
        return Response(data={"removed": removed_qty}, status=status.HTTP_200_OK)
