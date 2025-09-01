import pytest
from unittest.mock import Mock, patch
from django.test import RequestFactory
from rest_framework.test import APIRequestFactory
from rest_framework import serializers
from api.v2.serializers import GundiTraceSerializer, EventCreateUpdateSerializer
from integrations.models import Integration, GundiTrace
from django.contrib.auth.models import AnonymousUser
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.django_db
class TestGundiTraceSerializerFields:
    """Test that GundiTraceSerializer fields are rendered correctly"""

    def test_get_fields_returns_char_fields_for_integration_and_related_to(self):
        """Test that integration and related_to fields are CharField instances"""
        factory = APIRequestFactory()
        request = factory.get('/')
        request.user = AnonymousUser()
        
        serializer = GundiTraceSerializer(context={'request': request})
        fields = serializer.get_fields()
        
        # Check that integration field is a CharField
        assert isinstance(fields['integration'], serializers.CharField)
        assert fields['integration'].write_only is True
        assert fields['integration'].required is False
        assert fields['integration'].help_text == "Integration ID (UUID)"
        
        # Check that related_to field is a CharField
        assert isinstance(fields['related_to'], serializers.CharField)
        assert fields['related_to'].write_only is True
        assert fields['related_to'].required is False
        assert fields['related_to'].help_text == "Related GundiTrace ID (UUID)"

    def test_get_fields_with_authenticated_user_still_returns_char_fields(self):
        """Test that even authenticated users get CharField instances (current behavior)"""
        factory = APIRequestFactory()
        request = factory.get('/')
        user = User.objects.create_user(username='testuser', email='test@example.com')
        request.user = user
        
        serializer = GundiTraceSerializer(context={'request': request})
        fields = serializer.get_fields()
        
        # Should still be CharField instances (current implementation)
        assert isinstance(fields['integration'], serializers.CharField)
        assert isinstance(fields['related_to'], serializers.CharField)

    def test_serializer_has_expected_base_fields(self):
        """Test that the serializer has all expected base fields"""
        factory = APIRequestFactory()
        request = factory.get('/')
        request.user = AnonymousUser()
        
        serializer = GundiTraceSerializer(context={'request': request})
        fields = serializer.get_fields()
        
        # Check base fields exist
        assert 'object_id' in fields
        assert 'created_at' in fields
        assert 'updated_at' in fields
        assert 'source' in fields
        assert 'integration' in fields
        assert 'related_to' in fields
        
        # Check field types
        assert isinstance(fields['object_id'], serializers.UUIDField)
        assert isinstance(fields['created_at'], serializers.DateTimeField)
        assert isinstance(fields['updated_at'], serializers.DateTimeField)
        assert isinstance(fields['source'], serializers.CharField)


@pytest.mark.django_db
class TestGundiTraceSerializerValidation:
    """Test that GundiTraceSerializer validation works correctly"""

    def test_validate_with_integration_string_id(self, provider_trap_tagger):
        """Test validation when integration is provided as a string ID"""
        factory = APIRequestFactory()
        request = factory.post('/')
        request.user = AnonymousUser()
        request.integration_id = str(provider_trap_tagger.id)
        
        serializer = GundiTraceSerializer(context={'request': request})
        
        # Test with integration as string ID
        data = {
            'integration': str(provider_trap_tagger.id),
            'source': 'test-source'
        }
        
        validated_data = serializer.validate(data)
        
        # Should convert string ID to Integration object
        assert isinstance(validated_data['integration'], Integration)
        assert validated_data['integration'].id == provider_trap_tagger.id

    def test_validate_with_integration_object(self, provider_trap_tagger):
        """Test validation when integration is provided as an object"""
        factory = APIRequestFactory()
        request = factory.post('/')
        request.user = AnonymousUser()
        request.integration_id = str(provider_trap_tagger.id)
        
        serializer = GundiTraceSerializer(context={'request': request})
        
        # Test with integration as object
        data = {
            'integration': provider_trap_tagger,
            'source': 'test-source'
        }
        
        validated_data = serializer.validate(data)
        
        # Should keep the Integration object
        assert isinstance(validated_data['integration'], Integration)
        assert validated_data['integration'].id == provider_trap_tagger.id

    def test_validate_without_integration_uses_request_integration_id(self, provider_trap_tagger):
        """Test validation when no integration provided but request has integration_id"""
        factory = APIRequestFactory()
        request = factory.post('/')
        request.user = AnonymousUser()
        request.integration_id = str(provider_trap_tagger.id)
        
        serializer = GundiTraceSerializer(context={'request': request})
        
        data = {
            'source': 'test-source'
        }
        
        validated_data = serializer.validate(data)
        
        # Should use integration from request.integration_id
        assert isinstance(validated_data['integration'], Integration)
        assert validated_data['integration'].id == provider_trap_tagger.id

    def test_validate_unauthorized_integration_raises_error(self, provider_trap_tagger):
        """Test validation fails when integration is not authorized"""
        factory = APIRequestFactory()
        request = factory.post('/')
        request.user = AnonymousUser()
        request.integration_id = str(provider_trap_tagger.id)
        
        serializer = GundiTraceSerializer(context={'request': request})
        
        # Create another integration
        other_integration = Integration.objects.create(
            name="Other Integration",
            type=provider_trap_tagger.type,
            owner=provider_trap_tagger.owner
        )
        
        data = {
            'integration': str(other_integration.id),
            'source': 'test-source'
        }
        
        with pytest.raises(serializers.ValidationError) as exc_info:
            serializer.validate(data)
        
        assert "Your API Key is not authorized for the integration_id" in str(exc_info.value)

    def test_validate_invalid_integration_id_raises_error(self, provider_trap_tagger):
        """Test validation fails when integration ID is invalid"""
        factory = APIRequestFactory()
        request = factory.post('/')
        request.user = AnonymousUser()
        # Use a valid UUID for request.integration_id so Django doesn't fail
        request.integration_id = str(provider_trap_tagger.id)
        
        serializer = GundiTraceSerializer(context={'request': request})
        
        data = {
            'integration': 'invalid-uuid',
            'source': 'test-source'
        }
        
        with pytest.raises(serializers.ValidationError) as exc_info:
            serializer.validate(data)
        
        # The actual error message includes the invalid ID
        assert "Invalid integration ID: invalid-uuid" in str(exc_info.value)

    def test_validate_no_integration_and_no_request_integration_id_raises_error(self):
        """Test validation fails when no integration provided and no request.integration_id"""
        factory = APIRequestFactory()
        request = factory.post('/')
        request.user = AnonymousUser()
        request.integration_id = None
        
        serializer = GundiTraceSerializer(context={'request': request})
        
        data = {
            'source': 'test-source'
        }
        
        with pytest.raises(serializers.ValidationError) as exc_info:
            serializer.validate(data)
        
        assert "This API Key isn't associated with an integration" in str(exc_info.value)

    def test_validate_nonexistent_request_integration_id_raises_error(self):
        """Test validation fails when request.integration_id is valid UUID but integration doesn't exist"""
        import uuid
        factory = APIRequestFactory()
        request = factory.post('/')
        request.user = AnonymousUser()
        # Use a valid UUID format that doesn't exist in the database
        request.integration_id = str(uuid.uuid4())
        
        serializer = GundiTraceSerializer(context={'request': request})
        
        data = {
            'source': 'test-source'
        }
        
        with pytest.raises(serializers.ValidationError) as exc_info:
            serializer.validate(data)
        
        # The actual error message from the serializer when integration doesn't exist
        assert "Cannot find the integration associated with this API Key." in str(exc_info.value)


