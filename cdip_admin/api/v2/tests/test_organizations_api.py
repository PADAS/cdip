import pytest
from django.urls import reverse
from django.contrib.auth.models import User
from rest_framework import status
from accounts.models import AccountProfileOrganization
from core.enums import RoleChoices

pytestmark = pytest.mark.django_db

from integrations.models import (
    Organization,
)


def test_create_organization_as_superuser(api_client, organization, superuser):
    request_data = {
      "name": "Grumeti",
      "description": "A reserve in Tanzania"
    }

    api_client.force_authenticate(superuser)
    response = api_client.post(
        reverse("organizations-list"),
        data=request_data
    )

    # Check the request response
    assert response.status_code == status.HTTP_201_CREATED
    response_data = response.json()
    assert "id" in response_data
    # Check that the organization was created in the database
    assert Organization.objects.filter(name=request_data["name"]).exists()


def test_cannot_create_organization_as_org_admin(api_client, org_admin_user):
    request_data = {
      "name": "New Organization",
    }

    api_client.force_authenticate(org_admin_user)
    response = api_client.post(
        reverse("organizations-list"),
        data=request_data
    )

    # Check the request response
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_cannot_create_organization_as_org_viewer(api_client, org_viewer_user):
    request_data = {
      "name": "New Organization",
    }

    api_client.force_authenticate(org_viewer_user)
    response = api_client.post(
        reverse("organizations-list"),
        data=request_data
    )

    # Check the request response
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_delete_organization_as_superuser(api_client, superuser, organization):
    api_client.force_authenticate(superuser)
    response = api_client.delete(
        reverse("organizations-detail", kwargs={"pk": organization.id})
    )

    # Check the request response
    assert response.status_code == status.HTTP_204_NO_CONTENT
    # Check that the organization was deleted in the database
    with pytest.raises(Organization.DoesNotExist):
        Organization.objects.get(id=organization.id)


def test_cannot_delete_organization_as_org_admin(api_client, org_admin_user, organization):
    api_client.force_authenticate(org_admin_user)
    response = api_client.delete(
        reverse("organizations-detail", kwargs={"pk": organization.id})
    )

    # Check the request response
    assert response.status_code == status.HTTP_403_FORBIDDEN
    # Check that the organization was NOT deleted in the database
    assert Organization.objects.filter(id=organization.id).exists()


def test_cannot_delete_organization_as_org_viewer(api_client, org_viewer_user, organization):
    api_client.force_authenticate(org_viewer_user)
    response = api_client.delete(
        reverse("organizations-detail", kwargs={"pk": organization.id})
    )

    # Check the request response
    assert response.status_code == status.HTTP_403_FORBIDDEN
    # Check that the organization was NOT deleted in the database
    assert Organization.objects.filter(id=organization.id).exists()


def test_list_organizations_as_superuser(api_client, superuser, organizations_list):
    api_client.force_authenticate(superuser)
    response = api_client.get(
        reverse("organizations-list"),
    )
    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    # Check that the superuser can see all the organizations
    expected_organizations_ids = [str(o.id) for o in organizations_list]
    for org in response_data["results"]:
        assert org.get("id") in expected_organizations_ids


def test_list_organizations_as_org_admin_user(api_client, org_admin_user, organizations_list, organization):
    api_client.force_authenticate(org_admin_user)
    response = api_client.get(
        reverse("organizations-list"),
    )
    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    # Check that the admin only sees the organization he belongs to
    expected_organizations_ids = [str(organization.id)]
    for org in response_data["results"]:
        assert org.get("id") in expected_organizations_ids
        assert "name" in org
        assert "description" in org
        assert org.get("role") == RoleChoices.ADMIN.value


def test_list_organizations_as_org_viewer_user(api_client, org_viewer_user, organizations_list, organization):
    api_client.force_authenticate(org_viewer_user)
    response = api_client.get(
        reverse("organizations-list"),
    )
    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    # Check that the admin only sees the organization he belongs to
    expected_organizations_ids = [str(organization.id)]
    for org in response_data["results"]:
        assert org.get("id") in expected_organizations_ids
        assert "name" in org
        assert "description" in org
        assert org.get("role") == RoleChoices.VIEWER.value


def test_retrieve_organization_details_as_superuser(api_client, superuser, organization):
    api_client.force_authenticate(superuser)
    response = api_client.get(
        reverse("organizations-detail", kwargs={"pk": organization.id})
    )
    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    assert response_data.get("id") == str(organization.id)
    assert response_data.get("name") == organization.name
    assert response_data.get("description") == organization.description
    assert response_data.get("role") == "superuser"


