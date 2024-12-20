from datetime import datetime

import jsonschema
from rest_framework import serializers
from rest_framework import exceptions as drf_exceptions
from core.enums import RoleChoices
from accounts.utils import add_or_create_user_in_org
from accounts.models import AccountProfileOrganization, AccountProfile, UserAgreement, EULA
from core.utils import timezone_from_offset, parse_crontab_schedule_from_dict
from integrations.models import IntegrationConfiguration, IntegrationType, IntegrationAction, Integration, Route, \
    Source, SourceState, SourceConfiguration, ensure_default_route, RouteConfiguration, get_user_integrations_qs, \
    GundiTrace, WebhookConfiguration, IntegrationWebhook, IntegrationStatus, ConnectionStatus
from integrations.utils import register_integration_type_in_kong
from organizations.models import Organization
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from django.db import IntegrityError, transaction
from django.core.exceptions import ObjectDoesNotExist
from django_celery_beat.models import CrontabSchedule
from gundi_core.schemas.v2 import StreamPrefixEnum
from .utils import send_events_to_routing, send_attachments_to_routing, send_observations_to_routing, \
    send_event_update_to_routing

User = get_user_model()


class UserDetailsRetrieveSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    accepted_eula = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "email",
            "full_name",
            "is_superuser",
            "accepted_eula",
        )

    def get_full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}".strip().capitalize()

    def get_accepted_eula(self, obj):
        try:
            agreement = UserAgreement.objects.get(user=obj, eula=EULA.objects.get_active_eula())
        except UserAgreement.DoesNotExist as e:
            return False
        else:
            return agreement.accept


class OrganizationSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = ["id", "name", "description", "role"]

    def get_role(self, obj):
        user = self.context.get("request").user
        if user.is_superuser:
            return "superuser"
        return obj.accountprofileorganization_set.filter(accountprofile__user=user).last().role


class InviteUserSerializer(serializers.Serializer):
    """
    Custom Serializer to support inviting users to an organization
    """

    email = serializers.EmailField(max_length=200, required=True)
    role = serializers.ChoiceField(choices=[(tag.value, tag.value) for tag in RoleChoices])
    first_name = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    last_name = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")

    class Meta:
        fields = (
            "email",
            "role",
            "first_name",
            "last_name"

        )

    def create(self, validated_data):
        org_id = self.context.get("view", {}).kwargs.get("organization_pk")
        role = validated_data.pop("role")
        return add_or_create_user_in_org(org_id=org_id, role=role, user_data=validated_data)

    def update(self, instance, validated_data):
        pass

    def validate_email(self, value):
        """
        Check if the user is already part of the Organization
        """
        email_clean = value.strip().lower()
        try:
            user = User.objects.get(Q(username=email_clean) | Q(email=email_clean))
        except User.DoesNotExist:
            pass  # New user
        else:  # Existent user
            org_id = self.context.get("view", {}).kwargs.get("pk")
            try:  # Check if user belongs to the organization
                is_organization_member = user.accountprofile.organizations.filter(id=org_id).exists()
            except AccountProfile.DoesNotExist:
                is_organization_member = False  # Superusers or other users created through the django admin

            if is_organization_member:
                raise drf_exceptions.ValidationError("The user is already a member of this organization.")

        return email_clean


class OrganizationMemberRetrieveSerializer(serializers.ModelSerializer):
    first_name = serializers.SerializerMethodField()
    last_name = serializers.SerializerMethodField()
    full_name = serializers.SerializerMethodField()
    email = serializers.SerializerMethodField()
    role = serializers.SerializerMethodField()

    class Meta:
        model = AccountProfileOrganization
        fields = (
            "id",
            "first_name",
            "last_name",
            "full_name",
            "email",
            "role",
        )

    def get_first_name(self, obj):
        return obj.accountprofile.user.first_name

    def get_last_name(self, obj):
        return obj.accountprofile.user.last_name

    def get_full_name(self, obj):
        return f"{self.get_first_name(obj)} {self.get_last_name(obj)}"

    def get_email(self, obj):
        return obj.accountprofile.user.email or obj.accountprofile.user.username

    def get_role(self, obj):
        return obj.role


class RemoveMemberSerializer(serializers.Serializer):
    """ Custom Serializer to support bulk removal of members from an organization"""

    member_ids = serializers.ListField(write_only=True, required=True)
    # ToDo: Validate ids?

    def create(self, validated_data):
        pass

    def update(self, instance, validated_data):
        pass


