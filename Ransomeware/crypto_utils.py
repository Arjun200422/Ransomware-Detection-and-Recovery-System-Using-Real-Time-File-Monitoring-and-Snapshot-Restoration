# crypto_utils.py
# Shared helper: derive key, encrypt_file, decrypt_file
import os
import base64
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.fernet import Fernet
from cryptography.hazmat.backends import default_backend

SALT_SIZE = 16
KDF_ITERS = 200_000

def derive_fernet_key(password: str, salt: bytes) -> bytes:
    """Derive a 32-byte key from password+salt and return base64 urlsafe key (Fernet)."""
    password_bytes = password.encode('utf-8')
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=KDF_ITERS,
        backend=default_backend()
    )
    key = kdf.derive(password_bytes)
    return base64.urlsafe_b64encode(key)

def encrypt_file(path: str, password: str) -> str:
    """Encrypt file at path -> writes path + '.enc' (salt + token). Returns output path."""
    with open(path, 'rb') as f:
        data = f.read()
    salt = os.urandom(SALT_SIZE)
    key = derive_fernet_key(password, salt)
    fernet = Fernet(key)
    token = fernet.encrypt(data)
    out_path = path + '.enc'
    with open(out_path, 'wb') as out:
        out.write(salt + token)
    return out_path

def decrypt_file(enc_path: str, password: str) -> str:
    """Decrypt enc_path (expects salt prefix) -> writes original filename (removing .enc) or .dec. Returns output path."""
    with open(enc_path, 'rb') as f:
        content = f.read()
    if len(content) <= SALT_SIZE:
        raise ValueError("File too short or missing salt + ciphertext")
    salt = content[:SALT_SIZE]
    token = content[SALT_SIZE:]
    key = derive_fernet_key(password, salt)
    fernet = Fernet(key)
    data = fernet.decrypt(token)  # will raise if wrong password / tampered
    if enc_path.endswith('.enc'):
        out_path = enc_path[:-4]
    else:
        out_path = enc_path + '.dec'
    if os.path.exists(out_path):
        raise FileExistsError(f"Output file already exists: {out_path}")
    with open(out_path, 'wb') as out:
        out.write(data)
    return out_path
