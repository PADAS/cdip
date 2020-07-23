from rest_framework import serializers

from organizations.models import Organization
from integrations.models import *


class OrganizationSerializer(serializers.ModelSerializer):

    class Meta:
        model = Organization
        fields = ['id', 'name', 'description']


class InboundIntegrationTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = InboundIntegrationType
        fields = ['id', 'name', 'description']


class InboundIntegrationConfigurationSerializer(serializers.ModelSerializer):
    class Meta:
        model = InboundIntegrationConfiguration
        fields = ['id', 'type', 'owner', 'endpoint', 'cursor', 'login', 'password', 'token',
                  'defaultConfiguration']


class OutboundIntegrationTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = OutboundIntegrationType
        fields = ['id', 'name', 'description']


class OutboundIntegrationConfigurationSerializer(serializers.ModelSerializer):
    class Meta:
        model = InboundIntegrationConfiguration
        fields = ['id', 'type', 'owner', 'endpoint', 'cursor', 'login', 'password', 'token']