class OrganizationMemberUpdateSerializer(serializers.Serializer):
    role = serializers.CharField(required=False)
    first_name = serializers.CharField(required=False)
    last_name = serializers.CharField(required=False)

    def create(self, validated_data):
        pass

    def update(self, instance, validated_data):
        if "role" in validated_data:
            instance.role = validated_data.pop("role")
            instance.save()
        # The rest of the data goes to the user model
        user = instance.accountprofile.user
        for k, v in validated_data.items():
            setattr(user, k, v)
        user.save()
        return instance


class IntegrationTypeSummarySerializer(serializers.ModelSerializer):

    class Meta:
        model = IntegrationType
        fields = ["id", "name", "value"]


class OwnerSummarySerializer(serializers.ModelSerializer):

    class Meta:
        model = Organization
        fields = ["id", "name", ]


class OwnerSerializer(serializers.ModelSerializer):

    class Meta:
        model = Organization
        fields = ["id", "name", "description"]


class IntegrationActionSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = IntegrationAction
        fields = (
            "id",
            "type",
            "name",
            "value"
        )


class IntegrationActionFullSerializer(serializers.ModelSerializer):
    class Meta:
        model = IntegrationAction
        fields = (
            "id",
            "type",
            "name",
            "value",
            "description",
            "schema",
            "ui_schema"
        )


class IntegrationWebhookSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = IntegrationAction
        fields = (
            "id",
            "name",
            "value"
        )


class IntegrationWebhookFullSerializer(serializers.ModelSerializer):
    class Meta:
        model = IntegrationWebhook
        fields = (
            "id",
            "name",
            "value",
            "description",
            "schema",
            "ui_schema",
        )


class IntegrationWebhookCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = IntegrationWebhook
        fields = (
            "name",
            "value",
            "description",
            "schema",
            "ui_schema",
        )


class IntegrationActionCreateUpdateSerializer(serializers.ModelSerializer):
    crontab_schedule = serializers.JSONField(write_only=True, required=False)

    class Meta:
        model = IntegrationAction
        fields = (
            "type",
            "name",
            "value",
            "description",
            "schema",
            "ui_schema",
            "is_periodic_action",
            "crontab_schedule"
        )


class IntegrationTypeFullSerializer(serializers.ModelSerializer):
    actions = IntegrationActionFullSerializer(many=True, read_only=True)
    webhook = IntegrationWebhookFullSerializer(read_only=True)

    class Meta:
        model = IntegrationType
        fields = (
            "id",
            "name",
            "value",
            "description",
            "actions",
            "webhook",
        )


class IntegrationTypeIdempotentCreateSerializer(serializers.ModelSerializer):
    actions = IntegrationActionCreateUpdateSerializer(many=True, write_only=True)
    webhook = IntegrationWebhookCreateUpdateSerializer(required=False, write_only=True)
    value = serializers.CharField(required=True)
    register_webhook_in_kong = serializers.BooleanField(write_only=True, default=True)

    class Meta:
        model = IntegrationType
        fields = (
            "name",
            "value",
            "description",
            "actions",
            "webhook",
            "register_webhook_in_kong",
            "service_url",
        )

    def validate_value(self, value):
        # Skip uniqueness validation for idempotent creation
        return value

    def validate(self, data):
        """
        Validate the actions or webhook data
        """
        for action_data in data.get("actions", []):
            # ToDo: validate action data?
            if self.instance and "value" in action:  # Update
                action = IntegrationAction.objects.get(integration_type=self, value=action_data["value"])
                serializer = IntegrationActionCreateUpdateSerializer(instance=action, data=action_data)
            else:  # Create
                # Validate the action data
                serializer = IntegrationActionCreateUpdateSerializer(data=action_data)
            serializer.is_valid(raise_exception=True)
        if webhook_data := data.get("webhook"):  # Update
            if self.instance and "value" in webhook_data:
                webhook = IntegrationWebhook.objects.get(integration_type=self, value=webhook_data["value"])
                serializer = IntegrationWebhookCreateUpdateSerializer(instance=webhook, data=webhook_data)
            else:  # Create
                serializer = IntegrationWebhookCreateUpdateSerializer(data=webhook_data)
                serializer.is_valid(raise_exception=True)
        return data

    def create(self, validated_data):
        actions = validated_data.pop("actions", [])
        webhook_data = validated_data.pop("webhook", {})
        register_webhook_in_kong = validated_data.pop("register_webhook_in_kong", True)
        # Create the integration type idempotently
        type_slug = validated_data.pop("value")
        with transaction.atomic():
            integration_type, type_created = IntegrationType.objects.update_or_create(value=type_slug, defaults=validated_data)
            # Create or update actions if provided
            for action_params in actions:  # Usually less than 5 actions
                action_slug = action_params.pop("value")
                if crontab_values := action_params.pop("crontab_schedule", None):
                    crontab_schedule = parse_crontab_schedule_from_dict(crontab_values)
                    action_params["crontab_schedule"] = crontab_schedule
                action, created = IntegrationAction.objects.update_or_create(
                    integration_type=integration_type,
                    value=action_slug,
                    defaults=action_params
                )
            # Create or update webhook if provided
            if webhook_data:
                webhook, webhook_created = IntegrationWebhook.objects.update_or_create(
                    integration_type=integration_type,
                    value=webhook_data.pop("value"),
                    defaults=webhook_data
                )
                # Register the integration type in Kong
                if webhook_created and register_webhook_in_kong:  # Register only once on creation
                    register_integration_type_in_kong(integration_type)

        return integration_type


