from rest_framework import serializers
from rest_framework import exceptions as drf_exceptions
from core.enums import RoleChoices
from accounts.utils import add_or_create_user_in_org
from django.contrib.auth import get_user_model

User = get_user_model()

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
        org_id = self.context.get("view", {}).kwargs.get("pk")
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
