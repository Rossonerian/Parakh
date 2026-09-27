"""Ed25519 signing keys for PolicyBundleV1 (detached signature over checksums.json).

The private key never lives in the repository: default location is
``$PARAKH_SIGNING_KEY`` or ``~/.config/parakh/signing_key.hex`` (mode 0600).
Karmi trusts bundles by public key id, configured on its side.
"""

from __future__ import annotations

import hashlib
import os
import secrets
from pathlib import Path
from typing import Any, Iterable

from model_lab.artifacts import ed25519
from model_lab.errors import IntegrityError, ValidationError

DEFAULT_KEY_PATH = Path.home() / ".config" / "parakh" / "signing_key.hex"


def key_path(path: str | Path | None = None) -> Path:
    return Path(path or os.environ.get("PARAKH_SIGNING_KEY") or DEFAULT_KEY_PATH).expanduser()


def key_id(public: bytes) -> str:
    return hashlib.sha256(public).hexdigest()[:16]


def generate_key(path: str | Path | None = None) -> dict[str, str]:
    """Create a new private key file (refuses to overwrite). Returns public key + id."""
    target = key_path(path)
    if target.exists():
        raise IntegrityError(f"signing key already exists at {target}; refusing to overwrite")
    target.parent.mkdir(parents=True, exist_ok=True)
    secret = secrets.token_bytes(32)
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="ascii") as handle:
        handle.write(secret.hex() + "\n")
    public = ed25519.public_key(secret)
    return {"path": str(target), "public_key": public.hex(), "key_id": key_id(public)}


def load_private(path: str | Path | None = None) -> bytes:
    target = key_path(path)
    if not target.is_file():
        raise ValidationError(f"no signing key at {target}; create one with `model-lab artifact keygen`")
    if target.stat().st_mode & 0o077:
        raise IntegrityError(f"signing key {target} is readable by other users; chmod 600 it")
    try:
        secret = bytes.fromhex(target.read_text(encoding="ascii").strip())
    except ValueError as exc:
        raise ValidationError("signing key file is not hex") from exc
    if len(secret) != 32:
        raise ValidationError("signing key must be 32 bytes")
    return secret


def sign(secret: bytes, data: bytes, *, signed_file: str) -> dict[str, Any]:
    public = ed25519.public_key(secret)
    return {"algorithm": "ed25519", "key_id": key_id(public), "public_key": public.hex(),
            "signature": ed25519.sign(secret, data).hex(), "signed_file": signed_file}


def verify(document: dict[str, Any], data: bytes, trusted_public_keys: Iterable[str]) -> list[str]:
    """Errors (empty = valid). The embedded public key must be one of the trusted keys."""
    errors: list[str] = []
    if document.get("algorithm") != "ed25519":
        return ["signature algorithm is not ed25519"]
    public_hex = str(document.get("public_key", ""))
    if public_hex not in set(trusted_public_keys):
        errors.append("signing key is not trusted")
    try:
        public, signature = bytes.fromhex(public_hex), bytes.fromhex(str(document.get("signature", "")))
    except ValueError:
        return errors + ["signature or public key is not hex"]
    if document.get("key_id") != key_id(public):
        errors.append("key_id does not match public key")
    if not ed25519.verify(public, data, signature):
        errors.append("signature does not verify")
    return errors
