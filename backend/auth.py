from __future__ import annotations

import json
import os
import secrets
from base64 import b64decode, b64encode
from datetime import datetime, timedelta, timezone
from hashlib import pbkdf2_hmac
import hmac
from pathlib import Path
from typing import Any, Dict, Optional
import hashlib

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-change-me")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "120"))
USERS_FILE = Path(os.getenv("USERS_FILE", "data/users.json"))
AUTH_REQUIRED = os.getenv("AUTH_REQUIRED", "false").lower() == "true"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)


class AuthError(HTTPException):
    def __init__(self, detail: str = "Authentication failed") -> None:
        super().__init__(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


def _load_users() -> Dict[str, Dict[str, Any]]:
    if not USERS_FILE.exists():
        return {}
    try:
        raw = json.loads(USERS_FILE.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _save_users(users: Dict[str, Dict[str, Any]]) -> None:
    USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    USERS_FILE.write_text(json.dumps(users, indent=2), encoding="utf-8")


def ensure_default_admin() -> None:
    users = _load_users()
    if users:
        return

    admin_user = os.getenv("ADMIN_USERNAME", "admin")
    admin_password = os.getenv("ADMIN_PASSWORD", "admin123")
    users[admin_user] = {
        "username": admin_user,
        "password_hash": _hash_password(admin_password),
        "role": "admin",
        "disabled": False,
    }
    _save_users(users)


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
    return f"pbkdf2_sha256${b64encode(salt).decode('utf-8')}${b64encode(digest).decode('utf-8')}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        prefix, salt_b64, digest_b64 = stored.split("$")
        if prefix != "pbkdf2_sha256":
            return False
        salt = b64decode(salt_b64.encode("utf-8"))
        expected = b64decode(digest_b64.encode("utf-8"))
        current = pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
        return secrets.compare_digest(current, expected)
    except Exception:
        return False


def register_user(username: str, password: str, role: str = "user") -> Dict[str, Any]:
    users = _load_users()
    if username in users:
        raise HTTPException(status_code=409, detail="User already exists")

    users[username] = {
        "username": username,
        "password_hash": _hash_password(password),
        "role": role,
        "disabled": False,
    }
    _save_users(users)
    return {"username": username, "role": role}


def authenticate_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    users = _load_users()
    user = users.get(username)
    if not user:
        return None
    if user.get("disabled"):
        return None
    if not _verify_password(password, str(user.get("password_hash", ""))):
        return None
    return user


def create_access_token(subject: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": subject, "role": role, "exp": int(expire.timestamp())}
    return _jwt_encode(payload)


def _b64url_encode(data: bytes) -> str:
    return b64encode(data).decode("utf-8").replace("+", "-").replace("/", "_").rstrip("=")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    normalized = data.replace("-", "+").replace("_", "/") + padding
    return b64decode(normalized.encode("utf-8"))


def _jwt_encode(payload: Dict[str, Any]) -> str:
    header = {"alg": ALGORITHM, "typ": "JWT"}
    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
    signature = hmac.new(SECRET_KEY.encode("utf-8"), signing_input, hashlib.sha256).digest()
    signature_b64 = _b64url_encode(signature)
    return f"{header_b64}.{payload_b64}.{signature_b64}"


def _jwt_decode(token: str) -> Dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise AuthError("Malformed token")

    header_b64, payload_b64, signature_b64 = parts
    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
    expected = hmac.new(SECRET_KEY.encode("utf-8"), signing_input, hashlib.sha256).digest()
    actual = _b64url_decode(signature_b64)
    if not secrets.compare_digest(expected, actual):
        raise AuthError("Invalid token signature")

    payload_raw = _b64url_decode(payload_b64)
    payload = json.loads(payload_raw.decode("utf-8"))
    exp = int(payload.get("exp", 0))
    if exp and int(datetime.now(timezone.utc).timestamp()) > exp:
        raise AuthError("Token expired")
    return payload


def _decode_token(token: str) -> Dict[str, Any]:
    try:
        return _jwt_decode(token)
    except Exception as exc:
        raise AuthError("Invalid token") from exc


async def get_current_user_optional(token: str | None = Depends(oauth2_scheme)) -> Dict[str, Any]:
    if not token:
        if AUTH_REQUIRED:
            raise AuthError("Missing authentication token")
        return {"username": "anonymous", "role": "anonymous"}

    payload = _decode_token(token)
    username = payload.get("sub")
    if not username:
        raise AuthError("Invalid token payload")

    users = _load_users()
    user = users.get(username)
    if not user:
        raise AuthError("User not found")
    return {"username": user["username"], "role": user.get("role", "user")}


def require_role(required_role: str):
    async def _checker(user: Dict[str, Any] = Depends(get_current_user_optional)) -> Dict[str, Any]:
        if user.get("role") != required_role:
            raise HTTPException(status_code=403, detail=f"{required_role} role required")
        return user

    return _checker
