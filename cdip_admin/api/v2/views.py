import django_filters
from django.db.models import Subquery
from rest_framework.permissions import IsAuthenticated

from activity_log.models import ActivityLog
from integrations.models import Route, get_user_integrations_qs, get_integrations_owners_qs, get_user_sources_qs, \
    get_user_routes_qs, GundiTrace, IntegrationAction
from integrations.models import IntegrationType, Integration
from integrations.filters import IntegrationFilter, ConnectionFilter, IntegrationTypeFilter, SourceFilter, RouteFilter, \
    GundiTraceFilter, ActivityLogFilter
from accounts.models import AccountProfileOrganization, EULA
from accounts.utils import remove_members_from_organization, get_user_organizations_qs
from emails.tasks import send_invite_email_task
from rest_framework import viewsets, status, mixins, generics
from rest_framework import filters as drf_filters
from rest_framework import exceptions as drf_exceptions
from rest_framework.decorators import action
from rest_framework.response import Response
from gundi_core.schemas.v2 import StreamPrefixEnum
from . import serializers as v2_serializers
from . import permissions
from . import filters as custom_filters


class UsersView(
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet
):
    """
    An endpoint for retrieving the details of the logged-in user
    """
    serializer_class = v2_serializers.UserDetailsRetrieveSerializer

    def get_object(self):
        return self.request.user


class EULAView(
    mixins.ListModelMixin,
    viewsets.GenericViewSet
):
    """
    An endpoint for retrieving and accepting EULA
    """
    # Authenticated users only
    permission_classes = [IsAuthenticated]
    queryset = EULA.objects.all()

    def get_serializer_class(self):
        if self.action == "accept":
            return v2_serializers.UserAgreementSerializer
        return v2_serializers.EULARetrieveSerializer

    def get_object(self):
        return EULA.objects.get_active_eula()

    # Overriden to return a single object (the active eula)
    def list(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
        except EULA.DoesNotExist:  # No active EULA
            return Response(status=status.HTTP_404_NOT_FOUND)
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    @action(detail=False, methods=["post", "put"])
    def accept(self, request):
        # Create a UserAgreement
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)


class OrganizationView(viewsets.ModelViewSet):
    """
    An endpoint for managing organizations
    """
    permission_classes = [permissions.IsSuperuser | permissions.IsOrgAdmin | permissions.IsOrgViewer]
    filter_backends = [
        drf_filters.OrderingFilter,
        custom_filters.CustomizableSearchFilter
    ]
    search_fields = ["name", "description", ]
    ordering_fields = ['id', 'name']
    ordering = ['id']

    def get_serializer_class(self):
        return v2_serializers.OrganizationSerializer

    def get_queryset(self):
        # Return a list with the organizations that the currently authenticated user is allowed to see.
        return get_user_organizations_qs(user=self.request.user)


class MemberViewSet(viewsets.ModelViewSet):
    """
    An endpoint for managing organization members
    """
    permission_classes = [permissions.IsSuperuser | permissions.IsOrgAdmin | permissions.IsOrgViewer]
    filter_backends = [drf_filters.OrderingFilter]
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


