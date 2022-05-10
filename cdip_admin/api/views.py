import logging

import rest_framework
from datadog import statsd
from django.core.exceptions import PermissionDenied
from django.db.models import F
from django.http import JsonResponse, Http404
from django.utils.translation import ugettext_lazy as _
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics
from rest_framework.decorators import permission_classes, api_view
from rest_framework.exceptions import APIException, status, ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from cdip_admin.utils import parse_bool
from .filters import *
from .serializers import *
from .utils import post_device_information

logger = logging.getLogger(__name__)


@api_view(["GET"])
@permission_classes([AllowAny])
def public(request):
    statsd.increment("portal.healthcheck")
    return JsonResponse(
        {
            "message": "Hello from a public endpoint! You don't need to be authenticated to see this."
        }
    )


class OrganizationsListView(generics.ListAPIView):
    """Returns List of Organizations"""

    serializer_class = OrganizationSerializer
    permission_classes = (rest_framework.permissions.IsAuthenticated,)
    filter_class = OrganizationFilter

    def get_queryset(self):
        user = self.request.user
        queryset = Organization.objects.all()
        if not IsGlobalAdmin.has_permission(None, self.request, self):
            queryset = IsOrganizationMember.filter_queryset_for_user(
                queryset, user, "name"
            )
        return queryset

    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)


class OrganizationDetailsView(generics.RetrieveAPIView):
    """Returns Detail of an Organization"""

    serializer_class = OrganizationSerializer
    permission_classes = (rest_framework.permissions.IsAuthenticated,)

    filter_class = OrganizationFilter

    def get(self, request, *args, **kwargs):
        return self.retrieve(request, *args, **kwargs)


class InboundIntegrationTypeListView(generics.ListAPIView):
    """Returns List of Inbound Integration Types"""

    queryset = InboundIntegrationType.objects.all()
    serializer_class = InboundIntegrationTypeSerializer
    permission_classes = (rest_framework.permissions.IsAuthenticated,)

    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)


class InboundIntegrationTypeDetailsView(generics.RetrieveAPIView):
    """Returns Detail of an Inbound Integration Type"""

    queryset = InboundIntegrationType.objects.all()
    serializer_class = InboundIntegrationTypeSerializer
    permission_classes = (rest_framework.permissions.IsAuthenticated,)

    def get(self, request, *args, **kwargs):
        return self.retrieve(request, *args, **kwargs)


class OutboundIntegrationTypeListView(generics.ListAPIView):
    """Returns List of Outbound Integration Types"""

    queryset = OutboundIntegrationType.objects.all()
    serializer_class = OutboundIntegrationTypeSerializer
    permission_classes = (rest_framework.permissions.IsAuthenticated,)

    # filter_class = OutboundIntegrationTypeFilter
    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)


class OutboundIntegrationTypeDetailsView(generics.RetrieveAPIView):
    """Returns Detail of an Outbound Integration Type"""

    queryset = OutboundIntegrationType.objects.all()
    serializer_class = OutboundIntegrationTypeSerializer
    permission_classes = (IsGlobalAdmin | IsOrganizationMember,)

    def get(self, request, *args, **kwargs):
        return self.retrieve(request, *args, **kwargs)


class InboundIntegrationConfigurationListView(generics.ListAPIView):
    """Returns List of Inbound Integration Configurations"""

    serializer_class = InboundIntegrationConfigurationSerializer
    filter_backends = [DjangoFilterBackend]
    filter_class = InboundIntegrationConfigurationFilter
    permission_classes = (rest_framework.permissions.IsAuthenticated,)

    queryset = InboundIntegrationConfiguration.objects.all()

    def get_queryset(self):
        qs = super().get_queryset()

        # Insist on filtering by enabled, and default to True.
        enabled_qp = parse_bool(self.request.GET.get("enabled", True))
        return qs.filter(enabled=enabled_qp)


class CeresTagIdentifiersListView(generics.ListAPIView):
    """Returns List of Identifiers used during the software provider configuration setup for Ceres Tag Integrations"""

    serializer_class = CeresTagIdentifiersSerializer
    filter_backends = [DjangoFilterBackend]
    filter_class = CeresTagIdentifiersFilter
    permission_classes = (rest_framework.permissions.IsAuthenticated,)

    queryset = InboundIntegrationConfiguration.objects.all()

    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)


