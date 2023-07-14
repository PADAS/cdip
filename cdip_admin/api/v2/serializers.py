import jsonschema
from rest_framework import serializers
from rest_framework import exceptions as drf_exceptions
from core.enums import RoleChoices
from accounts.utils import add_or_create_user_in_org
from accounts.models import AccountProfileOrganization, AccountProfile
from integrations.models import IntegrationConfiguration, IntegrationType, IntegrationAction, Integration, Route, \
    Source, SourceState, SourceConfiguration, ensure_default_route, RouteConfiguration, get_user_integrations_qs, \
    GundiTrace
from organizations.models import Organization
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from django.db import IntegrityError
from django.core.exceptions import ObjectDoesNotExist
from gundi_core.schemas.v2 import StreamPrefixEnum
from .utils import send_events_to_routing, send_attachments_to_routing

User = get_user_model()


class UserDetailsRetrieveSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "email",
            "full_name",
            "is_superuser"
        )

    def get_full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}".strip().capitalize()


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
        fields = ["id", "name"]


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
            "schema"
        )


class IntegrationTypeFullSerializer(serializers.ModelSerializer):
    actions = IntegrationActionFullSerializer(many=True)

    class Meta:
        model = IntegrationType
        fields = (
            "id",
            "name",
            "description",
            "actions"
        )


class IntegrationConfigurationRetrieveSerializer(serializers.ModelSerializer):
    action = IntegrationActionSummarySerializer()

    class Meta:
        model = IntegrationConfiguration
        fields = ["id", "integration", "action", "data"]


class RoutingRuleSummarySerializer(serializers.ModelSerializer):

    class Meta:
        model = Route
        fields = ("id", "name")


class IntegrationRetrieveFullSerializer(serializers.ModelSerializer):
    type = IntegrationTypeFullSerializer()
    owner = OwnerSerializer()
    configurations = IntegrationConfigurationRetrieveSerializer(many=True)
    default_route = RoutingRuleSummarySerializer(read_only=True)
    status = serializers.SerializerMethodField()

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
            "additional",
            "default_route",
            "status"
        )

    def get_status(self, obj):
        # ToDo: Review this after implenting events related to health status
        return {
            "id": "mockid-b16a-4dbd-ad32-197c58aeef59",
            "is_healthy": True,
            "details": "Last observation has been delivered with success.",
            "observation_delivered_24hrs": 50231,
            "last_observation_delivered_at": "2023-03-31T11:20:00+0200"
        }


class IntegrationConfigurationCreateSerializer(serializers.ModelSerializer):
    action = serializers.PrimaryKeyRelatedField(queryset=IntegrationAction.objects.all())

    class Meta:
        model = IntegrationConfiguration
        fields = ["action", "data"]


class IntegrationCreateUpdateSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    configurations = IntegrationConfigurationCreateSerializer(many=True, required=False)
    default_route = RoutingRuleSummarySerializer(read_only=True)
    create_default_route = serializers.BooleanField(default=True)

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
            "default_route",
            "create_default_route"
        )

    def validate(self, data):
        """
        Validate the configurations
        """
        for configuration in data.get("configurations", []):
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
        configurations = validated_data.pop("configurations")
        create_default_route = validated_data.pop("create_default_route")
        # Create the integration
        integration = Integration.objects.create(**validated_data)
        # Create configurations if provided
        for configuration in configurations:
            IntegrationConfiguration.objects.create(
                integration=integration,
                **configuration
            )
        # Create a default route as needed
        if create_default_route:
            ensure_default_route(integration=integration)
        return integration

    # ToDo. Support updates with nested configurations too?


class IntegrationSummarySerializer(serializers.ModelSerializer):
    type = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()

    class Meta:
        model = Integration
        fields = ("id", "name", "type", "base_url", "status", )

    def get_type(self, obj):
        return obj.type.value

    def get_status(self, obj):
        # ToDo: revisit this once we implement monitoring & troubleshooting
        return "healthy"


class IntegrationURLSerializer(serializers.ModelSerializer):

    class Meta:
        model = Integration
        fields = ("id", "base_url",)


class IntegrationOwnerSerializer(serializers.ModelSerializer):

    class Meta:
        model = Organization
        fields = ("id", "name", )


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
        # ToDo: Review this after remodeling configurations
        return "healthy"


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
            "update_frequency", "last_update",
        )

    def get_status(self, obj):
        # ToDo: revisit this once we implement monitoring & troubleshooting
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
        required=True,
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


class EventBulkCreateSerializer(serializers.ListSerializer):
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


class EventCreateSerializer(GundiTraceSerializer):
    object_type = serializers.HiddenField(default=StreamPrefixEnum.event.value)
    title = serializers.CharField(write_only=True, required=False)
    recorded_at = serializers.DateTimeField(write_only=True)
    location = serializers.JSONField(write_only=True, required=False)
    geometry = serializers.JSONField(write_only=True, required=False)
    event_type = serializers.CharField(write_only=True, required=False)
    event_details = serializers.JSONField(write_only=True, required=False)
    annotations = serializers.JSONField(write_only=True, required=False)

    class Meta:
        list_serializer_class = EventBulkCreateSerializer

    def validate_integration(self, value):
        # ToDo: How do we get the integration id injected based on the API Key being used
        # ToDo: Check that the user is allowed to see that integration
        # user = self.context["request"].user
        return value

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
        # Validate that either location or geometry is provided
        if not ("location" in data or "geometry" in data):
            raise drf_exceptions.ValidationError(detail=f"You must provide 'location' or 'geometry'")
        # Get or create sources as they are discovered
        source, created = Source.objects.get_or_create(
            integration=data["integration"],
            external_id=data["source"]
        )
        data["source"] = source
        return data

    def update(self, instance, validated_data):
        pass  # ToDo: Implement once we support updating events


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
    external_id = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)
