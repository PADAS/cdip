from django.http import JsonResponse, Http404


from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView
from rest_framework import generics, viewsets
from rest_framework.response import Response

from functools import wraps
import jwt


from .serializers import *

from core.utils import get_user_permissions

from integrations.models import *


def get_token_auth_header(args):
    """Obtains the Access Token from the Authorization Header
    """
    for arg in args:
        auth = arg.headers.get("authorization", None)
        if auth:
            parts = auth.split()
            return parts[1]


def get_user_perms(args):
    for arg in args:
        if hasattr(arg, 'user'):
            auth0user = arg.user.social_auth.get(provider='auth0')
            permissions = get_user_permissions(auth0user.uid)
            return permissions


def requires_scope(required_scope: object) -> object:
    """Determines if the required scope is present in the Access Token
    Args:
        required_scope (str): The scope required to access the resource
    """
    def require_scope(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            token = get_token_auth_header(args)
            if token is None:
                permissions = get_user_perms(args)
                for permission in permissions:
                    permission_name = permission['permission_name']
                    if permission_name == required_scope:
                        return f(*args, **kwargs)
                response = JsonResponse({'message': 'You don\'t have access to this resource'})
                response.status_code = 403
                return response
            decoded = jwt.decode(token, verify=False)
            if decoded.get("scope"):
                token_scopes = decoded["scope"].split()
                for token_scope in token_scopes:
                    if token_scope == required_scope:
                        return f(*args, **kwargs)
            response = JsonResponse({'message': 'You don\'t have access to this resource'})
            response.status_code = 403
            return response
        return decorated
    return require_scope


@api_view(['GET'])
@permission_classes([AllowAny])
def public(request):
    return JsonResponse({'message': 'Hello from a public endpoint! You don\'t need to be authenticated to see this.'})


@api_view(['GET'])
def private(request):
    return JsonResponse({'message': 'Hello from a private endpoint! You need to be authenticated to see this.'})


@api_view(['GET'])
@requires_scope('read:messages')
def private_scoped(request):
    return JsonResponse({'message': 'Hello from a private endpoint! You need to be authenticated and have a scope of read:messages to see this.'})


class OrganizationsListView(generics.ListAPIView):
    """ Returns List of Organizations """
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer

    @requires_scope('read:organizations')
    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)


class OrganizationDetailsView(generics.RetrieveAPIView):
    """ Returns Detail of an Organization """
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer

    @requires_scope('read:organizations')
    def get(self, request, *args, **kwargs):
        return self.retrieve(request, *args, **kwargs)


class InboundIntegrationTypeListView(generics.ListAPIView):
    """ Returns List of Inbound Integration Types """
    queryset = InboundIntegrationType.objects.all()
    serializer_class = InboundIntegrationTypeSerializer

    @requires_scope('read:inboundintegrationtype')
    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)


class InboundIntegrationTypeDetailsView(generics.RetrieveAPIView):
    """ Returns Detail of an Inbound Integration Type """
    queryset = InboundIntegrationType.objects.all()
    serializer_class = InboundIntegrationTypeSerializer

    @requires_scope('read:inboundintegrationtype')
    def get(self, request, *args, **kwargs):
        return self.retrieve(request, *args, **kwargs)


class OutboundIntegrationTypeListView(generics.ListAPIView):
    """ Returns List of Outbound Integration Types """
    queryset = OutboundIntegrationType.objects.all()
    serializer_class = InboundIntegrationTypeSerializer

    @requires_scope('read:outboundintegrationtype')
    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)


class OutboundIntegrationTypeDetailsView(generics.RetrieveAPIView):
    """ Returns Detail of an Outbound Integration Type """
    queryset = OutboundIntegrationType.objects.all()
    serializer_class = OutboundIntegrationTypeSerializer

    @requires_scope('read:outboundintegrationtype')
    def get(self, request, *args, **kwargs):
        return self.retrieve(request, *args, **kwargs)


class InboundIntegrationConfigurationListView(generics.ListAPIView):
    """ Returns List of Inbound Integration Configurations """
    queryset = InboundIntegrationConfiguration.objects.all()
    serializer_class = InboundIntegrationConfigurationSerializer

    @requires_scope('read:inboundintegrationconfiguration')
    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)


class InboundIntegrationConfigurationDetailsView(generics.RetrieveAPIView):
    """ Returns Detail of an Inbound Integration Configuration """
    queryset = InboundIntegrationConfiguration.objects.all()
    serializer_class = InboundIntegrationConfigurationSerializer

    @requires_scope('read:inboundintegrationconfiguration')
    def get(self, request, *args, **kwargs):
        return self.retrieve(request, *args, **kwargs)


class InboundIntegrationConfigurationDetailsViewByType(APIView):
    """ Returns Detail of an Inbound Integration Configuration by the Integration Type"""
    def get_object(self, type_id):
        try:
            return InboundIntegrationConfiguration.objects.get(type__id=type_id)
        except InboundIntegrationConfiguration.DoesNotExist:
            raise Http404

    @requires_scope('read:inboundintegrationconfiguration')
    def get(self, request, type_id, format=None):
        configuration = self.get_object(type_id)
        serializer = InboundIntegrationConfigurationSerializer(configuration)
        return Response(serializer.data)


class OutboundIntegrationConfigurationListView(generics.ListAPIView):
    """ Returns List of Outbound Integration Configurations """
    queryset = OutboundIntegrationConfiguration.objects.all()
    serializer_class = OutboundIntegrationConfigurationSerializer

    @requires_scope('read:outboundintegrationconfiguration')
    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)


class OutboundIntegrationConfigurationDetailsView(generics.RetrieveAPIView):
    """ Returns Detail of an Outbound Integration Configuration """
    queryset = OutboundIntegrationConfiguration.objects.all()
    serializer_class = OutboundIntegrationConfigurationSerializer

    @requires_scope('read:outboundintegrationconfiguration')
    def get(self, request, *args, **kwargs):
        return self.retrieve(request, *args, **kwargs)


