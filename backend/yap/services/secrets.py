"""Encryption of stored API keys (REV-15) with a secret from the server environment."""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from yap.messages import msg
from yap.services.common import ConflictError


class KeyBox:
    """Encrypts and decrypts API keys with `APP_SECRET_KEY`. Without the secret, keys
    can neither be stored nor used."""

    def __init__(self, secret: str | None) -> None:
        if secret:
            # Fernet needs 32 url-safe base64 bytes; derive them from any secret string
            digest = hashlib.sha256(secret.encode()).digest()
            self._fernet: Fernet | None = Fernet(base64.urlsafe_b64encode(digest))
        else:
            self._fernet = None

    @property
    def available(self) -> bool:
        return self._fernet is not None

    def _require(self) -> Fernet:
        if self._fernet is None:
            raise ConflictError(msg("secret_missing"))
        return self._fernet

    def encrypt(self, plain: str) -> bytes:
        return self._require().encrypt(plain.encode())

    def decrypt(self, token: bytes) -> str:
        try:
            return self._require().decrypt(token).decode()
        except InvalidToken:
            raise ConflictError(msg("secret_cannot_decrypt")) from None
