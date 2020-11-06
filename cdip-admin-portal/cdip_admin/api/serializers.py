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
        fields = ['id', 'name', 'slug', 'description']


class InboundIntegrationConfigurationSerializer(serializers.ModelSerializer):
    type_slug = serializers.SlugField(source='type.slug', read_only=True)

    class Meta:
        model = InboundIntegrationConfiguration
        fields = ['id', 'type', 'owner', 'endpoint', 'state', 'login', 'password', 'token', 'type_slug',
                  'defaultConfiguration']
        read_only_fields = ['id', 'type', 'owner', 'endpoint', 'login', 'password', 'token', 'defaultConfiguration']


class OutboundIntegrationTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = OutboundIntegrationType
        fields = ['id', 'name', 'slug', 'description']


class OutboundIntegrationConfigurationSerializer(serializers.ModelSerializer):
    type_slug = serializers.SlugField(source='type.slug', read_only=True)

    class Meta:
        model = InboundIntegrationConfiguration
        fields = ['id', 'type', 'owner', 'endpoint', 'state', 'login', 'password', 'token', 'type_slug']


class DeviceSerializer(serializers.ModelSerializer):
    inbound_configuration_id = serializers.CharField(source='inbound_configuration.id', read_only=True)
    outbound_configuration_id = serializers.CharField(source='outbound_configuration.id', read_only=True)

    class Meta:
        model = Device
        fields = ['id', 'external_id', 'inbound_configuration_id', 'outbound_configuration_id']


class DeviceStateSerializer(serializers.ModelSerializer):
    device_external_id = serializers.CharField(source='device.external_id', read_only=True)

    class Meta:
        model = DeviceState
        fields = ['device_external_id', 'end_state']
