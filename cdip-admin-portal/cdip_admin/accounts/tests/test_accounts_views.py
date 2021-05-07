from django.contrib.auth.models import User
from django.urls import reverse

from accounts.views import get_accounts_in_user_organization
from conftest import setup_account_profile_mapping
from core.enums import RoleChoices


def test_get_accounts_list_global_admin_user(client, global_admin_user, setup_data):
    org1 = setup_data["org1"]
    org2 = setup_data["org2"]

    client.force_login(global_admin_user.user)

    response = client.get(reverse("account_list"), HTTP_X_USERINFO=global_admin_user.user_info)

    assert response.status_code == 200

    response = response.context['accounts']

    assert response.count() == User.objects.all().count()


def test_get_accounts_list_organization_member_admin(client, organization_member_user, setup_data):
    org1 = setup_data["org1"]
    org2 = setup_data["org2"]
    u1 = setup_data["u1"]
    u2 = setup_data["u2"]

    account_profile_mapping = {(organization_member_user.user, org1, RoleChoices.ADMIN),
                               (u1, org1, RoleChoices.VIEWER),
                               (u2, org2, RoleChoices.VIEWER)}
    setup_account_profile_mapping(account_profile_mapping)

    client.force_login(organization_member_user.user)

    response = client.get(reverse("account_list"), HTTP_X_USERINFO=organization_member_user.user_info)

    assert response.status_code == 200

    response = response.context['accounts']

    accounts = get_accounts_in_user_organization(organization_member_user.user)

    assert response.count() == User.objects.filter(id__in=accounts).count()


def test_get_accounts_list_organization_member_viewer(client, organization_member_user, setup_data):
    org1 = setup_data["org1"]
    org2 = setup_data["org2"]
    u1 = setup_data["u1"]
    u2 = setup_data["u2"]

    account_profile_mapping = {(organization_member_user.user, org1, RoleChoices.ADMIN),
                               (u1, org1, RoleChoices.VIEWER),
                               (u2, org2, RoleChoices.VIEWER)}
    setup_account_profile_mapping(account_profile_mapping)

    client.force_login(organization_member_user.user)

    response = client.get(reverse("account_list"), HTTP_X_USERINFO=organization_member_user.user_info)

    assert response.status_code == 200

    response = response.context['accounts']

    accounts = get_accounts_in_user_organization(organization_member_user.user)

    assert response.count() == User.objects.filter(id__in=accounts).count()


def test_get_accounts_detail_organization_member_viewer(client, organization_member_user, setup_data):
    org1 = setup_data["org1"]
    org2 = setup_data["org2"]
    u1 = setup_data["u1"]
    u2 = setup_data["u2"]

    account_profile_mapping = {(organization_member_user.user, org1, RoleChoices.ADMIN),
                               (u1, org1, RoleChoices.VIEWER),
                               (u2, org2, RoleChoices.VIEWER)}
    setup_account_profile_mapping(account_profile_mapping)

    client.force_login(organization_member_user.user)

    response = client.get(reverse("account_detail", kwargs={'user_id': u1.id}), HTTP_X_USERINFO=organization_member_user.user_info)

    assert response.status_code == 200

    response = client.get(reverse("account_detail", kwargs={'user_id': u2.id}),
                          HTTP_X_USERINFO=organization_member_user.user_info)

    # user should not be able to see detail of users not in their organization
    assert response.status_code == 403


def test_add_account_organization_member_admin(client, organization_member_user, setup_data):
    org1 = setup_data["org1"]
    org2 = setup_data["org2"]
    u1 = setup_data["u1"]
    u2 = setup_data["u2"]

    account_profile_mapping = {(organization_member_user.user, org1, RoleChoices.ADMIN),
                               (u1, org1, RoleChoices.VIEWER),
                               (u2, org2, RoleChoices.VIEWER)}
    setup_account_profile_mapping(account_profile_mapping)

    client.force_login(organization_member_user.user)

    response = client.get(reverse("account_add", kwargs={'org_id': org1.id}), HTTP_X_USERINFO=organization_member_user.user_info)

    assert response.status_code == 200

    response = client.get(reverse("account_add", kwargs={'org_id': org2.id}),
                          HTTP_X_USERINFO=organization_member_user.user_info)

    # user should not be able to invite users for organizations they are not admin of
    assert response.status_code == 403

    # TODO: test post


def test_update_account_organization_member_admin(client, organization_member_user, setup_data):
    org1 = setup_data["org1"]
    org2 = setup_data["org2"]
    u1 = setup_data["u1"]
    u2 = setup_data["u2"]

    account_profile_mapping = {(organization_member_user.user, org1, RoleChoices.ADMIN),
                               (u1, org1, RoleChoices.VIEWER),
                               (u2, org2, RoleChoices.VIEWER)}
    setup_account_profile_mapping(account_profile_mapping)

    client.force_login(organization_member_user.user)

    response = client.get(reverse("account_update", kwargs={'user_id': u1.id}),
                          HTTP_X_USERINFO=organization_member_user.user_info)

    assert response.status_code == 200

    response = client.get(reverse("account_update", kwargs={'user_id': u2.id}),
                          HTTP_X_USERINFO=organization_member_user.user_info)

    # user should not be able to invite users for organizations they are not admin of
    assert response.status_code == 403

    # TODO: test post


def test_update_account_profile_organization_member_admin(client, organization_member_user, setup_data):
    org1 = setup_data["org1"]
    org2 = setup_data["org2"]
    u1 = setup_data["u1"]
    u2 = setup_data["u2"]

    account_profile_mapping = {(organization_member_user.user, org1, RoleChoices.ADMIN),
                               (u1, org1, RoleChoices.VIEWER),
                               (u2, org2, RoleChoices.VIEWER)}
    setup_account_profile_mapping(account_profile_mapping)

    client.force_login(organization_member_user.user)

    response = client.get(reverse("account_profile_update", kwargs={'org_id': org1.id,
                                                                    'user_id': u1.id}),
                          HTTP_X_USERINFO=organization_member_user.user_info)

    assert response.status_code == 200

    response = client.get(reverse("account_profile_update", kwargs={'org_id': org2.id,
                                                                    'user_id': u2.id}),
                          HTTP_X_USERINFO=organization_member_user.user_info)

    # user should not be able to invite users for organizations they are not admin of
    assert response.status_code == 403

    # TODO: test post