def test_retrieve_organization_details_as_org_admin_user(api_client, org_admin_user, organization):
    api_client.force_authenticate(org_admin_user)
    response = api_client.get(
        reverse("organizations-detail", kwargs={"pk": organization.id})
    )
    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    assert response_data.get("id") == str(organization.id)
    assert response_data.get("name") == organization.name
    assert response_data.get("description") == organization.description
    assert response_data.get("role") == RoleChoices.ADMIN.value


def test_cannot_retrieve_unrelated_organization_details_as_org_admin_user(api_client, org_admin_user, organization, organizations_list):
    # Pick an organization where this user is not a member
    unrelated_organization = [o for o in organizations_list if o != organization][0]
    api_client.force_authenticate(org_admin_user)
    response = api_client.get(
        reverse("organizations-detail", kwargs={"pk": unrelated_organization.id})
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_cannot_retrieve_unrelated_organization_details_as_org_viewer(api_client, org_viewer_user, organization, organizations_list):
    # Pick an organization where this user is not a member
    unrelated_organization = [o for o in organizations_list if o != organization][0]
    api_client.force_authenticate(org_viewer_user)
    response = api_client.get(
        reverse("organizations-detail", kwargs={"pk": unrelated_organization.id})
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


# def test_update_organization_details_as_superuser(api_client, superuser, setup_data):
#     # ToDo: Implement
#     pass
#
#
# def test_update_organization_details_as_org_admin(api_client, org_admin_user, setup_data):
#     # ToDo: Implement
#     pass
#

def _test_invite_user(
        api_client, inviter, organization, user_email, role, is_new, org_members_group,
        mocker, mock_add_account, mock_send_invite_email_task
):
    request_data = {
        "email": user_email,
        "first_name": "Frank",
        "last_name": "Smith",
        "role": role
    }

    api_client.force_authenticate(inviter)
    # Mock external dependencies
    mocker.patch("accounts.utils.add_account", mock_add_account)  # mock user creation in Keycloak
    mocker.patch("api.v2.views.send_invite_email_task", mock_send_invite_email_task)  # mock email sending
    response = api_client.put(
        reverse("members-invite", kwargs={"organization_pk": organization.id}),
        data=request_data
    )
    assert response.status_code == status.HTTP_200_OK
    # Check that the user was created in the database
    user = User.objects.get(username=user_email)
    assert user.email == user_email
    if is_new:
        assert user.first_name == request_data["first_name"]
        assert user.last_name == request_data["last_name"]
    # Check the user role in the organization
    profile = AccountProfileOrganization.objects.get(
        organization_id=organization.id, accountprofile__user=user
    )
    assert profile.role == role
    if is_new:  # Check that user was created in keycloak
        assert mock_add_account.called
    else:
        assert not mock_add_account.called
    # Check that the invitation email was sent
    assert mock_send_invite_email_task.delay.called


def _test_cannot_invite_user(
        api_client, inviter, organization, user_email, role, is_new, org_members_group,
        mocker, mock_add_account, mock_send_invite_email_task
):
    request_data = {
        "email": user_email,
        "first_name": "Frank",
        "last_name": "Smith",
        "role": role
    }

    api_client.force_authenticate(inviter)
    # Mock external dependencies
    mocker.patch("accounts.utils.add_account", mock_add_account)  # mock user creation in Keycloak
    mocker.patch("api.v2.views.send_invite_email_task", mock_send_invite_email_task)  # mock email sending
    response = api_client.put(
        reverse("members-invite", kwargs={"organization_pk": organization.id}),
        data=request_data
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    if is_new:
        # Check that the user was NOT created in the database
        with pytest.raises(User.DoesNotExist):
            User.objects.get(username=user_email)
    # Check that user was NOT created in keycloak
    assert not mock_add_account.called
    # Check that the invitation email was NOT sent
    assert not mock_send_invite_email_task.delay.called


def test_invite_new_user_org_admin_as_superuser(
        api_client, superuser, organization, new_user_email, org_members_group,
        mocker, mock_add_account, mock_send_invite_email_task
):
    _test_invite_user(
        api_client=api_client,
        inviter=superuser,
        organization=organization,
        user_email=new_user_email(),
        role=RoleChoices.ADMIN.value,
        is_new=True,
        org_members_group=org_members_group,
        mocker=mocker,
        mock_add_account=mock_add_account,
        mock_send_invite_email_task=mock_send_invite_email_task
    )


def test_invite_new_user_org_admin_as_org_admin(
        api_client, org_admin_user, organization, new_user_email, org_members_group,
        mocker, mock_add_account, mock_send_invite_email_task
):
    _test_invite_user(
        api_client=api_client,
        inviter=org_admin_user,
        organization=organization,
        user_email=new_user_email(),
        role=RoleChoices.ADMIN.value,
        is_new=True,
        org_members_group=org_members_group,
        mocker=mocker,
        mock_add_account=mock_add_account,
        mock_send_invite_email_task=mock_send_invite_email_task
    )


def test_cannot_invite_new_user_org_admin_as_org_viewer(
        api_client, org_viewer_user, organization, new_user_email, org_members_group,
        mocker, mock_add_account, mock_send_invite_email_task
):
    _test_cannot_invite_user(
        api_client=api_client,
        inviter=org_viewer_user,
        organization=organization,
        user_email=new_user_email(),
        role=RoleChoices.ADMIN.value,
        is_new=True,
        org_members_group=org_members_group,
        mocker=mocker,
        mock_add_account=mock_add_account,
        mock_send_invite_email_task=mock_send_invite_email_task
    )


def test_invite_new_user_org_viewer_as_superuser(
        api_client, superuser, organization, new_user_email, org_members_group,
        mocker, mock_add_account, mock_send_invite_email_task
):
    _test_invite_user(
        api_client=api_client,
        inviter=superuser,
        organization=organization,
        user_email=new_user_email(),
        role=RoleChoices.VIEWER.value,
        is_new=True,
        org_members_group=org_members_group,
        mocker=mocker,
        mock_add_account=mock_add_account,
        mock_send_invite_email_task=mock_send_invite_email_task
    )


def test_invite_new_user_org_viewer_as_org_admin(
        api_client, org_admin_user, organization, new_user_email, org_members_group,
        mocker, mock_add_account, mock_send_invite_email_task
):
    _test_invite_user(
        api_client=api_client,
        inviter=org_admin_user,
        organization=organization,
        user_email=new_user_email(),
        role=RoleChoices.VIEWER.value,
        is_new=True,
        org_members_group=org_members_group,
        mocker=mocker,
        mock_add_account=mock_add_account,
        mock_send_invite_email_task=mock_send_invite_email_task
    )


def test_cannot_invite_new_org_viewer_as_org_viewer(
        api_client, org_viewer_user, organization, new_user_email, org_members_group,
        mocker, mock_add_account, mock_send_invite_email_task
):
    _test_cannot_invite_user(
        api_client=api_client,
        inviter=org_viewer_user,
        organization=organization,
        user_email=new_user_email(),
        role=RoleChoices.VIEWER.value,
        is_new=True,
        org_members_group=org_members_group,
        mocker=mocker,
        mock_add_account=mock_add_account,
        mock_send_invite_email_task=mock_send_invite_email_task
    )


def test_invite_existent_user_org_admin_as_superuser(
        api_client, superuser, organization, new_random_user, org_members_group,
        mocker, mock_add_account, mock_send_invite_email_task
):
    _test_invite_user(
        api_client=api_client,
        inviter=superuser,
        organization=organization,
        user_email=new_random_user().email,
        role=RoleChoices.ADMIN.value,
        is_new=False,
        org_members_group=org_members_group,
        mocker=mocker,
        mock_add_account=mock_add_account,
        mock_send_invite_email_task=mock_send_invite_email_task
    )


def test_invite_existent_user_org_admin_as_org_admin(
        api_client, org_admin_user, organization, new_random_user, org_members_group,
        mocker, mock_add_account, mock_send_invite_email_task
):
    _test_invite_user(
        api_client=api_client,
        inviter=org_admin_user,
        organization=organization,
        user_email=new_random_user().email,
        role=RoleChoices.ADMIN.value,
        is_new=False,
        org_members_group=org_members_group,
        mocker=mocker,
        mock_add_account=mock_add_account,
        mock_send_invite_email_task=mock_send_invite_email_task
    )


def test_cannot_invite_existent_user_org_admin_as_org_viewer(
        api_client, org_viewer_user, organization, new_random_user, org_members_group,
        mocker, mock_add_account, mock_send_invite_email_task
):
    _test_cannot_invite_user(
        api_client=api_client,
        inviter=org_viewer_user,
        organization=organization,
        user_email=new_random_user().email,
        role=RoleChoices.ADMIN.value,
        is_new=False,
        org_members_group=org_members_group,
        mocker=mocker,
        mock_add_account=mock_add_account,
        mock_send_invite_email_task=mock_send_invite_email_task
    )


def test_invite_existent_user_org_viewer_as_superuser(
        api_client, superuser, organization, new_random_user, org_members_group,
        mocker, mock_add_account, mock_send_invite_email_task
):
    _test_invite_user(
        api_client=api_client,
        inviter=superuser,
        organization=organization,
        user_email=new_random_user().email,
        role=RoleChoices.VIEWER.value,
        is_new=False,
        org_members_group=org_members_group,
        mocker=mocker,
        mock_add_account=mock_add_account,
        mock_send_invite_email_task=mock_send_invite_email_task
    )


def test_invite_existent_user_org_viewer_as_org_admin(
        api_client, org_admin_user, organization, new_random_user, org_members_group,
        mocker, mock_add_account, mock_send_invite_email_task
):
    _test_invite_user(
        api_client=api_client,
        inviter=org_admin_user,
        organization=organization,
        user_email=new_random_user().email,
        role=RoleChoices.VIEWER.value,
        is_new=False,
        org_members_group=org_members_group,
        mocker=mocker,
        mock_add_account=mock_add_account,
        mock_send_invite_email_task=mock_send_invite_email_task
    )


def test_cannot_invite_existent_user_org_viewer_as_org_viewer(
        api_client, org_viewer_user, organization, new_random_user, org_members_group,
        mocker, mock_add_account, mock_send_invite_email_task
):
    _test_cannot_invite_user(
        api_client=api_client,
        inviter=org_viewer_user,
        organization=organization,
        user_email=new_random_user().email,
        role=RoleChoices.VIEWER.value,
        is_new=False,
        org_members_group=org_members_group,
        mocker=mocker,
        mock_add_account=mock_add_account,
        mock_send_invite_email_task=mock_send_invite_email_task
    )


def _test_list_organization_members(api_client, user, organization, members_apo_list):
    api_client.force_authenticate(user)
    response = api_client.get(
        reverse("members-list", kwargs={"organization_pk": organization.id}),
    )
    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    # Check that the superuser can see all the members
    expected_member_ids = [m.id for m in members_apo_list]
    # The requester user should also be in the organization, unless it's a superuser
    if not user.is_superuser:
        user_apo = AccountProfileOrganization.objects.get(accountprofile__user=user)
        expected_member_ids.append(user_apo.id)
    for member in response_data["results"]:
        assert member.get("id") in expected_member_ids
        assert "first_name" in member
        assert "last_name" in member
        assert "role" in member


def test_list_organization_members_as_superuser(api_client, superuser, organization, members_apo_list):
    _test_list_organization_members(
        api_client=api_client,
        user=superuser,
        organization=organization,
        members_apo_list=members_apo_list
    )


def test_list_organization_members_as_org_admin(api_client, org_admin_user, organization, members_apo_list):
    _test_list_organization_members(
        api_client=api_client,
        user=org_admin_user,
        organization=organization,
        members_apo_list=members_apo_list
    )


def test_list_organization_members_as_org_viewer(api_client, org_viewer_user, organization, members_apo_list):
    _test_list_organization_members(
        api_client=api_client,
        user=org_viewer_user,
        organization=organization,
        members_apo_list=members_apo_list
    )



# def test_retrieve_member_details_as_superuser(api_client, superuser, setup_data):
#     # ToDo: Implement
#     pass
#
#
# def test_retrieve_member_details_as_org_admin(api_client, org_admin_user, setup_data):
#     # ToDo: Implement
#     pass
#
#
# def test_cannot_retrieve_other_member_details_as_org_viewer(api_client, org_viewer_user, setup_data):
#     # ToDo: Implement
#     pass
#
#
# def test_update_member_details_as_superuser(api_client, superuser, setup_data):
#     # ToDo: Implement
#     pass
#
#
# def test_update_member_details_as_org_admin(api_client, org_admin_user, setup_data):
#     # ToDo: Implement
#     pass
#
#
# def test_cannot_update_member_details_as_org_viewer(api_client, org_viewer_user, setup_data):
#     # ToDo: Implement
#     pass
#
#
# def test_remove_member_as_superuser(api_client, superuser, setup_data):
#     # ToDo: Implement
#     pass
#
#
# def test_remove_member_as_org_admin(api_client, org_admin_user, setup_data):
#     # ToDo: Implement
#     pass
#
#
# def test_cannot_remove_member_as_org_viewer(api_client, org_viewer_user, setup_data):
#     # ToDo: Implement
#     pass

