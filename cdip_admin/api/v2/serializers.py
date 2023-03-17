from rest_framework import serializers
from rest_framework import exceptions as drf_exceptions
from core.enums import RoleChoices
from accounts.utils import add_or_create_user_in_org
from accounts.models import AccountProfileOrganization
from organizations.models import Organization
from django.contrib.auth import get_user_model


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
            user = User.objects.get(email=email_clean)
        except User.DoesNotExist:
            pass  # New user
        else:  # Existent user
            org_id = self.context.get("view", {}).kwargs.get("pk")
            is_organization_member = user.accountprofile.organizations.filter(id=org_id).exists()
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
        return obj.accountprofile.user.email

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
