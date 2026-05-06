import pytest

from src import crypto
from src.db import _deserialize_connection_config


def test_encrypt_string_fails_closed_without_secret(monkeypatch):
    monkeypatch.setattr(crypto, "_fernet", None)

    with pytest.raises(crypto.EncryptionUnavailableError):
        crypto.encrypt_string("super-secret-token")


def test_plaintext_sensitive_connection_config_is_rejected():
    with pytest.raises(crypto.EncryptionUnavailableError):
        _deserialize_connection_config(
            {
                "connector_type": "shopify",
                "access_token": "plain-text-token",
            }
        )
