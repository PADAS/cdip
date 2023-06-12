import base64
import json
from django.utils.deprecation import MiddlewareMixin


class ApiIntegrationIdMiddleware(MiddlewareMixin):
    """
    This middleware looks for headers with extra info, previously injected by kong/key-auth,
    and sets the integration id in the request.
    Available headers:
    'HTTP_X_CONSUMER_ID'
    'HTTP_X_CONSUMER_CUSTOM_ID'
    'HTTP_X_CONSUMER_USERNAME'
    'HTTP_X_CREDENTIAL_IDENTIFIER'
    """

    def process_request(self, request):
        # Try to get the integration id from the username header
        if consumer_username := request.META.get("HTTP_X_CONSUMER_USERNAME"):
            # 'integration:17e7a1e0-168b-4f68-9392-35ec29222f13'
            request.integration_id = consumer_username.split(":")[-1]
        # Try to get it from the consumer custom id
        elif encoded_custom_id := request.META.get("HTTP_X_CONSUMER_CUSTOM_ID"):
            payload = base64.b64decode(encoded_custom_id)
            side_data = json.loads(payload)
            request.integration_id = side_data["integration_ids"][0]
