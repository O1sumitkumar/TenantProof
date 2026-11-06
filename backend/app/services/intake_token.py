"""Intake link tokens. The raw token is never stored: it is derived as
HMAC(secret, case_id:version). The DB keeps only sha256(token) for lookup, so a
DB leak does not leak links, and bumping the version revokes the old link."""

import base64
import hashlib
import hmac


def make_token(secret: str, case_id: str, version: int) -> str:
    digest = hmac.new(secret.encode(), f"{case_id}:{version}".encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
