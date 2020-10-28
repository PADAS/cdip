import json
import logging
from functools import wraps

import jwt
import rest_framework
from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import PermissionDenied
from django.db.models import F, Window
from django.db.models.functions import FirstValue
from django.http import JsonResponse
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics
from rest_framework.decorators import permission_classes, api_view
from rest_framework.permissions import AllowAny
from datadog import statsd

from accounts.models import AccountProfile
from cdip_admin import settings
from cdip_admin.utils import jwt_decode_token
from clients.models import ClientProfile
from .filters import InboundIntegrationConfigurationFilter, DeviceStateFilter
from .serializers import *
from .utils import update_device_information

logger = logging.getLogger(__name__)


@api_view(['GET'])
@permission_classes([AllowAny])
def public(request):
    statsd.increment('portal.healthcheck')
    return JsonResponse({'message': 'Hello from a public endpoint! You don\'t need to be authenticated to see this.'})


def get_user_perms(args):
    """Obtains the Access Token from the Authorization Header
    """
    for arg in args:
        if isinstance(arg, rest_framework.request.Request):
            if arg.auth:
                permissions = []
                token = jwt_decode_token(arg.auth.decode('ascii'))
                for p in token['authorization'].get('permissions', []):
                    if 'scopes' in p:
                        for scope in p['scopes']:
                            if '.' in p['rsname']:
                                app, model = p['rsname'].split('.', 1)
                                permissions.append(f'{app}.{scope}.{model}')
                            else:
                                permissions.append(f'{scope}:{p["rsname"]}')
                    else:
                        permissions.append(p['rsname'])

                return permissions
            else:
                token = jwt_decode_token(arg.user.oidc_profile.access_token)
                permissions = [
                    role for role in token['resource_access'].get(
                        settings.KEYCLOAK_CLIENT_ID,
                        {'roles': []}
                    )['roles']
                ]

                return permissions


def get_profile(user_id):
    profile = get_user_profile(user_id)

    if profile is None:
        profile = get_client_profile(user_id)

    return profile


def get_user_profile(user_id):

    try:
        profile = AccountProfile.objects.get(user_id=user_id)
    except ObjectDoesNotExist:
        profile = None

    return profile


def get_client_profile(user_id):

    try:
        profile = ClientProfile.objects.get(client_id=user_id)
    except ObjectDoesNotExist:
        profile = None

    return profile


def requires_scope(required_scope: list) -> list:
    """Determines if the required scope is present in the Access Token
    Args:
        required_scope (str): The scope required to access the resource
    """
    def require_scope(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            token_scopes = get_user_perms(args)
            for token_scope in token_scopes:
                if token_scope in required_scope:
                    return f(*args, **kwargs)
            response = JsonResponse({'message': 'You don\'t have access to this resource'})
            response.status_code = 403
            return response
        return decorated
    return require_scope


class OrganizationsListView(generics.ListAPIView):
    """ Returns List of Organizations """
    serializer_class = OrganizationSerializer

    def get_queryset(self):
        user_id = self.request.session['user_id']

        profile = get_profile(user_id)

        if profile.organizations:
            queryset = Organization.objects.filter(id__in=profile.organizations.all())
        else:
            raise PermissionDenied
        return queryset

    @requires_scope(['read:organizations', 'core.admin'])
    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)


class OrganizationDetailsView(generics.RetrieveAPIView):
    """ Returns Detail of an Organization """
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer

    @requires_scope(['read:organizations', 'core.admin'])
    def get(self, request, *args, **kwargs):
        return self.retrieve(request, *args, **kwargs)


class InboundIntegrationTypeListView(generics.ListAPIView):
    """ Returns List of Inbound Integration Types """
    queryset = InboundIntegrationType.objects.all()
    serializer_class = InboundIntegrationTypeSerializer

    @requires_scope(['read:inboundintegrationtype', 'core.admin'])
    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)


class InboundIntegrationTypeDetailsView(generics.RetrieveAPIView):
    """ Returns Detail of an Inbound Integration Type """
    queryset = InboundIntegrationType.objects.all()
    serializer_class = InboundIntegrationTypeSerializer

    @requires_scope(['read:inboundintegrationtype', 'core.admin'])
    def get(self, request, *args, **kwargs):
        return self.retrieve(request, *args, **kwargs)


class OutboundIntegrationTypeListView(generics.ListAPIView):
    """ Returns List of Outbound Integration Types """
    queryset = OutboundIntegrationType.objects.all()
    serializer_class = InboundIntegrationTypeSerializer

    @requires_scope(['read:outboundintegrationtype', 'core.admin'])
    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)


