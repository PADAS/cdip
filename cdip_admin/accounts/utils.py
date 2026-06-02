import logging

from django.contrib.auth.models import User, Group
from django.core.exceptions import SuspiciousOperation
from django.db.models import Q

from core.enums import DjangoGroups
from organizations.models import Organization

from .keycloak import add_account
from .models import AccountProfile, AccountProfileOrganization


logger = logging.getLogger(__name__)


def add_or_create_user_in_org(org_id, role, user_data):
    email = user_data["email"]
    first_name = user_data["first_name"]
    last_name = user_data["last_name"]
    user_created = False
    org_members_group_id = Group.objects.get(name=DjangoGroups.ORGANIZATION_MEMBER).id

    try:
        user = User.objects.get(Q(username=email) | Q(email=email))
        if not user.groups.filter(name=DjangoGroups.ORGANIZATION_MEMBER.value).exists():
            user.groups.add(org_members_group_id)

    except User.DoesNotExist:
        if not add_account(user_data):
            raise SuspiciousOperation
        user = User.objects.create(
            email=email,
            username=email,
            first_name=first_name,
            last_name=last_name,
        )
        user.groups.add(org_members_group_id)
        user_created = True

    account_profile, _ = AccountProfile.objects.get_or_create(user_id=user.id)
    AccountProfileOrganization.objects.get_or_create(
        accountprofile_id=account_profile.id, organization_id=org_id, role=role,
    )
    return user, user_created


def remove_members_from_organization(org_id, profile_ids):
    removed_qty, _ = AccountProfileOrganization.objects.filter(organization__id=org_id, id__in=profile_ids).delete()
    return removed_qty


def get_user_organizations_qs(user):
    # Returns a queryset with the organizations that the user is allowed to see
    if user.is_superuser:
        return Organization.objects.all()
    try:
        profile = user.accountprofile
    except AccountProfile.DoesNotExist as e:
        return Organization.objects.none()
    return profile.organizations.all()