class IntegrationTypeUpdateSerializer(IntegrationTypeIdempotentCreateSerializer):
    actions = IntegrationActionCreateUpdateSerializer(many=True, required=False, write_only=True)
    webhook = IntegrationWebhookCreateUpdateSerializer(required=False, write_only=True)

    class Meta:
        model = IntegrationType
        fields = (
            "name",
            "value",
            "description",
            "actions",
            "webhook",
            "service_url",
        )

    def update(self, instance, validated_data):
        actions = validated_data.pop("actions", [])
        # Update the integration type
        super().update(instance=instance, validated_data=validated_data)
        # Update or Create nested actions if provided
        for action_data in actions:  # Usually less than 5 actions
            action_data["integration_type"] = self.instance
            IntegrationAction.objects.update_or_create(
                value=action_data.get("value"),
                defaults=action_data
            )
        # Create or update webhook if provided
        if webhook_data := validated_data.get("webhook"):
            webhook, created = IntegrationWebhook.objects.update_or_create(
                integration_type=instance.value,
                value=webhook_data.pop("value"),
                defaults=webhook_data
            )
        return instance


class IntegrationConfigurationRetrieveSerializer(serializers.ModelSerializer):
    action = IntegrationActionSummarySerializer()

    class Meta:
        model = IntegrationConfiguration
        fields = ("id", "integration", "action", "data",)


class WebhookConfigurationRetrieveSerializer(serializers.ModelSerializer):
    webhook = IntegrationWebhookSummarySerializer()

    class Meta:
        model = WebhookConfiguration
        fields = ("id", "integration", "webhook", "data",)


class WebhookConfigurationCreateUpdateSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(required=False, read_only=True)
    integration = serializers.PrimaryKeyRelatedField(required=False, queryset=Integration.objects.all())
    webhook = serializers.PrimaryKeyRelatedField(required=False, queryset=IntegrationWebhook.objects.all())

    class Meta:
        model = WebhookConfiguration
        fields = ["id", "integration", "webhook", "data"]


class RoutingRuleSummarySerializer(serializers.ModelSerializer):

    class Meta:
        model = Route
        fields = ("id", "name")


class IntegrationRetrieveFullSerializer(serializers.ModelSerializer):
    type = IntegrationTypeFullSerializer()
    owner = OwnerSerializer()
    configurations = IntegrationConfigurationRetrieveSerializer(many=True)
    webhook_configuration = WebhookConfigurationRetrieveSerializer()
    default_route = RoutingRuleSummarySerializer(read_only=True)
    status = serializers.SerializerMethodField()
    status_details = serializers.SerializerMethodField()

    class Meta:
        model = Integration
        fields = (
            "id",
            "name",
            "base_url",
            "enabled",
            "type",
            "owner",
            "configurations",
            "webhook_configuration",
            "additional",
            "default_route",
            "status",
            "status_details",
        )

    def get_status(self, obj):
        integration_status, _ = IntegrationStatus.objects.get_or_create(integration=obj)
        return integration_status.status

    def get_status_details(self, obj):
        integration_status, _ = IntegrationStatus.objects.get_or_create(integration=obj)
        return integration_status.status_details


class IntegrationConfigurationCreateUpdateSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(required=False)
    integration = serializers.PrimaryKeyRelatedField(required=False, queryset=Integration.objects.all())
    action = serializers.PrimaryKeyRelatedField(required=False, queryset=IntegrationAction.objects.all())

    class Meta:
        model = IntegrationConfiguration
        fields = ["id", "integration", "action", "data"]


class IntegrationCreateUpdateSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    configurations = IntegrationConfigurationCreateUpdateSerializer(many=True, required=False)
    webhook_configuration = WebhookConfigurationCreateUpdateSerializer(required=False)
    default_route = RoutingRuleSummarySerializer(read_only=True)
    create_default_route = serializers.BooleanField(write_only=True, default=True)
    create_configurations = serializers.BooleanField(write_only=True, default=True)

    class Meta:
        model = Integration
        fields = (
            "id",
            "name",
            "base_url",
            "enabled",
            "type",
            "owner",
            "configurations",
            "webhook_configuration",
            "default_route",
            "create_default_route",
            "create_configurations"
        )

    def validate(self, data):
        """
        Validate the configurations
        """
        for configuration in data.get("configurations", []):
            if self.instance and "id" in configuration:  # Integration Update
                action = IntegrationConfiguration.objects.get(id=configuration["id"]).action
            else:  # Create a new integration or new config
                if "action" not in configuration:
                    raise drf_exceptions.ValidationError("The action id is required.")
                action = configuration["action"]
            configuration_schema = action.schema
            if configuration_schema and not configuration:  # Blank or None
                raise drf_exceptions.ValidationError("The configuration can't be null or empty")
            try:  # Validate schema
                action.validate_configuration(configuration["data"])
            except jsonschema.exceptions.ValidationError as err:
                print(err)
                raise drf_exceptions.ValidationError(detail=f"configuration: {err.message}")
        return data

    def create(self, validated_data):
        configurations = validated_data.pop("configurations", [])
        webhook_configuration = validated_data.pop("webhook_configuration", {})
        create_default_route = validated_data.pop("create_default_route")
        create_configurations = validated_data.pop("create_configurations")
        # Create the integration
        integration = Integration.objects.create(**validated_data)
        # Create configurations if provided
        for configuration in configurations:  # Usually less than 5-10 configs
            IntegrationConfiguration.objects.create(
                integration=integration,
                **configuration
            )
        # Create other missing configurations
        if create_configurations:
            integration.create_missing_configurations()
        # Create a default route as needed
        if create_default_route:
            ensure_default_route(integration=integration)
        # Create webhook configuration if provided
        if webhook_configuration and integration.type.webhook:
            WebhookConfiguration.objects.create(
                integration=integration,
                webhook=integration.type.webhook,
                data=webhook_configuration.get("data", {})
            )
        return integration

    def update(self, instance, validated_data):
        configurations = validated_data.pop("configurations", [])
        webhook_configuration = validated_data.pop("webhook_configuration", {})
        # Update the integration
        super().update(instance=instance, validated_data=validated_data)
        # Update or Create nested configurations if provided
        for config_data in configurations:  # Usually less than 5-10 configs
            config_data["integration"] = self.instance
            IntegrationConfiguration.objects.update_or_create(
                id=config_data.get("id"),
                defaults=config_data
            )
        # Update or Create webhook configuration if provided
        if webhook_configuration and instance.type.webhook:
            WebhookConfiguration.objects.update_or_create(
                integration=self.instance,
                webhook=self.instance.type.webhook,
                defaults={"data": webhook_configuration.get("data", {})}
            )
        return instance


class IntegrationSummarySerializer(serializers.ModelSerializer):
    owner = OwnerSummarySerializer(read_only=True)
    type = IntegrationTypeSummarySerializer(read_only=True)
    status = serializers.SerializerMethodField()
    status_details = serializers.SerializerMethodField()

    class Meta:
        model = Integration
        fields = ("id", "name", "owner", "type", "base_url", "status", "status_details", )

    def get_status(self, obj):
        integration_status, _ = IntegrationStatus.objects.get_or_create(integration=obj)
        return integration_status.status

    def get_status_details(self, obj):
        integration_status, _ = IntegrationStatus.objects.get_or_create(integration=obj)
        return integration_status.status_details


class IntegrationURLSerializer(serializers.ModelSerializer):

    class Meta:
        model = Integration
        fields = ("id", "base_url",)


class IntegrationOwnerSerializer(serializers.ModelSerializer):

    class Meta:
        model = Organization
        fields = ("id", "name", )


class IntegrationApiKeySerializer(serializers.ModelSerializer):
    class Meta:
        model = Integration
        fields = ("api_key", )


