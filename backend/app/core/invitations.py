import hashlib
import secrets

INVITATION_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
INVITATION_CODE_LENGTH = 12
INVITATION_CODE_PREFIX = "FK-"


def generate_invitation_code() -> str:
    value = "".join(
        secrets.choice(INVITATION_CODE_ALPHABET) for _ in range(INVITATION_CODE_LENGTH)
    )
    return f"{INVITATION_CODE_PREFIX}{value}"


def normalize_invitation_code(code: str) -> str:
    return code.strip().upper()


def hash_invitation_code(code: str) -> str:
    normalized = normalize_invitation_code(code)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
