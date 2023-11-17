from enum import auto
from core.utils import AutoNameEnum


class ActivityActions(AutoNameEnum):
    CREATED = auto()
    UPDATED = auto()
    DELETED = auto()