class OutboundIntegrationTypeDetailsView(generics.RetrieveAPIView):
    """ Returns Detail of an Outbound Integration Type """
    queryset = OutboundIntegrationType.objects.all()
    serializer_class = OutboundIntegrationTypeSerializer

    @requires_scope(['read:outboundintegrationtype', 'core.admin'])
    def get(self, request, *args, **kwargs):
        return self.retrieve(request, *args, **kwargs)


class InboundIntegrationConfigurationListView(generics.ListAPIView):
    """ Returns List of Inbound Integration Configurations
    """
    queryset = InboundIntegrationConfiguration.objects.all()
    serializer_class = InboundIntegrationConfigurationSerializer
    filter_backends = [DjangoFilterBackend]
    filter_class = InboundIntegrationConfigurationFilter

    def get_queryset(self):
        user_id = self.request.session['user_id']
        if user_id is None:
            logger.warning("Retrieve Inbound Configuration, User Not Logged In")
            raise PermissionDenied
        logger.info("Retrieve Inbound Configuration",
                    extra={"user_id": user_id})
        profile = get_profile(user_id)
        if profile:
            if isinstance(profile, ClientProfile):
                queryset = InboundIntegrationConfiguration.objects.filter(type_id=profile.type.id)
            else:
                queryset = InboundIntegrationConfiguration.objects.filter(owner__id__in=profile.organizations.all())
        else:
            logger.warning("Retrieve Inbound Configuration, Profile Not Found",
                           extra={"user_id": user_id})
            raise PermissionDenied
        return queryset

    @requires_scope(['read:inboundintegrationconfiguration', 'core.admin'])
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

    @requires_scope(['read:inboundintegrationconfiguration', 'core.admin'])
    def get(self, request, *args, **kwargs):
        return self.retrieve(request, *args, **kwargs)

    @requires_scope(['update:inboundintegrationconfiguration', 'core.admin'])
    def put(self, request, *args, **kwargs):
        pk = kwargs['pk']
        response = self.update(request, *args, **kwargs)
        data = request.data
        state = data['state']
        item = InboundIntegrationConfiguration.objects.get(id=pk)
        update_device_information(state, item)
        return response

    # TODO: this doesn't work yet with the savannah function
    @requires_scope(['patch:inboundintegrationconfiguration', 'core.admin'])
    def patch(self, request, *args, **kwargs):
        # TODO: update_device_information takes 2 params
        update_device_information(self.queryset)
        return self.partial_update(request, *args, **kwargs)


class OutboundIntegrationConfigurationListView(generics.ListAPIView):
    """ Returns List of Outbound Integration Configurations """
    queryset = OutboundIntegrationConfiguration.objects.all()
    serializer_class = OutboundIntegrationConfigurationSerializer

    @requires_scope(['read:outboundintegrationconfiguration', 'core.admin'])
    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)


class OutboundIntegrationConfigurationDetailsView(generics.RetrieveAPIView):
    """ Returns Detail of an Outbound Integration Configuration """
    queryset = OutboundIntegrationConfiguration.objects.all()
    serializer_class = OutboundIntegrationConfigurationSerializer

    @requires_scope(['read:outboundintegrationconfiguration', 'core.admin'])
    def get(self, request, *args, **kwargs):
        return self.retrieve(request, *args, **kwargs)


class DeviceDetailsView(generics.RetrieveAPIView):
    """ Returns Detail of a Device """
    queryset = Device.objects.all()
    serializer_class = DeviceSerializer

    # TODO: Create New Permission Set for Device Management
    @requires_scope(['read:inboundintegrationconfiguration', 'core.admin'])
    def get(self, request, *args, **kwargs):
        return self.retrieve(request, *args, **kwargs)


class DeviceListView(generics.ListAPIView):
    """ Returns List of Devices """
    queryset = Device.objects.all()
    serializer_class = DeviceSerializer

    # TODO: Create New Permission Set for Device Management
    @requires_scope(['read:inboundintegrationconfiguration', 'core.admin'])
    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)


class DeviceStateListView(generics.ListAPIView):
    """ Returns Device States -- Latest state for each device. """
    queryset = DeviceState.objects.all()
    serializer_class = DeviceStateSerializer
    filter_backends = [DjangoFilterBackend]
    filter_class = DeviceStateFilter

    def get_queryset(self):

        filter = {
            'device__inbound_configuration__id': self.args['inbound_config_id']
        } if self.args else {}

        queryset = DeviceState.objects.filter(**filter).annotate(
            last_end_state=Window(expression=FirstValue(F('end_state')),
                                   partition_by=F('device_id'), order_by=[F('created_at').desc(),])
                                   ).distinct('device_id')

        return queryset

    # TODO: Create New Permission Set for Device Management
    @requires_scope(['read:inboundintegrationconfiguration', 'core.admin'])
    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)








