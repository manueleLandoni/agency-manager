from __future__ import annotations

import base64
import os
from dataclasses import dataclass

from argon2.low_level import Type, hash_secret_raw
from cryptography.fernet import Fernet, InvalidToken


@dataclass
class CryptoContext:
    data_key: bytes


class CryptoManager:
    @staticmethod
    def generate_data_key() -> bytes:
        return Fernet.generate_key()

    @staticmethod
    def random_salt(length: int = 16) -> bytes:
        return os.urandom(length)

    @staticmethod
    def derive_user_key(password: str, salt: bytes) -> bytes:
        raw = hash_secret_raw(
            secret=password.encode("utf-8"),
            salt=salt,
            time_cost=3,
            memory_cost=65536,
            parallelism=2,
            hash_len=32,
            type=Type.ID,
        )
        return base64.urlsafe_b64encode(raw)

    @staticmethod
    def wrap_data_key(data_key: bytes, user_key: bytes) -> bytes:
        return Fernet(user_key).encrypt(data_key)

    @staticmethod
    def unwrap_data_key(wrapped_data_key: bytes, user_key: bytes) -> bytes:
        return Fernet(user_key).decrypt(wrapped_data_key)


def encrypt_field(value: str | None, data_key: bytes) -> bytes | None:
    if value is None or value == "":
        return None
    return Fernet(data_key).encrypt(value.encode("utf-8"))


def decrypt_field(value: bytes | None, data_key: bytes) -> str:
    if not value:
        return ""
    try:
        return Fernet(data_key).decrypt(value).decode("utf-8")
    except InvalidToken:
        return ""
