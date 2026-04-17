"""Encryption utilities for MemText entries.

Uses AES-256-GCM via Fernet (AES-128-CBC with HMAC) for simplicity and security.
Key derivation uses PBKDF2-HMAC-SHA256.
"""

import base64
import hashlib
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.backends import default_backend
import os

from memtext.db import get_db_path, update_entry, get_entry


def derive_key(password: str, salt: Optional[bytes] = None) -> tuple[bytes, bytes]:
    """Derive encryption key from password using PBKDF2."""
    if salt is None:
        salt = os.urandom(16)
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,  # 256-bit key for AES-256
        salt=salt,
        iterations=100_000,
        backend=default_backend(),
    )
    key = kdf.derive(password.encode())
    return key, salt


def encrypt_content(plaintext: str, password: str) -> tuple[str, bytes, bytes]:
    """Encrypt content using AES-256-GCM. Returns (ciphertext_b64, salt, nonce)."""
    key, salt = derive_key(password)
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    plaintext_bytes = plaintext.encode("utf-8")
    ciphertext = aesgcm.encrypt(nonce, plaintext_bytes, None)
    ciphertext_b64 = base64.b64encode(ciphertext).decode("utf-8")
    return ciphertext_b64, salt, nonce


def decrypt_content(
    ciphertext_b64: str, password: str, salt: bytes, nonce: bytes
) -> str:
    """Decrypt content using AES-256-GCM. Returns plaintext."""
    key, _ = derive_key(password, salt)
    aesgcm = AESGCM(key)
    ciphertext = base64.b64decode(ciphertext_b64)
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext.decode("utf-8")


def encrypt_entry(entry_id: int, password: str) -> bool:
    """Encrypt an entry's content. Title remains unencrypted for search."""
    entry = get_entry(entry_id)
    if not entry:
        return False

    content = entry.get("content", "")
    if not content:
        return False

    try:
        ciphertext_b64, salt, nonce = encrypt_content(content, password)
        encrypted_data = {
            "ciphertext": ciphertext_b64,
            "salt": base64.b64encode(salt).decode("utf-8"),
            "nonce": base64.b64encode(nonce).decode("utf-8"),
        }
        # Update entry: mark as encrypted, store encrypted blob, clear plaintext content
        conn = __import__("sqlite3").connect(get_db_path())
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE context_entries SET is_encrypted = 1, encrypted_content = ?, content = '' WHERE id = ?",
            (str(encrypted_data), entry_id),
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False

    content = entry.get("content", "")
    if not content:
        return False

    try:
        ciphertext_b64, salt, nonce = encrypt_content(content, password)
        # Store encryption metadata
        encrypted_data = {
            "ciphertext": ciphertext_b64,
            "salt": base64.b64encode(salt).decode("utf-8"),
            "nonce": base64.b64encode(nonce).decode("utf-8"),
        }
        success = update_entry(
            entry_id,
            is_encrypted=1,
            encrypted_content=entry.get(
                "encrypted_content", ""
            ),  # preserve existing if any
        )
        # Actually we need to set encrypted_content properly
        conn = __import__("sqlite3").connect(get_db_path())
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE context_entries SET is_encrypted = 1, encrypted_content = ? WHERE id = ?",
            (str(encrypted_data), entry_id),
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def decrypt_entry(entry_id: int, password: str) -> Optional[str]:
    """Decrypt an entry's content. Returns the decrypted content or None on failure."""
    entry = get_entry(entry_id)
    if not entry or not entry.get("is_encrypted"):
        return None

    encrypted_data_str = entry.get("encrypted_content", "")
    if not encrypted_data_str:
        return None

    try:
        import ast

        encrypted_data = ast.literal_eval(encrypted_data_str)
        ciphertext_b64 = encrypted_data["ciphertext"]
        salt_b64 = encrypted_data["salt"]
        nonce_b64 = encrypted_data["nonce"]
        salt = base64.b64decode(salt_b64)
        nonce = base64.b64decode(nonce_b64)
        return decrypt_content(ciphertext_b64, password, salt, nonce)
    except Exception:
        return None


def is_entry_encrypted(entry_id: int) -> bool:
    """Check if an entry is encrypted."""
    entry = get_entry(entry_id)
    return entry is not None and bool(entry.get("is_encrypted"))
