import logging
from functools import wraps

import rest_framework
from datadog import statsd
from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import PermissionDenied
from django.db.models import F, Window
from django.db.models.functions import FirstValue
from django.http import JsonResponse, Http404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics
from rest_framework.decorators import permission_classes, api_view
from rest_framework.permissions import AllowAny

from accounts.utils import get_user_profile
from cdip_admin import settings
from cdip_admin.utils import jwt_decode_token
from clients.models import ClientProfile
from core.permissions import IsGlobalAdmin, IsOrganizationMember, IsServiceAccount
from .filters import InboundIntegrationConfigurationFilter, DeviceStateFilter
from .serializers import *
from .utils import post_device_information

logger = logging.getLogger(__name__)


@api_view(['GET'])
@permission_classes([AllowAny])
def public(request):
    statsd.increment('portal.healthcheck')
    return JsonResponse({'message': 'Hello from a public endpoint! You don\'t need to be authenticated to see this.'})


# def get_user_perms(args):
#     """Obtains the Access Token from the Authorization Header
#     """
#     for arg in args:
#         if isinstance(arg, rest_framework.request.Request):
#             if arg.auth:
#                 permissions = []
#                 token = jwt_decode_token(arg.auth.decode('ascii'))
#                 for p in token['authorization'].get('permissions', []):
#                     if 'scopes' in p:
#                         for scope in p['scopes']:
#                             if '.' in p['rsname']:
#                                 app, model = p['rsname'].split('.', 1)
#                                 permissions.append(f'{app}.{scope}.{model}')
#                             else:
#                                 permissions.append(f'{scope}:{p["rsname"]}')
#                     else:
#                         permissions.append(p['rsname'])
#                 client_id = token['clientId']
#                 arg.session['user_id'] = client_id
#                 return permissions
#             else:
#                 token = jwt_decode_token(arg.user.oidc_profile.access_token)
#                 permissions = [
#                     role for role in token['resource_access'].get(
#                         settings.KEYCLOAK_CLIENT_ID,
#                         {'roles': []}
#                     )['roles']
#                 ]
#                 arg.session['user_id'] = arg.user.username
#                 return permissions


def get_profile(user_id):
    profile = get_user_profile(user_id)

    if profile is None:
        profile = get_client_profile(user_id)

    return profile


def get_client_profile(user_id):

    try:
        profile = ClientProfile.objects.get(client_id=user_id)
    except ObjectDoesNotExist:
        profile = None

    return profile


# def requires_scope(required_scope: list) -> list:
#     """Determines if the required scope is present in the Access Token
#     Args:
#         required_scope (str): The scope required to access the resource
#     """
#     def require_scope(f):
#         @wraps(f)
#         def decorated(*args, **kwargs):
#             token_scopes = get_user_perms(args)
#             for token_scope in token_scopes:
#                 if token_scope in required_scope:
#                     return f(*args, **kwargs)
#             response = JsonResponse({'message': 'You don\'t have access to this resource'})
#             response.status_code = 403
#             return response
#         return decorated
#     return require_scope


# def service_accessible():
#     def get_client_id(f):
#         @wraps(f)
#         def decorated(*args, **kwargs):
#             for arg in args:
#                 if isinstance(arg, rest_framework.request.Request):
#                     if arg.auth:
#                         token = jwt_decode_token(arg.auth.decode('ascii'))
#                         client_id = token['clientId']
#                         arg.session['client_id'] = client_id
#             return f(*args, **kwargs)
#         return decorated
#     return get_client_id


class OrganizationsListView(generics.ListAPIView):
    """ Returns List of Organizations """
    serializer_class = OrganizationSerializer
    permission_classes = [IsGlobalAdmin | IsOrganizationMember]

    def get_queryset(self):
        user = self.request.user
        queryset = Organization.objects.all()
        if not IsGlobalAdmin.has_permission(None, self.request, self):
            queryset = IsOrganizationMember.filter_queryset_for_user(queryset, user, 'name')
        return queryset

    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)


class OrganizationDetailsView(generics.RetrieveAPIView):
    """ Returns Detail of an Organization """
    serializer_class = OrganizationSerializer
    permission_classes = [IsGlobalAdmin | IsOrganizationMember]

    def get(self, request, *args, **kwargs):
        return self.retrieve(request, *args, **kwargs)


class InboundIntegrationTypeListView(generics.ListAPIView):
    """ Returns List of Inbound Integration Types """
    queryset = InboundIntegrationType.objects.all()
    serializer_class = InboundIntegrationTypeSerializer
    permission_classes = [IsGlobalAdmin | IsOrganizationMember]

    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)


class InboundIntegrationTypeDetailsView(generics.RetrieveAPIView):
    """ Returns Detail of an Inbound Integration Type """
    queryset = InboundIntegrationType.objects.all()
    serializer_class = InboundIntegrationTypeSerializer
    permission_classes = [IsGlobalAdmin | IsOrganizationMember]

    def get(self, request, *args, **kwargs):
        return self.retrieve(request, *args, **kwargs)


class OutboundIntegrationTypeListView(generics.ListAPIView):
    """ Returns List of Outbound Integration Types """
    queryset = OutboundIntegrationType.objects.all()
    serializer_class = InboundIntegrationTypeSerializer
    permission_classes = [IsGlobalAdmin | IsOrganizationMember]

    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)


class OutboundIntegrationTypeDetailsView(generics.RetrieveAPIView):
    """ Returns Detail of an Outbound Integration Type """
    queryset = OutboundIntegrationType.objects.all()
    serializer_class = OutboundIntegrationTypeSerializer
    permission_classes = [IsGlobalAdmin | IsOrganizationMember]

    def get(self, request, *args, **kwargs):
        return self.retrieve(request, *args, **kwargs)