@pytest.mark.django_db
class TestEventCreateUpdateSerializer:
    """Test that EventCreateUpdateSerializer inherits correctly from GundiTraceSerializer"""

    def test_event_serializer_has_gunditrace_fields(self):
        """Test that EventCreateUpdateSerializer has all GundiTraceSerializer fields"""
        factory = APIRequestFactory()
        request = factory.get('/')
        request.user = AnonymousUser()
        
        serializer = EventCreateUpdateSerializer(context={'request': request})
        fields = serializer.get_fields()
        
        # Should have all GundiTraceSerializer fields
        assert 'object_id' in fields
        assert 'created_at' in fields
        assert 'updated_at' in fields
        assert 'source' in fields
        assert 'integration' in fields
        assert 'related_to' in fields
        
        # Should have event-specific fields
        assert 'object_type' in fields
        assert 'title' in fields
        assert 'recorded_at' in fields
        assert 'location' in fields
        assert 'geometry' in fields
        assert 'event_type' in fields
        assert 'event_details' in fields
        assert 'annotations' in fields
        assert 'status' in fields

    def test_event_serializer_integration_field_is_char_field(self):
        """Test that EventCreateUpdateSerializer integration field is CharField"""
        factory = APIRequestFactory()
        request = factory.get('/')
        request.user = AnonymousUser()
        
        serializer = EventCreateUpdateSerializer(context={'request': request})
        fields = serializer.get_fields()
        
        # Should be CharField like parent class
        assert isinstance(fields['integration'], serializers.CharField)
        assert fields['integration'].help_text == "Integration ID (UUID)"

    def test_event_serializer_related_to_field_is_char_field(self):
        """Test that EventCreateUpdateSerializer related_to field is CharField"""
        factory = APIRequestFactory()
        request = factory.get('/')
        request.user = AnonymousUser()
        
        serializer = EventCreateUpdateSerializer(context={'request': request})
        fields = serializer.get_fields()
        
        # Should be CharField like parent class
        assert isinstance(fields['related_to'], serializers.CharField)
        assert fields['related_to'].help_text == "Related GundiTrace ID (UUID)"


@pytest.mark.django_db
class TestBackwardCompatibility:
    """Test that the changes maintain backward compatibility"""

    def test_serializer_can_handle_missing_context(self):
        """Test that serializer works when no context is provided"""
        serializer = GundiTraceSerializer()
        fields = serializer.get_fields()
        
        # Should still have all expected fields
        assert 'integration' in fields
        assert 'related_to' in fields
        assert isinstance(fields['integration'], serializers.CharField)
        assert isinstance(fields['related_to'], serializers.CharField)

    def test_serializer_can_handle_missing_request_in_context(self):
        """Test that serializer works when context has no request"""
        serializer = GundiTraceSerializer(context={})
        fields = serializer.get_fields()
        
        # Should still have all expected fields
        assert 'integration' in fields
        assert 'related_to' in fields
        assert isinstance(fields['integration'], serializers.CharField)
        assert isinstance(fields['related_to'], serializers.CharField)

    def test_serializer_can_handle_request_without_user(self):
        """Test that serializer works when request has no user"""
        factory = APIRequestFactory()
        request = factory.get('/')
        # Don't set request.user
        
        serializer = GundiTraceSerializer(context={'request': request})
        fields = serializer.get_fields()
        
        # Should still have all expected fields
        assert 'integration' in fields
        assert 'related_to' in fields
        assert isinstance(fields['integration'], serializers.CharField)
        assert isinstance(fields['related_to'], serializers.CharField)
