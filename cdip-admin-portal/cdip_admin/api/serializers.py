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
        read_only_fields = ['id', 'type', 'owner', 'endpoint', 'login', 'password', 'token', 'type_slug',
                            'default_devicegroup']
        fields = ['state',] + read_only_fields


class OutboundIntegrationTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = OutboundIntegrationType
        fields = ['id', 'name', 'slug', 'description']


class OutboundIntegrationConfigurationSerializer(serializers.ModelSerializer):
    type_slug = serializers.SlugField(source='type.slug', read_only=True)
    inbound_type_slug = serializers.CharField(required=False)

    class Meta:
        model = OutboundIntegrationConfiguration
        fields = ['id', 'type', 'owner', 'name', 'endpoint', 'state', 'login', 'password',
                  'token', 'type_slug', 'inbound_type_slug',  'additional']


class DeviceSerializer(serializers.ModelSerializer):
    inbound_configuration_id = serializers.CharField(source='inbound_configuration.id', read_only=True)

    class Meta:
        model = Device
        fields = ['id', 'external_id', 'inbound_configuration_id',]


class DeviceStateSerializer(serializers.ModelSerializer):
    device_external_id = serializers.CharField(source='device.external_id', read_only=True)

    class Meta:
        model = DeviceState
        fields = ['device_external_id', 'state']

from django.urls import reverse
from core.utils import add_base_url
class BridgeSerializer(serializers.ModelSerializer):

    href = serializers.SerializerMethodField('_href')

    def _href(self, obj):
        request = self.context['request']
        obj_path = reverse('bridge-integration-view', kwargs={'pk': obj.id})
        return add_base_url(request, obj_path)


    class Meta:
        model = BridgeIntegration
        fields = '__all__'