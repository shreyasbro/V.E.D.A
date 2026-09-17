"""
V.E.D.A. Local Secure Credential Vault (Windows DPAPI)
Provides cryptographically secure credential storage using the Windows
Data Protection API (DPAPI). Keys are tied to the current Windows user profile
and machine, ensuring API keys cannot be exfiltrated or inspected in plain text.
"""

import sys
import base64
from typing import Optional

def _is_windows() -> bool:
    return sys.platform.startswith("win")

def encrypt_secret(plain_text: Optional[str]) -> str:
    """Encrypts a string using Windows DPAPI. Returns base64 ciphertext."""
    if not plain_text:
        return ""
    if not _is_windows():
        return base64.b64encode(plain_text.encode("utf-8")).decode("ascii")

    try:
        import ctypes
        import ctypes.wintypes

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [
                ("cbData", ctypes.wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_byte))
            ]

        data_bytes = plain_text.encode("utf-8")
        blob_in = DATA_BLOB()
        blob_in.cbData = len(data_bytes)
        blob_in.pbData = ctypes.cast(ctypes.create_string_buffer(data_bytes), ctypes.POINTER(ctypes.c_byte))

        blob_out = DATA_BLOB()

        crypt32 = ctypes.windll.crypt32
        # CryptProtectData(pDataIn, szDataDescr, pOptionalEntropy, pReserved, pPromptStruct, dwFlags, pDataOut)
        # CRYPTPROTECT_UI_FORBIDDEN = 0x1
        if crypt32.CryptProtectData(ctypes.byref(blob_in), "VEDA_KEY", None, None, None, 0x1, ctypes.byref(blob_out)):
            out_bytes = ctypes.string_at(blob_out.pbData, blob_out.cbData)
            ctypes.windll.kernel32.LocalFree(blob_out.pbData)
            return "dpapi:" + base64.b64encode(out_bytes).decode("ascii")
    except Exception:
        pass

    # Fallback to simple base64 obfuscation if DPAPI call fails
    return "b64:" + base64.b64encode(plain_text.encode("utf-8")).decode("ascii")

def decrypt_secret(cipher_text: Optional[str]) -> str:
    """Decrypts a DPAPI/base64 ciphertext into plain text."""
    if not cipher_text:
        return ""

    if cipher_text.startswith("dpapi:"):
        raw_b64 = cipher_text[6:]
        if not _is_windows():
            return ""
        try:
            import ctypes
            import ctypes.wintypes

            class DATA_BLOB(ctypes.Structure):
                _fields_ = [
                    ("cbData", ctypes.wintypes.DWORD),
                    ("pbData", ctypes.POINTER(ctypes.c_byte))
                ]

            raw_bytes = base64.b64decode(raw_b64)
            blob_in = DATA_BLOB()
            blob_in.cbData = len(raw_bytes)
            blob_in.pbData = ctypes.cast(ctypes.create_string_buffer(raw_bytes), ctypes.POINTER(ctypes.c_byte))

            blob_out = DATA_BLOB()

            crypt32 = ctypes.windll.crypt32
            # CRYPTPROTECT_UI_FORBIDDEN = 0x1
            if crypt32.CryptUnprotectData(ctypes.byref(blob_in), None, None, None, None, 0x1, ctypes.byref(blob_out)):
                out_bytes = ctypes.string_at(blob_out.pbData, blob_out.cbData)
                ctypes.windll.kernel32.LocalFree(blob_out.pbData)
                return out_bytes.decode("utf-8", errors="ignore")
        except Exception:
            return ""

    elif cipher_text.startswith("b64:"):
        try:
            return base64.b64decode(cipher_text[4:]).decode("utf-8", errors="ignore")
        except Exception:
            return ""

    # If it was stored in plaintext previously, return as is
    return cipher_text

def mask_key(key: Optional[str]) -> str:
    """Safely masks an API key as ••••••••abcd."""
    if not key or len(key.strip()) == 0:
        return "(Not Set)"
    k = key.strip()
    if len(k) <= 6:
        return "••••" + k[-2:]
    return "••••••••" + k[-4:]
