"""Thin encryption facade over the platform's EncryptionManager.

All PII in CIE tables flows through these two functions. If the team
later migrates to AES-256-GCM globally, swap the implementation here
without touching any model or pipeline code.
"""
from __future__ import annotations

from encryption_utils import EncryptedString, encryption_manager


EncryptedCallField = EncryptedString


def encrypt_field(value: str) -> str:
    return encryption_manager.encrypt(value)


def decrypt_field(ciphertext: str) -> str:
    return encryption_manager.decrypt(ciphertext)