class ConnectionRetrieveSerializer(serializers.ModelSerializer):
    id = serializers.SerializerMethodField()
    provider = serializers.SerializerMethodField()
    destinations = serializers.SerializerMethodField()
    routing_rules = serializers.SerializerMethodField()
    default_route = RoutingRuleSummarySerializer(read_only=True)
    owner = OwnerSerializer()
    status = serializers.SerializerMethodField()

    class Meta:
        model = Integration
        fields = (
            "id",
            "provider",
            "destinations",
            "routing_rules",
            "default_route",
            "owner",
            "status"
        )

    def get_id(self, obj):
        return str(obj.id)

    def get_provider(self, obj):
        return IntegrationSummarySerializer(instance=obj).data

    def get_destinations(self, obj):
        return IntegrationSummarySerializer(instance=obj.destinations, many=True).data

    def get_routing_rules(self, obj):
        return RoutingRuleSummarySerializer(instance=obj.routing_rules, many=True).data

    def get_status(self, obj):
        provider_status, _ = IntegrationStatus.objects.get_or_create(integration=obj)
        if provider_status.status == IntegrationStatus.Status.UNHEALTHY.value:
            return ConnectionStatus.UNHEALTHY.value
        if provider_status.status == IntegrationStatus.Status.DISABLED.value:
            return ConnectionStatus.DISABLED.value
        destination_statuses = []
        for destination in obj.destinations.all():
            destination_status, _ = IntegrationStatus.objects.get_or_create(integration=destination)
            destination_statuses.append(destination_status.status)
        if IntegrationStatus.Status.UNHEALTHY.value in destination_statuses:
            return ConnectionStatus.UNHEALTHY.value
        if IntegrationStatus.Status.DISABLED.value in destination_statuses:
            return ConnectionStatus.NEEDS_REVIEW.value
        return ConnectionStatus.HEALTHY.value


class SourceRetrieveSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    status = serializers.SerializerMethodField()
    provider = serializers.SerializerMethodField()
    destinations = serializers.SerializerMethodField()
    routing_rules = serializers.SerializerMethodField()
    update_frequency = serializers.SerializerMethodField()
    last_update = serializers.SerializerMethodField()

    class Meta:
        model = Source
        fields = (
            "id", "external_id", "status", "provider", "destinations", "routing_rules",
            "update_frequency", "last_update", "created_at"
        )

    def get_status(self, obj):
        # ToDo: revisit this once we implement status at the source level
        return "healthy"

    def get_update_frequency(self, obj):
        try:  # ToDo: revisit this once we implement monitoring & troubleshooting
            source_configuration = obj.configuration
        except SourceConfiguration.DoesNotExist:
            return "unknown"
        else:
            return source_configuration.data.get("report_every", "unknown") if source_configuration else "unknown"

    def get_last_update(self, obj):
        try:  # ToDo: revisit this once we implement monitoring & troubleshooting
            source_state = obj.state
        except SourceState.DoesNotExist:
            return "unknown"
        else:
            return source_state.data.get("last_data_received", "unknown") if obj.state else "unknown"

    def get_provider(self, obj):
        return IntegrationSummarySerializer(instance=obj.integration).data

    def get_destinations(self, obj):
        return IntegrationSummarySerializer(instance=obj.integration.destinations, many=True).data

    def get_routing_rules(self, obj):
        return RoutingRuleSummarySerializer(instance=obj.integration.routing_rules, many=True).data


class RouteConfigurationSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)

    class Meta:
        model = RouteConfiguration
        fields = ["id", "name", "data"]


class PKRelatedOrNestedField(serializers.PrimaryKeyRelatedField):
    # This custom field accepts either the id of a related object or a nested serializer
    default_error_messages = {
        'required': _('This field is required.'),
        'does_not_exist': _('Invalid pk "{pk_value}" - object does not exist.'),
        'incorrect_type': _('Incorrect type. Expected pk value, received {data_type}.'),
    }

    def __init__(self, **kwargs):
        self.pk_field = kwargs.pop("pk_field", None)
        self.nested_serializer = kwargs.pop("nested_serializer", None)
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        if isinstance(data, dict):  # It's a nested object
            return self.nested_serializer.to_internal_value(data=data)
        return super().to_internal_value(data=data)  # It's PK Related Field


class RouteCreateUpdateSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    data_providers = serializers.PrimaryKeyRelatedField(many=True, queryset=Integration.objects.all())
    destinations = serializers.PrimaryKeyRelatedField(many=True, queryset=Integration.objects.all())
    configuration = PKRelatedOrNestedField(
        queryset=RouteConfiguration.objects.all(),
        required=False,
        nested_serializer=RouteConfigurationSerializer(required=False)
    )

    class Meta:
        model = Route
        fields = (
            "id",
            "name",
            "owner",
            "data_providers",
            "destinations",
            "configuration",
            "additional",
            # "filters"  # ToDo: Support "filters" or "rules"
        )

    def _validate_integrations_selection(self, integration_ids):
        user = self.context.get("request").user
        if user.is_superuser:  # Superusers can do anything
            return integration_ids
        # Other users can only select integrations within their organizations
        user_managed_integrations = get_user_integrations_qs(user)
        if user_managed_integrations.filter(id__in=[i.id for i in integration_ids]).count() != len(integration_ids):
            raise drf_exceptions.ValidationError(
                detail=f"You don't have enough privileges in at least one of the selected destinations"
            )
        return integration_ids

    def validate_data_providers(self, value):
        # Check if the user is allowed to manage the selected data providers
        return self._validate_integrations_selection(integration_ids=value)

    def validate_destinations(self, value):
        # Check if the user is allowed to manage the selected destinations
        return self._validate_integrations_selection(integration_ids=value)

    def validate_configuration(self, value):
        # We support sending an id or a nested configuration object
        if isinstance(value, dict):
            # Create the configuration
            configuration = RouteConfigurationSerializer(data=value)
            configuration.is_valid()
            configuration.save()
            return configuration.instance
        return value


class RouteRetrieveFullSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    data_providers = IntegrationSummarySerializer(many=True)
    destinations = IntegrationSummarySerializer(many=True)
    configuration = RouteConfigurationSerializer()

    class Meta:
        model = Route
        fields = (
            "id",
            "name",
            "owner",
            "data_providers",
            "destinations",
            "configuration",
            "additional",
            # "filters"  # ToDo: Support "filters" or "rules"
        )


class KeyRelatedField(serializers.RelatedField):
    """
    Similar to a PKRelatedField but supports using any other non-unique column as related key.
    If there are many related objects it returns the first one.
    """
    default_error_messages = {
        'required': _('This field is required.'),
        'does_not_exist': _('Invalid key "{key_value}" - object does not exist.'),
        'incorrect_type': _('Incorrect type. Expected uuid value, received {data_type}.'),
    }

    def __init__(self, **kwargs):
        self.key_field = kwargs.pop('key_field', None)
        assert self.key_field is not None, 'The `key_field` argument is required.'
        super().__init__(**kwargs)

    def use_pk_only_optimization(self):
        return True

    def to_internal_value(self, data):
        data = self.key_field.to_internal_value(data)
        try:
            related_object = self.get_queryset().filter(**{self.key_field: data}).first()
        except (TypeError, ValueError):
            self.fail('incorrect_type', data_type=type(data).__name__)
        else:
            if not related_object:
                self.fail('does_not_exist', key_value=data)
            return related_object

    def to_representation(self, value):
        return getattr(value, self.key_field)


class GundiTraceSerializer(serializers.Serializer):
    object_id = serializers.UUIDField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True, source="object_updated_at")
    related_to = KeyRelatedField(
        key_field="object_id",
        write_only=True,
        required=False,
        queryset=GundiTrace.objects.all()
    )
    integration = serializers.PrimaryKeyRelatedField(
        write_only=True,
        required=False,
        queryset=Integration.objects.all()
    )
    source = serializers.CharField(
        write_only=True,
        default="default-source"
    )

    def validate(self, data):
        # Check the integration id
        request = self.context["request"]
        if integration := data.get("integration"):
            if not request.integration_id or request.integration_id != str(integration.id):
                raise drf_exceptions.ValidationError(detail=f"Your API Key is not authorized for the integration_id")
        elif request.integration_id:
            try:
                data["integration"] = Integration.objects.get(id=request.integration_id)
            except Integration.DoesNotExist:
                raise drf_exceptions.ValidationError(detail=f"Cannot find the integration associated with this API Key.")
        else:
            raise drf_exceptions.ValidationError(detail=f"This API Key isn't associated with an integration.")
        return data


class EventBulkCreateUpdateSerializer(serializers.ListSerializer):
    """
    Custom Serializer to support bulk creation of events
    """

    def create(self, validated_data):
        events = [self.child.create(attrs) for attrs in validated_data]
        try:
            new_events = GundiTrace.objects.bulk_create(events)
        except IntegrityError as e:
            raise drf_exceptions.ValidationError(e)
        else:
            # Publish messages to a topic to be processed by routing services
            event_ids = [str(event.object_id) for event in new_events]
            send_events_to_routing(
                events=validated_data,
                gundi_ids=event_ids
            )
        return new_events

    def update(self, instance, validated_data):
        pass


