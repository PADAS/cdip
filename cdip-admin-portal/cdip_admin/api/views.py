from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.authentication import SessionAuthentication, BasicAuthentication
from rest_framework_jwt.authentication import JSONWebTokenAuthentication
from rest_framework import generics, viewsets
from rest_framework.response import Response

from functools import wraps
import jwt

from .serializers import *

from organizations.models import Organization

from integrations.models import *


def get_token_auth_header(request):
    """Obtains the Access Token from the Authorization Header
    """
    auth = request.headers.get("authorization", None)
    if auth:
        parts = auth.split()
        return parts[1]


def requires_scope(required_scope: object) -> object:
    """Determines if the required scope is present in the Access Token
    Args:
        required_scope (str): The scope required to access the resource
    """
    def require_scope(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            token = get_token_auth_header(args[0])
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
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer


class OrganizationDetailsView(generics.RetrieveAPIView):
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer


class InboundIntegrationTypeListView(generics.ListAPIView):
    queryset = InboundIntegrationType.objects.all()
    serializer_class = InboundIntegrationTypeSerializer


class InboundIntegrationTypeDetailsView(generics.RetrieveAPIView):
    queryset = InboundIntegrationType.objects.all()
    serializer_class = InboundIntegrationTypeSerializer


class OutboundIntegrationTypeListView(generics.ListAPIView):
    queryset = OutboundIntegrationType.objects.all()
    serializer_class = InboundIntegrationTypeSerializer


class OutboundIntegrationTypeDetailsView(generics.RetrieveAPIView):
    queryset = OutboundIntegrationType.objects.all()
    serializer_class = OutboundIntegrationTypeSerializer


class InboundIntegrationConfigurationListView(generics.ListAPIView):
    queryset = InboundIntegrationConfiguration.objects.all()
    serializer_class = InboundIntegrationConfigurationSerializer


class InboundIntegrationConfigurationDetailsView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated, JSONWebTokenAuthentication]
    queryset = InboundIntegrationConfiguration.objects.all()
    serializer_class = InboundIntegrationConfigurationSerializer


