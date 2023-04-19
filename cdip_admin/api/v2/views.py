import django_filters
from django.db.models import Subquery
from integrations.models import OutboundIntegrationConfiguration, OutboundIntegrationType, DeviceGroup, \
    InboundIntegrationConfiguration
from accounts.models import AccountProfile, AccountProfileOrganization
from accounts.utils import remove_members_from_organization, get_user_organizations_qs
from emails.tasks import send_invite_email_task
from rest_framework import viewsets, status, filters, mixins
from rest_framework.decorators import action
from rest_framework.response import Response
from . import serializers as v2_serializers
from . import permissions


class OrganizationView(viewsets.ModelViewSet):
    """
    An endpoint for managing organizations
    """
    permission_classes = [permissions.IsSuperuser | permissions.IsOrgAdmin | permissions.IsOrgViewer]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['id', 'name']
    ordering = ['id']

    def get_serializer_class(self):
        return v2_serializers.OrganizationSerializer

    def get_queryset(self):
        """
        Return a list with the organizations that the currently authenticated user is allowed to see.
        """
        return get_user_organizations_qs(user=self.request.user)


class MemberViewSet(viewsets.ModelViewSet):
    """
    An endpoint for managing organization members
    """
    permission_classes = [permissions.IsSuperuser | permissions.IsOrgAdmin | permissions.IsOrgViewer]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['id']
    ordering = ['id']

    def get_serializer_class(self):
        if self.action == "invite":
            return v2_serializers.InviteUserSerializer
        if self.action == "remove":
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
        # Validations
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )
        # Add or create user
        user, created = serializer.save()
        send_invite_email_task.delay(
            user_id=user.id,
            org_id=organization_pk,
            is_new_user=created
        )
        return Response({'status': 'User invited successfully'})

    @action(detail=False, methods=['post', 'put', 'patch'], url_path="remove")
    def remove(self, request, organization_pk=None):
        """
        Invite members to an Organization
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # Remove members from organization
        removed_qty = remove_members_from_organization(org_id=organization_pk, profile_ids=serializer.validated_data["member_ids"])
        return Response(data={"removed": removed_qty}, status=status.HTTP_200_OK)


class DestinationView(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet
):
    """
    An endpoint for managing destinations
    """
    permission_classes = [permissions.IsSuperuser | permissions.IsOrgAdmin | permissions.IsOrgViewer]
    filter_backends = [filters.OrderingFilter, django_filters.rest_framework.DjangoFilterBackend]
    ordering_fields = ['id', 'name']
    ordering = ['id']
    filterset_fields = {
        'endpoint': ['exact', 'iexact', 'in'],
        'enabled': ['exact', 'in'],
        'type': ['exact', 'in'],
        'owner': ['exact', 'in']
    }

    def get_serializer_class(self):
        if self.action == "list":
            return v2_serializers.DestinationRetrieveSerializer
        if self.action == "create":
            return v2_serializers.DestinationCreateSerializer

    def get_queryset(self):
        """
        Return a list with the destinations that the currently authenticated user is allowed to see.
        """
        user_organizations = get_user_organizations_qs(user=self.request.user)
        destinations = OutboundIntegrationConfiguration.objects.filter(
            owner__in=Subquery(user_organizations.values('id'))
        )
        return destinations


class DestinationTypeView(
    mixins.ListModelMixin,
    viewsets.GenericViewSet
):
    """
    An endpoint for managing destination types
    """
    permission_classes = [permissions.IsSuperuser | permissions.IsOrgAdmin | permissions.IsOrgViewer]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['id', 'name']
    ordering = ['id']
    queryset = OutboundIntegrationType.objects.all()

    def get_serializer_class(self):
        return v2_serializers.DestinationTypeRetrieveSerializer


class ConnectionsView(
    mixins.ListModelMixin,
    viewsets.GenericViewSet
):
    """
    An endpoint for managing destination types
    """
    permission_classes = [permissions.IsSuperuser | permissions.IsOrgAdmin | permissions.IsOrgViewer]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['id', 'name']
    ordering = ['id']

    def get_queryset(self):
        """
        Return a list of sources used to get the connections
        """
        user_organizations = get_user_organizations_qs(user=self.request.user)
        sources = InboundIntegrationConfiguration.objects.filter(
            owner__in=Subquery(user_organizations.values('id'))
        )
        return sources

    def get_serializer_class(self):
        return v2_serializers.ConnectionRetrieveSerializer
