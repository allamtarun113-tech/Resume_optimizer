"""Symmetric encryption for secrets stored in the database (users' OpenAI keys)."""

from cryptography.fernet import Fernet, InvalidToken


class CryptoError(RuntimeError):
    pass


def _fernet(key: str) -> Fernet:
    if not key:
        raise CryptoError("APP_ENCRYPTION_KEY is not set")
    try:
        return Fernet(key.encode())
    except ValueError as exc:
        raise CryptoError("APP_ENCRYPTION_KEY is not a valid Fernet key") from exc


def encrypt(plaintext: str, key: str) -> str:
    return _fernet(key).encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str, key: str) -> str:
    try:
        return _fernet(key).decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise CryptoError("Stored secret can't be decrypted (was the key rotated?)") from exc