class InboundIntegrationConfigurationListView(generics.ListAPIView):
    """ Returns List of Inbound Integration Configurations
    """
    queryset = InboundIntegrationConfiguration.objects.filter(enabled=True).all()
    serializer_class = InboundIntegrationConfigurationSerializer
    filter_backends = [DjangoFilterBackend]
    filter_class = InboundIntegrationConfigurationFilter
    permission_classes = [IsGlobalAdmin | IsOrganizationMember | IsServiceAccount]

    def get_queryset(self):
        queryset = self.queryset
        if 'client_id' in self.request.session:
            client_id = self.request.session['client_id']
            client_profile = get_client_profile(client_id)
            queryset = queryset.filter(type_id=client_profile.type.id)
        else:
            if not IsGlobalAdmin.has_permission(None, self.request, None):
                queryset = IsOrganizationMember.filter_queryset_for_user(queryset, self.request.user,
                                                                         'owner__name')
        return queryset

    # @service_accessible()
    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)


class InboundIntegrationConfigurationDetailsView(generics.RetrieveUpdateAPIView):
    """ Returns Detail of an Inbound Integration Configuration
        Example State: {
                            "state": "{\"ST2010-2758\": 14469584, \"ST2010-2759\": 14430249, \"ST2010-2760\": 14650428}"
                       }
    """
    queryset = InboundIntegrationConfiguration.objects.all()
    serializer_class = InboundIntegrationConfigurationSerializer
    permission_classes = [IsGlobalAdmin | IsOrganizationMember]

    def get(self, request, *args, **kwargs):
        return self.retrieve(request, *args, **kwargs)

    def put(self, request, *args, **kwargs):
        response = self.update(request, *args, **kwargs)
        return response

    # # TODO: this doesn't work yet with the savannah function
    # @requires_scope(['patch:inboundintegrationconfiguration', 'core.admin'])
    # def patch(self, request, *args, **kwargs):
    #     # TODO: update_device_information takes 2 params
    #     # update_device_information(self.queryset)
    #     return self.partial_update(request, *args, **kwargs)


class OutboundIntegrationConfigurationListView(generics.ListAPIView):
    """ Returns List of Outbound Integration Configurations """

    queryset = OutboundIntegrationConfiguration.objects.all()
    serializer_class = OutboundIntegrationConfigurationSerializer
    permission_classes = [IsGlobalAdmin | IsOrganizationMember]

    def get_queryset(self):
        queryset = OutboundIntegrationConfiguration.objects.filter(enabled=True).all()

        if not IsGlobalAdmin.has_permission(None, self.request, None):
            queryset = IsOrganizationMember.filter_queryset_for_user(queryset, self.request.user, 'owner__name')

        inbound_id = self.request.query_params.get('inbound_id')
        if inbound_id:
            try:
                ibc = InboundIntegrationConfiguration.objects.get(id=inbound_id)
                queryset = queryset.filter(devicegroup__devices__inbound_configuration=ibc).annotate(
                    inbound_type_slug=F('devicegroup__devices__inbound_configuration__type__slug')).distinct()
            except InboundIntegrationConfiguration.DoesNotExist:
                queryset = queryset.none()

        return queryset

    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)


class OutboundIntegrationConfigurationDetailsView(generics.RetrieveAPIView):
    """ Returns Detail of an Outbound Integration Configuration """

    queryset = OutboundIntegrationConfiguration.objects.all()
    serializer_class = OutboundIntegrationConfigurationSerializer
    permission_classes = [IsGlobalAdmin | IsOrganizationMember]

    def get(self, request, *args, **kwargs):
        return self.retrieve(request, *args, **kwargs)


class DeviceDetailsView(generics.RetrieveAPIView):
    """ Returns Detail of a Device """
    queryset = Device.objects.all()
    serializer_class = DeviceSerializer
    permission_classes = [IsGlobalAdmin | IsOrganizationMember]

    def get(self, request, *args, **kwargs):
        return self.retrieve(request, *args, **kwargs)


class DeviceListView(generics.ListAPIView):
    """ Returns List of Devices """
    serializer_class = DeviceSerializer
    permission_classes = [IsGlobalAdmin | IsOrganizationMember]

    def get_queryset(self):
        user = self.request.user
        queryset = Device.objects.all()
        if not IsGlobalAdmin.has_permission(None, self.request, None):
            queryset = IsOrganizationMember.filter_queryset_for_user(queryset, user,
                                                                     'inbound_configuration__owner__name')
        return queryset

    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)


class DeviceStateListView(generics.ListAPIView):
    """ Returns Device States -- Latest state for each device. """
    queryset = DeviceState.objects.all()
    serializer_class = DeviceStateSerializer
    filter_backends = [DjangoFilterBackend]
    filter_class = DeviceStateFilter
    permission_classes = [IsGlobalAdmin | IsOrganizationMember | IsServiceAccount]

    def get_queryset(self):

        filter = {
            'device__inbound_configuration__id': self.request.query_params['inbound_config_id']
        } if self.args else {}

        queryset = super().get_queryset().filter(**filter).order_by('device_id', '-created_at').distinct('device_id')

        return queryset

    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)


@api_view(['POST'])
def update_inbound_integration_state(request, integration_id):
    logger.info(f"Updating Inbound Configuration State, Integration ID {integration_id}")
    if request.method == 'POST':
        data = request.data

        try:
            config = InboundIntegrationConfiguration.objects.get(id=integration_id)
        except InboundIntegrationConfiguration.DoesNotExist:
            logger.warning("Retrieve Inbound Configuration, Integration Not Found",
                           extra={"integration_id": integration_id})
            raise Http404

        result = post_device_information(data, config)
        response = list(result)
        return JsonResponse(response, safe=False)









