"""RSA key-pair authentication helpers.

Snowflake recommends key-pair authentication for service users instead of
passwords: the private key stays on our side (loaded from a file path given in
an environment variable), and only the public key is registered on the
Snowflake user (`ALTER USER ... SET RSA_PUBLIC_KEY='...'`).

This module:
* generates a key pair for local demos (`python -m app.security.keypair out_dir`),
* loads a private key from disk into the DER bytes the Snowflake connector expects,
* computes the public-key fingerprint Snowflake shows (`RSA_PUBLIC_KEY_FP`),
* signs/verifies a challenge to prove possession of the private key.
"""
from __future__ import annotations

import base64
import hashlib
import sys
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa


def generate_keypair(out_dir: str | Path, passphrase: str | None = None) -> tuple[Path, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    enc = (
        serialization.BestAvailableEncryption(passphrase.encode())
        if passphrase
        else serialization.NoEncryption()
    )
    priv = out / "rsa_key.p8"
    pub = out / "rsa_key.pub"
    priv.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, enc))
    pub.write_bytes(
        key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    )
    priv.chmod(0o600)
    return priv, pub


def load_private_key(path: str | Path, passphrase: str | None = None):
    return serialization.load_pem_private_key(
        Path(path).read_bytes(), password=passphrase.encode() if passphrase else None
    )


def private_key_der(path: str | Path, passphrase: str | None = None) -> bytes:
    """DER/PKCS8 bytes - the format `snowflake.connector.connect(private_key=...)` accepts."""
    return load_private_key(path, passphrase).private_bytes(
        serialization.Encoding.DER, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )


def public_key_fingerprint(public_pem_path: str | Path) -> str:
    pub = serialization.load_pem_public_key(Path(public_pem_path).read_bytes())
    der = pub.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return "SHA256:" + base64.b64encode(hashlib.sha256(der).digest()).decode()


def sign_challenge(private_path: str | Path, challenge: bytes, passphrase: str | None = None) -> bytes:
    key = load_private_key(private_path, passphrase)
    return key.sign(challenge, padding.PKCS1v15(), hashes.SHA256())


def verify_challenge(public_pem_path: str | Path, challenge: bytes, signature: bytes) -> bool:
    pub = serialization.load_pem_public_key(Path(public_pem_path).read_bytes())
    try:
        pub.verify(signature, challenge, padding.PKCS1v15(), hashes.SHA256())
        return True
    except Exception:  # noqa: BLE001 - any failure means "not verified"
        return False


if __name__ == "__main__":  # pragma: no cover
    target = sys.argv[1] if len(sys.argv) > 1 else "./keys"
    p, q = generate_keypair(target)
    print(f"Private key: {p}\nPublic key:  {q}\nFingerprint: {public_key_fingerprint(q)}")
    body = "".join(q.read_text().splitlines()[1:-1])
    print("\nRegister in Snowflake with:\n  ALTER USER TABLEFLOW_SVC SET RSA_PUBLIC_KEY='" + body + "';")
