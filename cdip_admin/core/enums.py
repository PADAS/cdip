from enum import Enum


class RoleChoices(Enum):
    ADMIN = "admin"
    VIEWER = "viewer"

    def __str__(self):
        return self.value


class DjangoGroups(Enum):
    GLOBAL_ADMIN = "GlobalAdmin"
    ORGANIZATION_MEMBER = "OrganizationMember"

    def __str__(self):
        return self.value
