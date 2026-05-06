"""
crypto.py
=========
Application-layer AES-256 encryption using Fernet.

Used to encrypt highly sensitive fields (like LLM API keys) at rest before
sending them to Supabase, mitigating plaintext leaks from DB dumps or RLS bypasses.
"""

from __future__ import annotations

import base64
import logging
import os

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

# Single symmetric key used to encrypt/decrypt application state.
# Must be a url-safe base64-encoded 32-byte key.
# Generate one using: Fernet.generate_key()
_APP_SECRET_KEY = os.environ.get("APP_SECRET_KEY", "")


class EncryptionUnavailableError(RuntimeError):
    """Raised when an operation requires encryption but APP_SECRET_KEY is absent."""


_fernet: Fernet | None = None
if _APP_SECRET_KEY:
    try:
        _fernet = Fernet(_APP_SECRET_KEY.encode("utf-8"))
    except Exception as exc:
        logger.error("Failed to initialize Fernet with APP_SECRET_KEY: %s", exc)
        raise EncryptionUnavailableError("APP_SECRET_KEY is invalid. Sensitive values cannot be encrypted.") from exc
else:
    logger.warning("APP_SECRET_KEY is not set. Sensitive encryption paths are unavailable.")


def is_encryption_available() -> bool:
    return _fernet is not None


def require_encryption() -> None:
    if _fernet is None:
        raise EncryptionUnavailableError(
            "APP_SECRET_KEY is required for sensitive storage operations."
        )


def encrypt_string(plaintext: str) -> str:
    """Encrypt a plaintext string using AES-256.

    Fails closed when APP_SECRET_KEY is unavailable instead of silently
    returning plaintext.
    """
    if not plaintext:
        return ""

    require_encryption()

    try:
        encrypted_bytes = _fernet.encrypt(plaintext.encode("utf-8"))
        return encrypted_bytes.decode("utf-8")
    except Exception as exc:
        logger.error("Failed to encrypt string: %s", exc)
        raise EncryptionUnavailableError("Sensitive value encryption failed.") from exc


def decrypt_string(ciphertext: str) -> str:
    """Decrypt an AES-256 ciphertext string.

    For sensitive fields we fail closed when encryption is unavailable or
    ciphertext integrity cannot be verified.
    """
    if not ciphertext:
        return ""

    require_encryption()

    try:
        decrypted_bytes = _fernet.decrypt(ciphertext.encode("utf-8"))
        return decrypted_bytes.decode("utf-8")
    except InvalidToken:
        logger.error("Security Event: Invalid token during decryption (tampered or unencrypted data).")
        raise ValueError("Decryption failed: Cannot verify ciphertext integrity.")
    except Exception as exc:
        logger.error("Failed to decrypt string: %s", exc)
        raise ValueError(f"Decryption failed critically: {exc}")
