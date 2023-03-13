import logging
import requests
from django.http import JsonResponse
from django.contrib.auth.models import User, Group
from django.core.exceptions import SuspiciousOperation
from core.enums import DjangoGroups
from cdip_admin import settings
from core.utils import get_admin_access_token
from .models import AccountProfile, AccountProfileOrganization


KEYCLOAK_SERVER = settings.KEYCLOAK_SERVER
KEYCLOAK_REALM = settings.KEYCLOAK_REALM
KEYCLOAK_CLIENT = settings.KEYCLOAK_CLIENT_ID

KEYCLOAK_ADMIN_API = f"{KEYCLOAK_SERVER}/auth/admin/realms/{KEYCLOAK_REALM}/"

logger = logging.getLogger(__name__)


def add_account(user):

    url = KEYCLOAK_ADMIN_API + "users"

    token = get_admin_access_token()

    if not token:
        logger.warning("Cannot get a valid access_token.")
        response = JsonResponse({"message": "You don't have access to this resource"})
        response.status_code = 403
        return response

    headers = {
        "authorization": f"{token['token_type']} {token['access_token']}",
        "Content-type": "application/json",
    }
    # Prepare the payload in the format expected by keycloak
    user_data = {
        "email": user["email"],
        "firstName": user["first_name"],
        "lastName": user["last_name"],
        "enabled": True  # Enable user in keycloak
    }
    response = requests.post(url=url, headers=headers, json=user_data)

    if response.ok:
        logger.info(f"User created successfully")
    elif response.status_code == 409:
        logger.info(f'Keycloak user {user["email"]} already exists.')
    else:
        logger.error(f"Error adding account: {response.status_code}], {response.text}")
        return False

    return True


def add_or_create_user_in_org(org_id, role, user_data):
    email = user_data["email"]
    first_name = user_data["first_name"]
    last_name = user_data["last_name"]
    username = email

    try:
        user = User.objects.get(email=email)
        if not user.groups.filter(
                name=DjangoGroups.ORGANIZATION_MEMBER.value
        ).exists():
            group_id = Group.objects.get(
                name=DjangoGroups.ORGANIZATION_MEMBER
            ).id
            user.groups.add(group_id)

    except User.DoesNotExist:
        # create keycloak user
        response = add_account(user_data)
        # create django user
        if response:
            user = User.objects.create(
                email=email,
                username=username,
                first_name=first_name,
                last_name=last_name,
            )
            group_id = Group.objects.get(
                name=DjangoGroups.ORGANIZATION_MEMBER
            ).id
            user.groups.add(group_id)
        else:
            raise SuspiciousOperation

    account_profile, created = AccountProfile.objects.get_or_create(
        user_id=user.id,
    )
    apo, created = AccountProfileOrganization.objects.get_or_create(
        accountprofile_id=account_profile.id, organization_id=org_id, role=role
    )
    return user
