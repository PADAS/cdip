import logging
import requests
from django.http import JsonResponse
from django.contrib.auth.models import User, Group
from django.core.exceptions import SuspiciousOperation
from django.db.models import Q
from core.enums import DjangoGroups
from cdip_admin import settings
from core.utils import get_admin_access_token
from organizations.models import Organization
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
    user_created = False
    try:
        user = User.objects.get(Q(username=email) | Q(email=email))
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
            user_created = True
        else:
            raise SuspiciousOperation

    account_profile, created = AccountProfile.objects.get_or_create(
        user_id=user.id,
    )
    apo, created = AccountProfileOrganization.objects.get_or_create(
        accountprofile_id=account_profile.id, organization_id=org_id, role=role
    )
    return user, user_created


def remove_members_from_organization(org_id, profile_ids):
    removed_qty, _ = AccountProfileOrganization.objects.filter(organization__id=org_id, id__in=profile_ids).delete()
    return removed_qty


def get_password_reset_link(user):
    return f"{KEYCLOAK_SERVER}/auth/realms/{KEYCLOAK_REALM}/login-actions/reset-credentials?client_id={KEYCLOAK_CLIENT}"


def get_user_organizations_qs(user):
    # Returns a queryset with the organizations that the user is allowed to see
    if user.is_superuser:
        return Organization.objects.all()
    try:
        profile = user.accountprofile
    except AccountProfile.DoesNotExist as e:
        return Organization.objects.none()
    return profile.organizations.all()