class EventCreateUpdateSerializer(GundiTraceSerializer):
    object_type = serializers.HiddenField(default=StreamPrefixEnum.event.value)
    title = serializers.CharField(write_only=True, required=False)
    recorded_at = serializers.DateTimeField(write_only=True)
    location = serializers.JSONField(write_only=True, required=False)
    geometry = serializers.JSONField(write_only=True, required=False)
    event_type = serializers.CharField(write_only=True, required=False)
    event_details = serializers.JSONField(write_only=True, required=False)
    annotations = serializers.JSONField(write_only=True, required=False)
    status = serializers.CharField(write_only=True, required=False)

    class Meta:
        list_serializer_class = EventBulkCreateUpdateSerializer

    def validate_location(self, value):
        # I must contain lat and lon and other extra fields are accepted
        if "lat" not in value or "lon" not in value:
            raise drf_exceptions.ValidationError(detail=f"'location' requires 'lat' and 'lon'.")
        return value

    def validate_geometry(self, value):
        # ToDo: Validate that it's a valid geojson
        return value

    def create(self, validated_data):
        user = self.context["request"].user
        # Store the user when possible. API Key authenticated requests are not related to a user
        created_by = user if user and not user.is_anonymous else None
        # Don't save to the DB if it's a bulk create
        instance = GundiTrace(
            # We save only IDs, no sensitive data is saved
            data_provider=validated_data["integration"],
            related_to=validated_data.get("related_to"),
            source=validated_data["source"],
            object_type=validated_data["object_type"],
            created_by=created_by
            # Other fields are filled in later by the routing services
        )
        # Save if it's a single object create request
        if isinstance(self._kwargs["data"], dict):
            instance.save()
            send_events_to_routing(
                events=[validated_data],
                gundi_ids=[str(instance.object_id)]
            )
        return instance

    def validate(self, data):
        data = super().validate(data)
        # Get or create sources as they are discovered
        if not self.instance:
            source, created = Source.objects.get_or_create(
                integration=data["integration"],
                external_id=data.get("source", "default-source")
            )
            data["source"] = source
        return data

    def update(self, traces, validated_data):
        trace = traces.first()  # For the user it's a single update
        # Add a timestamp to all the traces in case of multiple destinations
        traces.update(object_updated_at=datetime.now(tz=trace.created_at.tzinfo))
        # Routing services take care of sending updates for each destination as needed
        send_event_update_to_routing(
            event_trace=trace,
            event_changes=validated_data
        )
        return trace


class ObservationBulkCreateSerializer(serializers.ListSerializer):
    """
    Custom Serializer to support bulk creation of observations
    """

    def create(self, validated_data):
        observations = [self.child.create(attrs) for attrs in validated_data]
        try:
            new_observations = GundiTrace.objects.bulk_create(observations)
        except IntegrityError as e:
            raise drf_exceptions.ValidationError(e)
        else:
            # Publish messages to a topic to be processed by routing services
            observation_ids = [str(event.object_id) for event in new_observations]
            send_observations_to_routing(
                observations=validated_data,
                gundi_ids=observation_ids
            )
        return new_observations

    def update(self, instance, validated_data):
        pass


class ObservationCreateSerializer(GundiTraceSerializer):
    object_type = serializers.HiddenField(default=StreamPrefixEnum.observation.value)
    type = serializers.CharField(write_only=True, required=False)
    subject_type = serializers.CharField(write_only=True, required=False)
    source_name = serializers.CharField(write_only=True, required=False)
    recorded_at = serializers.DateTimeField(write_only=True)
    location = serializers.JSONField(write_only=True, required=True)
    additional = serializers.JSONField(write_only=True, required=False)
    annotations = serializers.JSONField(write_only=True, required=False)

    class Meta:
        list_serializer_class = ObservationBulkCreateSerializer

    def validate_location(self, value):
        # I must contain lat and lon and other extra fields are accepted
        if "lat" not in value or "lon" not in value:
            raise drf_exceptions.ValidationError(detail=f"'location' requires 'lat' and 'lon'.")
        return value

    def create(self, validated_data):
        user = self.context["request"].user
        # Store the user when possible. API Key authenticated requests are not related to a user
        created_by = user if user and not user.is_anonymous else None
        # Don't save to the DB if it's a bulk create
        instance = GundiTrace(
            # We save only IDs, no sensitive data is saved
            data_provider=validated_data["integration"],
            related_to=validated_data.get("related_to"),
            source=validated_data["source"],
            object_type=validated_data["object_type"],
            created_by=created_by
            # Other fields are filled in later by the routing services
        )
        # Save if it's a single object create request
        if isinstance(self._kwargs["data"], dict):
            instance.save()
            send_observations_to_routing(
                observations=[validated_data],
                gundi_ids=[str(instance.object_id)]
            )
        return instance

    def validate(self, data):
        data = super().validate(data)
        # Get or create sources as they are discovered
        source, created = Source.objects.get_or_create(
            integration=data["integration"],
            external_id=data.get("source", "default-source"),
            defaults={
                "name": data.get("source_name", "")
            }
        )
        data["source"] = source
        return data

    def update(self, instance, validated_data):
        pass  # ToDo: Implement if we decide to support updating tracking data