class IntegrationsView(viewsets.ModelViewSet):
    """
    An endpoint for managing integrations
    """
    permission_classes = [permissions.IsSuperuser | permissions.IsOrgAdmin | permissions.IsOrgViewer]
    filter_backends = [
        drf_filters.OrderingFilter,
        django_filters.rest_framework.DjangoFilterBackend,
        custom_filters.CustomizableSearchFilter
    ]
    filterset_class = IntegrationFilter
    ordering_fields = ['id', 'name', 'base_url', 'type__name', 'owner__name']
    ordering = ['id']
    search_fields = ["name", "base_url", 'type__name', 'type__value', 'owner__name', ]

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return v2_serializers.IntegrationCreateUpdateSerializer
        if self.action == "urls":
            return v2_serializers.IntegrationURLSerializer
        if self.action == "owners":
            return v2_serializers.IntegrationOwnerSerializer
        if self.action == "api_key":
            return v2_serializers.IntegrationApiKeySerializer
        return v2_serializers.IntegrationRetrieveFullSerializer

    def get_queryset(self):
        # Superusers can see all
        if self.request.user.is_superuser:
            return Integration.objects.all()
        # Return the list of connections that the user is allowed to see
        return get_user_integrations_qs(user=self.request.user)

    @action(detail=False, methods=['get'])
    def urls(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)

    @action(detail=True, methods=['get'], url_path="api-key")
    def api_key(self, request, *args, **kwargs):
        return self.retrieve(request, *args, **kwargs)

    @action(detail=False, methods=['get'])
    def owners(self, request, *args, **kwargs):
        # Filter integrations if any filters are applied
        integrations_qs = self.filter_queryset(self.get_queryset())
        # Get the owners of those integrations
        owners_qs = get_integrations_owners_qs(integrations_qs)
        # Return a paginated response
        page = self.paginate_queryset(owners_qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(owners_qs, many=True)
        return Response(serializer.data)


class IntegrationTypeView(viewsets.ModelViewSet):
    """
    An endpoint for listing integration types.
    """
    queryset = IntegrationType.objects.all()
    lookup_field = "value"
    permission_classes = [permissions.IsSuperuser | permissions.IsOrgAdmin | permissions.IsOrgViewer]
    filter_backends = [
        drf_filters.OrderingFilter,
        django_filters.rest_framework.DjangoFilterBackend,
        custom_filters.CustomizableSearchFilter
    ]
    filterset_class = IntegrationTypeFilter
    ordering_fields = ["id", "value", "name"]
    ordering = ["name"]
    search_fields = ["value", "name", "description"]

    def get_serializer_class(self):
        if self.action == "create":
            return v2_serializers.IntegrationTypeIdempotentCreateSerializer
        elif self.action in ["update", "partial_update"]:
            return v2_serializers.IntegrationTypeUpdateSerializer
        return v2_serializers.IntegrationTypeFullSerializer


class ConnectionsView(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet
):
    """
    An endpoint for retrieving connections
    """
    permission_classes = [permissions.IsSuperuser | permissions.IsOrgAdmin | permissions.IsOrgViewer]
    filter_backends = [
        drf_filters.OrderingFilter,
        django_filters.rest_framework.DjangoFilterBackend,
        custom_filters.CustomizableSearchFilter
    ]
    filterset_class = ConnectionFilter
    ordering_fields = ['id', 'name', 'base_url', 'type__name', 'owner__name']
    ordering = ['id']
    search_fields = [  # Default search fields (used in the global search box)
        "name", "base_url", 'type__name',  # Providers
        "routing_rules_by_provider__destinations__name",  # Destinations
        "routing_rules_by_provider__destinations__type__name",
        "routing_rules_by_provider__destinations__base_url",
        "owner__name",  # Organizations
    ]

    def get_queryset(self):
        """
        Return the integrations used as providers in at least one route
        """
        providers = Integration.objects.filter(routing_rules_by_provider__isnull=False).distinct()
        if self.request.user.is_superuser:
            return providers  # Superusers can see all the providers
        # Filter providers to return only the ones that the user is allowed to see
        user_organizations = get_user_organizations_qs(user=self.request.user)
        return providers.filter(owner__in=Subquery(user_organizations.values('id')))

    def get_serializer_class(self):
        return v2_serializers.ConnectionRetrieveSerializer


class SourcesView(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet
):
    """
    An endpoint for retrieving sources
    """
    permission_classes = [permissions.IsSuperuser | permissions.IsOrgAdmin | permissions.IsOrgViewer]
    #lookup_field = 'external_id'
    filter_backends = [
        drf_filters.OrderingFilter,
        django_filters.rest_framework.DjangoFilterBackend,
        custom_filters.CustomizableSearchFilter
    ]
    filterset_class = SourceFilter
    ordering_fields = ['external_id', 'integration__name', 'created_at', 'last_update', 'update_frequency',
                       'integration__id']
    ordering = ['external_id']
    search_fields = [  # Default search fields (used in the global search box)
        "external_id",  # Sources
        "integration__name", "integration__base_url",  # Providers
        "integration__type__name",  "integration__type__value",
        "integration__routing_rules_by_provider__destinations__name",  # Destinations
        "integration__routing_rules_by_provider__destinations__type__name",
        "integration__routing_rules_by_provider__destinations__type__value",
        "integration__routing_rules_by_provider__destinations__base_url",
        "integration__owner__name",  # Organizations
    ]

    def get_queryset(self):
        # Return a list with the devices that the currently authenticated user is allowed to see
        return get_user_sources_qs(user=self.request.user)

    def get_serializer_class(self):
        return v2_serializers.SourceRetrieveSerializer


class RoutesView(viewsets.ModelViewSet):
    """
    An endpoint for managing routes
    """
    permission_classes = [permissions.IsSuperuser | permissions.IsOrgAdmin | permissions.IsOrgViewer]
    filter_backends = [
        drf_filters.OrderingFilter,
        django_filters.rest_framework.DjangoFilterBackend,
        custom_filters.CustomizableSearchFilter
    ]
    filterset_class = RouteFilter
    ordering_fields = ['id', 'name', 'owner__name']
    ordering = ['id']
    search_fields = [  # Default search fields (used in the global search box)
        "name", "owner__name",  # Routes
        "data_providers__name",  # Providers
        "data_providers__type__name",
        "data_providers__type__value",
        "data_providers__base_url",
        "destinations__name",  # Destinations
        "destinations__type__name",
        "destinations__type__value",
        "destinations__base_url",
    ]

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return v2_serializers.RouteCreateUpdateSerializer
        return v2_serializers.RouteRetrieveFullSerializer

    def get_queryset(self):
        # Returns a list with the routes that the user is allowed to see
        return get_user_routes_qs(user=self.request.user)


class SingleOrBulkCreateModelMixin(mixins.CreateModelMixin):

    def create(self, request, *args, **kwargs):
        # We accept a single object or a list
        many = isinstance(request.data, list)
        serializer = self.get_serializer(data=request.data, many=many)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, headers=headers)


