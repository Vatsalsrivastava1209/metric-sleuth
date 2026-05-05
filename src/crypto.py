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

_fernet: Fernet | None = None
if _APP_SECRET_KEY:
    try:
        _fernet = Fernet(_APP_SECRET_KEY.encode("utf-8"))
    except Exception as exc:
        logger.error("Failed to initialize Fernet with APP_SECRET_KEY: %s", exc)
else:
    logger.warning("APP_SECRET_KEY is not set. Encryption will be disabled (fallback to plaintext).")


def encrypt_string(plaintext: str) -> str:
    """Encrypt a plaintext string using AES-256.
    
    If encryption is disabled (no secret key), returns the original string
    but logs a warning.
    """
    if not plaintext:
        return ""
        
    if _fernet is None:
        logger.warning("Encryption disabled. Returning plaintext string.")
        return plaintext
        
    try:
        encrypted_bytes = _fernet.encrypt(plaintext.encode("utf-8"))
        return encrypted_bytes.decode("utf-8")
    except Exception as exc:
        logger.error("Failed to encrypt string: %s", exc)
        return plaintext


def decrypt_string(ciphertext: str) -> str:
    """Decrypt an AES-256 ciphertext string.
    
    If the string is not valid Fernet ciphertext (e.g. it was stored before
    encryption was enabled), this gracefully falls back and returns the
    string as-is.
    """
    if not ciphertext:
        return ""
        
    if _fernet is None:
        return ciphertext
        
    try:
        decrypted_bytes = _fernet.decrypt(ciphertext.encode("utf-8"))
        return decrypted_bytes.decode("utf-8")
    except InvalidToken:
        logger.error("Security Event: Invalid token during decryption (tampered or unencrypted data).")
        raise ValueError("Decryption failed: Cannot verify ciphertext integrity.")
    except Exception as exc:
        logger.error("Failed to decrypt string: %s", exc)
        raise ValueError(f"Decryption failed critically: {exc}")
