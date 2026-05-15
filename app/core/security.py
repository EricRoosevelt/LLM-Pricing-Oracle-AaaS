import hashlib
import secrets

from fastapi.security import APIKeyHeader

from app.core.config import settings


api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def hash_api_key(api_key: str) -> str:
    payload = f"{settings.API_KEY_PEPPER}:{api_key}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def verify_api_key_hash(api_key: str, stored_hash: str) -> bool:
    return secrets.compare_digest(hash_api_key(api_key), stored_hash)
