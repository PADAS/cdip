import jsonschema
from rest_framework import serializers
from rest_framework import exceptions as drf_exceptions
from core.enums import RoleChoices
from accounts.utils import add_or_create_user_in_org
from accounts.models import AccountProfileOrganization, AccountProfile
from integrations.models import IntegrationConfiguration, IntegrationType, IntegrationAction, Integration, RoutingRule
from organizations.models import Organization
from django.contrib.auth import get_user_model
from django.db.models import Q


User = get_user_model()


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


class IntegrationConfigurationSerializer(serializers.ModelSerializer):
    action = IntegrationActionSummarySerializer()

    class Meta:
        model = IntegrationConfiguration
        fields = ["id", "integration", "action", "data"]


class IntegrationRetrieveFullSerializer(serializers.ModelSerializer):
    type = IntegrationTypeFullSerializer()
    owner = OwnerSerializer()
    configurations = IntegrationConfigurationSerializer(many=True)
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


class IntegrationCreateUpdateSerializer(serializers.ModelSerializer):
    type = IntegrationTypeSummarySerializer()
    owner = OwnerSerializer()
    configurations = IntegrationConfigurationSerializer(many=True)

    class Meta:
        model = Integration
        fields = (
            "id",
            "name",
            "base_url",
            "enabled",
            "type",
            "owner",
            "configurations"
        )

    def validate(self, data):
        """
        Validate the configuration schema
        """
        destination_type = data["type"]
        configuration_schema = destination_type.dest_configuration_schema
        configuration = data["configuration"]
        if configuration_schema and not configuration:  # Blank or None
            raise drf_exceptions.ValidationError("The configuration can't be null or empty")

        try:  # Validate schema
            jsonschema.validate(instance=configuration, schema=configuration_schema)
        except jsonschema.exceptions.ValidationError as err:
            print(err)
            raise drf_exceptions.ValidationError(detail=f"configuration: {err.message}")
        return data


class IntegrationSummarySerializer(serializers.ModelSerializer):

    class Meta:
        model = Integration
        fields = ("id", "name", "base_url", )


class RoutingRuleSummarySerializer(serializers.ModelSerializer):

    class Meta:
        model = RoutingRule
        fields = ("id", "name")


class ConnectionRetrieveSerializer(serializers.ModelSerializer):
    id = serializers.SerializerMethodField()
    provider = serializers.SerializerMethodField()
    destinations = serializers.SerializerMethodField()
    routing_rules = serializers.SerializerMethodField()
    owner = OwnerSerializer()
    status = serializers.SerializerMethodField()

    class Meta:
        model = Integration
        fields = (
            "id",
            "provider",
            "destinations",
            "routing_rules",
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
