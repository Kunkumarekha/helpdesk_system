import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from database import get_connection

# Change this secret before using the project anywhere public.
SECRET_KEY = "change-this-helpdesk-secret-key"
TOKEN_EXPIRE_HOURS = 8

bearer_scheme = HTTPBearer()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        120000,
    )
    return (
        base64.urlsafe_b64encode(salt).decode()
        + "$"
        + base64.urlsafe_b64encode(password_hash).decode()
    )


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt_text, hash_text = stored_hash.split("$", 1)
        salt = base64.urlsafe_b64decode(salt_text.encode())
        expected = base64.urlsafe_b64decode(hash_text.encode())

        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            120000,
        )

        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def base64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def create_access_token(data: dict) -> str:
    header = {
        "alg": "HS256",
        "typ": "JWT",
    }

    now = datetime.now(timezone.utc)
    payload = dict(data)
    payload["iat"] = int(now.timestamp())
    payload["exp"] = int(
        (now + timedelta(hours=TOKEN_EXPIRE_HOURS)).timestamp()
    )

    header_part = base64url(
        json.dumps(header, separators=(",", ":")).encode()
    )
    payload_part = base64url(
        json.dumps(payload, separators=(",", ":")).encode()
    )

    message = f"{header_part}.{payload_part}".encode()

    signature = hmac.new(
        SECRET_KEY.encode(),
        message,
        hashlib.sha256,
    ).digest()

    signature_part = base64url(signature)

    return f"{header_part}.{payload_part}.{signature_part}"


def verify_access_token(token: str) -> dict:
    try:
        parts = token.split(".")

        if len(parts) != 3:
            raise ValueError("Invalid token")

        header_part, payload_part, signature_part = parts

        message = f"{header_part}.{payload_part}".encode()

        expected_signature = hmac.new(
            SECRET_KEY.encode(),
            message,
            hashlib.sha256,
        ).digest()

        actual_signature = base64.urlsafe_b64decode(
            signature_part + "=" * (-len(signature_part) % 4)
        )

        if not hmac.compare_digest(
            expected_signature,
            actual_signature
        ):
            raise ValueError("Invalid signature")

        payload = json.loads(
            base64.urlsafe_b64decode(
                payload_part + "=" * (-len(payload_part) % 4)
            )
        )

        if datetime.now(timezone.utc).timestamp() >= payload["exp"]:
            raise ValueError("Token expired")

        return payload

    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
):
    payload = verify_access_token(credentials.credentials)

    user_id = int(payload["sub"])

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT id, name, email, role, is_active, created_at
        FROM users
        WHERE id = ?
        """,
        (user_id,),
    )

    user = cur.fetchone()
    conn.close()

    if not user or not user["is_active"]:
        raise HTTPException(
            status_code=401,
            detail="User is inactive or does not exist",
        )

    return dict(user)


def require_roles(*roles):
    allowed_roles = set(roles)

    def checker(current_user=Depends(get_current_user)):
        if current_user["role"] not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail="You do not have permission for this operation",
            )
        return current_user

    return checker
