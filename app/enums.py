from enum import Enum


class UserRole(str, Enum):
    OPS = "ops"
    MANAGER = "manager"


class PaymentMethod(str, Enum):
    CASH = "Cash"
    MOBILE_MONEY = "Mobile Money"
    BANK_CARD = "Bank Card"
    CREDIT = "Credit"