class TraceUpdateMixin:
    """
    Update Gundi Traces based on object id.
    """
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        # There may be multiple traces with the same object_id for multiple destinations
        traces = self.get_queryset().filter(object_id=kwargs['pk'])
        if traces.count() == 0:
            raise drf_exceptions.NotFound()
        serializer = self.get_serializer(traces, many=False,  data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)

    def perform_update(self, serializer):
        serializer.save()

    def partial_update(self, request, *args, **kwargs):
        kwargs['partial'] = True
        return self.update(request, *args, **kwargs)


class EventsView(
    SingleOrBulkCreateModelMixin,
    TraceUpdateMixin,
    viewsets.GenericViewSet
):
    """
    An endpoint for sending Events (a.k.a Reports).
    """
    authentication_classes = []  # Authentication is handled by Keycloak
    permission_classes = []
    serializer_class = v2_serializers.EventCreateUpdateSerializer
    queryset = GundiTrace.objects.all()


class ObservationsView(
    SingleOrBulkCreateModelMixin,
    viewsets.GenericViewSet
):
    """
    An endpoint for sending Observations (a.k.a Positions).
    """
    authentication_classes = []  # Authentication is handled by Keycloak
    permission_classes = []
    serializer_class = v2_serializers.ObservationCreateSerializer
    queryset = GundiTrace.objects.all()


class AttachmentViewSet(
    mixins.CreateModelMixin,
    viewsets.GenericViewSet
):
    """
    An endpoint for managing event attachments
    """
    authentication_classes = []  # Authentication is handled by Keycloak
    permission_classes = []
    serializer_class = v2_serializers.EventAttachmentSerializer

    def get_queryset(self):
        return GundiTrace.objects.filter(
            object_type=StreamPrefixEnum.attachment.value,
            related_to=self.kwargs['event_pk']
        )

    def create(self, request, *args, **kwargs):
        if len(request.FILES) == 0:
            raise drf_exceptions.ValidationError("At least one file must be provided.")
        # We accept a single attachment or a list
        many = len(request.FILES) > 1
        for key in request.FILES.keys():
            request.data.pop(key)
        data = [
            {
                **request.data.dict(),
                "file": v
            }
            for k, v in request.FILES.items()
        ]
        context = self.get_serializer_context()
        if not many:
            data = data[0]
        serializer = self.get_serializer(data=data, many=many, context=context)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, headers=headers)


class GundiTraceViewSet(
    mixins.ListModelMixin,
    viewsets.GenericViewSet
):
    """
    An endpoint retrieving traces.
    """
    permission_classes = [permissions.IsSuperuser]
    filter_backends = [drf_filters.OrderingFilter, django_filters.rest_framework.DjangoFilterBackend]
    filterset_class = GundiTraceFilter
    ordering_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']
    serializer_class = v2_serializers.GundiTraceRetrieveSerializer
    queryset = GundiTrace.objects.all()


class ActivityLogsViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet
):
    """
    An endpoint retrieving and revert activity logs.
    """
    permission_classes = [permissions.IsSuperuser | permissions.IsOrgAdmin | permissions.IsOrgViewer]
    serializer_class = v2_serializers.ActivityLogRetrieveSerializer
    filter_backends = [
        drf_filters.OrderingFilter,
        django_filters.rest_framework.DjangoFilterBackend,
        custom_filters.CustomizableSearchFilter
    ]
    filterset_class = ActivityLogFilter
    ordering_fields = ["created_at", ]
    ordering = ["-created_at"]
    search_fields = [  # Default search fields (used in the global search box)
        "title", "value", "created_by__username", "created_by__email",
        "integration__name", "integration__base_url", "integration__type__name", "integration__type__value",
    ]

    def get_queryset(self):
        # Superusers can see all
        if self.request.user.is_superuser:
            return ActivityLog.objects.all()
        # Returns a list with the logs of integrations that the user is allowed to see
        user_integrations = get_user_integrations_qs(user=self.request.user)
        return ActivityLog.objects.filter(integration__in=Subquery(user_integrations.values("id")))

    @action(detail=True, methods=["post", "put"])
    def revert(self, request, pk=None):
        activity_log = self.get_object()
        if not activity_log.is_reversible:
            raise drf_exceptions.ValidationError("This activity log is not reversible.")
        activity_log.revert()
        return Response({"status": "Activity reverted with success"})


class ActionTriggerView(
    viewsets.GenericViewSet
):
    """
    An endpoint for triggering actions
    """
    permission_classes = [permissions.IsSuperuser | permissions.IsOrgAdmin | permissions.IsOrgViewer]
    lookup_field = "value"
    serializer_class = v2_serializers.ActionTriggerSerializer

    @action(detail=True, methods=["post", "put"], lookup_field="value")
    def execute(self, request, integration_pk, value=None):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        integration = Integration.objects.get(id=integration_pk)
        integration_action = IntegrationAction.objects.get(integration_type=integration.type, value=value)
        response_data = integration_action.execute(
            integration=integration,
            run_in_background=serializer.data.get("run_in_background", False),
            config_overrides=serializer.data.get("config_overrides")
        )
        return Response(response_data, status=status.HTTP_200_OK)