class InboundIntegrationConfigurationDetailsView(generics.RetrieveUpdateAPIView):

    queryset = InboundIntegrationConfiguration.objects.all()
    serializer_class = InboundIntegrationConfigurationSerializer
    permission_classes = (IsGlobalAdmin | IsOrganizationMember | IsServiceAccount,)

    def get(self, request, *args, **kwargs):
        integration = get_object_or_404(
            InboundIntegrationConfiguration, id=kwargs["pk"]
        )
        self.permission_checks(request, integration)
        return self.retrieve(request, *args, **kwargs)

    def put(self, request, *args, **kwargs):
        integration = get_object_or_404(
            InboundIntegrationConfiguration, id=kwargs["pk"]
        )
        self.permission_checks(request, integration)
        response = self.update(request, *args, **kwargs)
        return response

    def permission_checks(self, request, integration):
        if not IsGlobalAdmin.has_permission(None, request, None):
            if IsOrganizationMember.has_permission(None, request, None):
                if not IsOrganizationMember.has_object_permission(
                    None, request, self, integration
                ):
                    raise PermissionDenied
            elif IsServiceAccount.has_permission(None, request, None):
                if not IsServiceAccount.has_object_permission(
                    None, request, self, integration
                ):
                    raise PermissionDenied


class OutboundIntegrationConfigurationListView(generics.ListAPIView):
    """Returns List of Outbound Integration Configurations"""

    queryset = OutboundIntegrationConfiguration.objects.all()
    serializer_class = OutboundIntegrationConfigurationSerializer
    permission_classes = (IsGlobalAdmin | IsOrganizationMember | IsServiceAccount,)

    # filter_backends =
    def get_queryset(self):
        queryset = OutboundIntegrationConfiguration.objects.filter(enabled=True).all()

        if not IsGlobalAdmin.has_permission(
            None, self.request, None
        ) and not IsServiceAccount.has_permission(None, self.request, None):
            queryset = IsOrganizationMember.filter_queryset_for_user(
                queryset, self.request.user, "owner__name"
            )

        inbound_id = self.request.query_params.get("inbound_id")
        device_id = self.request.query_params.get("device_id")
        if inbound_id:
            try:
                device = Device.objects.get(
                    external_id=device_id, inbound_configuration_id=inbound_id
                )
                queryset = (
                    queryset.filter(devicegroup__devices__id=device.id)
                    .annotate(
                        inbound_type_slug=F(
                            "devicegroup__devices__inbound_configuration__type__slug"
                        )
                    )
                    .distinct()
                )
            except Device.DoesNotExist:
                queryset = queryset.none()

        return queryset

    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)


class OutboundIntegrationConfigurationDetailsView(generics.RetrieveAPIView):
    """Returns Detail of an Outbound Integration Configuration"""

    queryset = OutboundIntegrationConfiguration.objects.all()
    serializer_class = OutboundIntegrationConfigurationSerializer
    permission_classes = (IsGlobalAdmin | IsOrganizationMember | IsServiceAccount,)

    def get(self, request, *args, **kwargs):
        return self.retrieve(request, *args, **kwargs)


class DeviceView(generics.RetrieveAPIView):
    """Returns Detail of a Device"""

    queryset = Device.objects.all()
    serializer_class = DeviceSerializer
    permission_classes = [IsGlobalAdmin | IsOrganizationMember | IsServiceAccount]

    def get(self, request, *args, **kwargs):
        return self.retrieve(request, *args, **kwargs)


class IntegrationDeviceView(generics.GenericAPIView):
    """Returns Detail of a Device based on integration_id and external_id

    param1 -- external_id of device
    """

    queryset = Device.objects.all()
    serializer_class = DeviceSerializer
    permission_classes = [IsGlobalAdmin | IsOrganizationMember | IsServiceAccount]

    def get_queryset(self):
        user = self.request.user
        queryset = super().get_queryset()
        integration_id = self.kwargs.get("integration_id")
        queryset = queryset.filter(inbound_configuration=integration_id)
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            queryset = IsOrganizationMember.filter_queryset_for_user(
                queryset, user, "inbound_configuration__owner__name"
            )
        return queryset

    def get(self, request, *args, **kwargs):
        external_id = self.request.query_params.get("external_id", None)
        if not external_id:
            raise MissingArgumentException(
                detail=_('"external_id" is required.'),
            )
        device = self.get_queryset().get(external_id=external_id)
        serializer = self.get_serializer(device)
        return Response(serializer.data)