class EventAttachmentListSerializer(serializers.ListSerializer):
    """
    Custom Serializer to support bulk creation of events
    """

    def create(self, validated_data):
        attachments = [
            self.child.create(data) for data in validated_data
        ]

        try:  # Write to the database
            new_attachments = GundiTrace.objects.bulk_create(attachments)
        except IntegrityError as e:
            raise drf_exceptions.ValidationError(e)
        else:
            attachment_ids = [str(att.object_id) for att in new_attachments]
            # Publish messages to a topic to be processed by routing services
            send_attachments_to_routing(
                attachments_data=validated_data,
                gundi_ids=attachment_ids
            )
            return new_attachments

    def update(self, instance, validated_data):
        pass


class EventAttachmentSerializer(GundiTraceSerializer):
    source = serializers.CharField(
        write_only=True,
        required=False,
    )
    file = serializers.FileField(write_only=True)
    integration = serializers.PrimaryKeyRelatedField(
        write_only=True,
        required=False,
        queryset=Integration.objects.all()
    )

    class Meta:
        list_serializer_class = EventAttachmentListSerializer

    def create(self, validated_data):
        user = self.context["request"].user
        created_by = user if user and not user.is_anonymous else None
        # Don't save to teh DB if it's a bulk create
        instance = GundiTrace(
            # We save only IDs, no sensitive data is saved
            data_provider=validated_data.get("integration"),
            related_to=validated_data.get("related_to"),
            object_type=StreamPrefixEnum.attachment.value,
            created_by=created_by
            # Other fields are filled in later by the routing services
        )
        # Save if it's a single object create request
        if isinstance(self._kwargs["data"], dict):
            instance.save()
            send_attachments_to_routing(
                attachments_data=[validated_data],
                gundi_ids=[str(instance.object_id)]
            )
        return instance

    def validate(self, data):
        data = super().validate(data)
        if not data.get("related_to"):
            # Relate the attachment to the current event
            data["related_to"] = GundiTrace.objects.filter(
                object_id=self.context["view"].kwargs["event_pk"]
            ).first().object_id
        # ToDo: Get source from id from the related event?
        return data


class GundiTraceRetrieveSerializer(serializers.Serializer):
    object_id = serializers.UUIDField(read_only=True)
    object_type = serializers.CharField(read_only=True)
    related_to = serializers.UUIDField(read_only=True)
    data_provider = serializers.PrimaryKeyRelatedField(
        read_only=True,
    )
    destination = serializers.PrimaryKeyRelatedField(
        read_only=True,
    )
    delivered_at = serializers.DateTimeField(read_only=True)
    last_update_delivered_at = serializers.DateTimeField(read_only=True)
    external_id = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True, source="object_updated_at")
    is_duplicate = serializers.BooleanField(read_only=True)
    has_error = serializers.BooleanField(read_only=True)


class ActivityLogRetrieveSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    log_level = serializers.IntegerField(read_only=True)
    log_type = serializers.CharField(read_only=True)
    origin = serializers.CharField(read_only=True)
    integration = IntegrationSummarySerializer(read_only=True)
    value = serializers.CharField(read_only=True)
    title = serializers.CharField(read_only=True)
    created_by = UserDetailsRetrieveSerializer(read_only=True)
    details = serializers.JSONField(read_only=True)
    is_reversible = serializers.BooleanField(read_only=True)
    revert_data = serializers.JSONField(read_only=True)


class ActionTriggerSerializer(serializers.Serializer):
    run_in_background = serializers.BooleanField(required=False, default=False)
    config_overrides = serializers.JSONField(required=False)


class UserAgreementSerializer(serializers.ModelSerializer):
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())
    eula = serializers.HiddenField(default=EULA.objects.get_active_eula)
    accept = serializers.BooleanField(read_only=True)
    date_accepted = serializers.DateTimeField(read_only=True)

    class Meta:
        model = UserAgreement
        fields = (
            "user",
            "eula",
            "accept",
            "date_accepted",
        )

    def get_unique_together_validators(self):
        # Overriden to disable unique together check as it's handled in the create method
        return []

    def create(self, validated_data):
        # Creates the user agreement in a idempotent way
        agreement, created = UserAgreement.objects.update_or_create(
            user=validated_data["user"],
            eula=validated_data["eula"],
            defaults={"accept": True}
        )
        return agreement


class EULARetrieveSerializer(serializers.ModelSerializer):
    accepted = serializers.SerializerMethodField()

    class Meta:
        model = EULA
        fields = (
            "version",
            "eula_url",
            "accepted"
        )

    def get_accepted(self, obj):
        try:
            user = self.context["request"].user
            agreement = UserAgreement.objects.get(user=user, eula=EULA.objects.get_active_eula())
        except UserAgreement.DoesNotExist as e:
            return False
        else:
            return agreement.accept
