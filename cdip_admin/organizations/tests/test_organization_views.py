from django.urls import reverse

from conftest import setup_account_profile_mapping
from core.enums import RoleChoices
from organizations.models import Organization


def test_get_organizations_list_global_admin(client, global_admin_user):
    client.force_login(global_admin_user.user)

    # Get organizations list
    response = client.get(reverse("organization_list"), HTTP_X_USERINFO=global_admin_user.user_info)

    assert response.status_code == 200
    response = response.json()

    # should receive all organizations as the admin
    assert len(response) == Organization.objects.all().count()


def test_get_organizations_list_organization_member_viewer(client, organization_member_user, setup_data):
    org1 = setup_data["org1"]

    account_profile_mapping = {(organization_member_user.user, org1, RoleChoices.VIEWER)}
    setup_account_profile_mapping(account_profile_mapping)

    client.force_login(organization_member_user.user)

    # Get organizations list
    response = client.get(reverse("organization_list"), HTTP_X_USERINFO=organization_member_user.user_info)

    assert response.status_code == 200
    response = response.json()

    # should receive the organization user is viewer of
    assert len(response) == Organization.objects.filter(id=org1.id).count()


def test_get_organization_detail_organization_member_viewer(client, organization_member_user, setup_data):

    org1 = setup_data["org1"]
    org2 = setup_data["org2"]

    account_profile_mapping = {(organization_member_user.user, org1, RoleChoices.VIEWER)}
    setup_account_profile_mapping(account_profile_mapping)

    client.force_login(organization_member_user.user)

    response = client.get(reverse("organizations_detail", kwargs={'module_id': org1.id}),
                          HTTP_X_USERINFO=organization_member_user.user_info)

    assert response.status_code == 200
    response = response.context['organization']

    assert response.id == org1.id

    response = client.get(reverse("organizations_detail", kwargs={'module_id': org2.id}),
                          HTTP_X_USERINFO=organization_member_user.user_info)


def test_add_organizations_list_global_admin(client, global_admin_user):
    client.force_login(global_admin_user.user)

    # Get organizations list
    response = client.get(reverse("organizations_add"), HTTP_X_USERINFO=global_admin_user.user_info)

    assert response.status_code == 200

    # TODO: Test Post


def test_update_organizations_list_global_admin(client, global_admin_user, setup_data):
    org1 = setup_data["org1"]

    client.force_login(global_admin_user.user)

    # Get organizations list
    response = client.get(reverse("organizations_update", kwargs={'organization_id': org1.id}),
                          HTTP_X_USERINFO=global_admin_user.user_info)

    assert response.status_code == 200

    # TODO: Test Post