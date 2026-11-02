from enum import Enum

class UserRole(str, Enum):
    USER = "user"
    BARANGAY_OFFICIAL = "barangay_official"
    LGU_OFFICIAL = "lgu_official"
    SUPERADMIN = "superadmin"
    BARANGAY_MEMBER = "barangay_member"
    