class DeviceListView(generics.ListCreateAPIView):

    """Returns List of Devices"""

    serializer_class = DeviceSerializer
    permission_classes = (IsGlobalAdmin | IsOrganizationMember | IsServiceAccount,)
    queryset = Device.objects.all()

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["external_id", "inbound_configuration__type__slug"]

    def create(self, request, *args, **kwargs):
        device, created = Device.objects.get_or_create(
            inbound_configuration_id=request.data.get("inbound_configuration"),
            external_id=request.data.get("external_id"),
        )
        if created:
            status_code = status.HTTP_201_CREATED
            ibc = InboundIntegrationConfiguration.objects.get(
                id=request.data.get("inbound_configuration")
            )
            if ibc:
                logger.info(
                    "Adding id %s to default device group for ibc: %s",
                    device.id,
                    ibc.id,
                )
                ibc.default_devicegroup.devices.add(device.id)
        else:
            status_code = status.HTTP_200_OK
        serializer = self.get_serializer(device)

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status_code, headers=headers)

    def get_queryset(self):
        user = self.request.user
        queryset = super().get_queryset()
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            queryset = IsOrganizationMember.filter_queryset_for_user(
                queryset, user, "inbound_configuration__owner__name"
            )
        return queryset

    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        retval = super().post(request, *args, **kwargs)

        return retval


class BridgeIntegrationListView(generics.ListAPIView):

    serializer_class = BridgeSerializer
    permission_classes = (IsGlobalAdmin | IsOrganizationMember | IsServiceAccount,)
    queryset = BridgeIntegration.objects.all()

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user

        if not IsGlobalAdmin.has_permission(None, self.request, None):
            queryset = IsOrganizationMember.filter_queryset_for_user(
                queryset, user, "owner__name"
            )
        return queryset

    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class BridgeIntegrationView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = BridgeSerializer
    permission_classes = (IsGlobalAdmin | IsOrganizationMember | IsServiceAccount,)
    queryset = BridgeIntegration.objects.all()


class MissingArgumentException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = _("Missing arguments.")
    default_code = "error"


class ResourceNotFoundException(APIException):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = _("Resource not found.")
    default_code = "error"


class DeviceStateListView(generics.ListAPIView):
    """Returns Device States -- Latest state for each device."""

    queryset = DeviceState.objects.all()
    serializer_class = DeviceStateSerializer
    filter_backends = [DjangoFilterBackend]
    filter_class = DeviceStateFilter
    permission_classes = (IsGlobalAdmin | IsOrganizationMember | IsServiceAccount,)

    def get_queryset(self):

        inbound_config_id = self.request.query_params.get("inbound_config_id", None)
        if not inbound_config_id:
            raise MissingArgumentException(
                detail=_('"inbound_config_id" is required.'),
            )

        try:
            inbound_config = InboundIntegrationConfiguration.objects.get(
                id=inbound_config_id
            )
        except InboundIntegrationConfiguration.DoesNotExist:
            raise ResourceNotFoundException

        if IsServiceAccount.has_permission(None, self.request, None):
            if not IsServiceAccount.has_object_permission(
                None, self.request, self, inbound_config
            ):
                raise PermissionDenied

        filter = {"device__inbound_configuration__id": inbound_config_id}

        queryset = (
            super()
            .get_queryset()
            .filter(**filter)
            .order_by("device_id", "-created_at")
            .distinct("device_id")
        )

        if IsOrganizationMember.has_permission(None, self.request, None):
            IsOrganizationMember.filter_queryset_for_user(
                queryset,
                self.request.user,
                "device__inbound_configuration__owner__name",
            )

        return queryset

    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)


@api_view(["POST"])
def update_inbound_integration_state(request, integration_id):
    logger.info(
        f"Updating Inbound Configuration State, Integration ID {integration_id}"
    )
    if request.method == "POST":
        data = request.data

        try:
            config = InboundIntegrationConfiguration.objects.get(id=integration_id)
        except InboundIntegrationConfiguration.DoesNotExist:
            logger.warning(
                "Retrieve Inbound Configuration, Integration Not Found",
                extra={"integration_id": integration_id},
            )
            raise Http404

        result = post_device_information(data, config)
        response = list(result)
        return JsonResponse(response, safe=False)
