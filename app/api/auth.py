import secrets

from fastapi import Header

from app.api.errors import api_error
from app.core.config import get_settings


def require_admin(x_admin_token: str = Header(default="")) -> None:
    """Single-operator auth: one shared token for the human via the
    frontend. No user accounts/RBAC - there is exactly one operator."""
    expected = get_settings().admin_token
    if not expected or not secrets.compare_digest(x_admin_token, expected):
        raise api_error(401, "unauthorized", "missing or invalid admin token")
