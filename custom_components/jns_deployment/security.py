from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import base64
import hashlib
import json

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .const import SIGNATURE_ALGORITHM, SIGNATURE_DOMAIN, TRUST_STORE_FILE


class SecurityError(Exception):
    """Raised when publisher trust or signature verification fails."""


@dataclass(frozen=True)
class TrustedPublisher:
    publisher_id: str
    name: str
    public_key_b64: str
    fingerprint_sha256: str
    scopes: frozenset[str]


class TrustStore:
    """Read-only runtime publisher trust store."""

    def __init__(self, trust_dir: Path) -> None:
        self.trust_dir = trust_dir.resolve()
        self.path = self.trust_dir / TRUST_STORE_FILE
        self.trust_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _fingerprint(raw_key: bytes) -> str:
        return hashlib.sha256(raw_key).hexdigest()

    def load(self) -> dict[str, TrustedPublisher]:
        if not self.path.is_file():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SecurityError("Trusted publisher store is not valid JSON.") from exc
        if data.get("schema") != 1:
            raise SecurityError("Unsupported trusted publisher store schema.")
        records = data.get("publishers")
        if not isinstance(records, list):
            raise SecurityError("Trusted publisher store requires a publishers list.")

        publishers: dict[str, TrustedPublisher] = {}
        for record in records:
            if not isinstance(record, dict):
                raise SecurityError("Invalid publisher record.")
            publisher_id = str(record.get("id", "")).strip()
            if not publisher_id:
                raise SecurityError("Trusted publisher id is required.")
            if publisher_id in publishers:
                raise SecurityError(f"Duplicate trusted publisher id: {publisher_id}")
            if not record.get("enabled", True):
                continue
            key_b64 = str(record.get("public_key", "")).strip()
            try:
                raw_key = base64.b64decode(key_b64, validate=True)
            except Exception as exc:
                raise SecurityError(f"Invalid Base64 public key for {publisher_id}.") from exc
            if len(raw_key) != 32:
                raise SecurityError(f"Ed25519 public key for {publisher_id} must be 32 bytes.")
            fingerprint = self._fingerprint(raw_key)
            declared = record.get("fingerprint_sha256")
            if declared is not None and str(declared).lower() != fingerprint:
                raise SecurityError(f"Public-key fingerprint mismatch for {publisher_id}.")
            scopes_raw = record.get("scopes", [])
            if not isinstance(scopes_raw, list):
                raise SecurityError(f"Publisher scopes must be a list for {publisher_id}.")
            scopes = frozenset(str(item) for item in scopes_raw)
            unknown = scopes - {"config", "platform"}
            if unknown:
                raise SecurityError(
                    f"Unknown publisher scopes for {publisher_id}: " + ", ".join(sorted(unknown))
                )
            publishers[publisher_id] = TrustedPublisher(
                publisher_id=publisher_id,
                name=str(record.get("name") or publisher_id),
                public_key_b64=key_b64,
                fingerprint_sha256=fingerprint,
                scopes=scopes,
            )
        return publishers

    def list_publishers(self) -> dict[str, Any]:
        publishers = self.load()
        return {
            "configured": self.path.is_file(),
            "count": len(publishers),
            "path": str(self.path),
            "publishers": [
                {
                    "id": pub.publisher_id,
                    "name": pub.name,
                    "fingerprint_sha256": pub.fingerprint_sha256,
                    "scopes": sorted(pub.scopes),
                }
                for pub in sorted(publishers.values(), key=lambda item: item.publisher_id)
            ],
        }

    def verify(
        self,
        manifest_raw: bytes,
        manifest: dict[str, Any],
        signature: dict[str, Any],
        required_scope: str,
    ) -> TrustedPublisher:
        if signature.get("algorithm") != SIGNATURE_ALGORITHM:
            raise SecurityError("Unsupported package signature algorithm.")
        manifest_publisher = str(manifest.get("publisher_id", "")).strip()
        signature_publisher = str(signature.get("publisher_id", "")).strip()
        if not manifest_publisher or manifest_publisher != signature_publisher:
            raise SecurityError("Manifest and signature publisher ids do not match.")
        digest = hashlib.sha256(manifest_raw).hexdigest()
        if str(signature.get("manifest_sha256", "")).lower() != digest:
            raise SecurityError("Package manifest SHA-256 does not match signature metadata.")
        publishers = self.load()
        publisher = publishers.get(manifest_publisher)
        if publisher is None:
            raise SecurityError(f"Package publisher is not trusted: {manifest_publisher}")
        if required_scope not in publisher.scopes:
            raise SecurityError(
                f"Publisher {manifest_publisher} is not trusted for {required_scope} packages."
            )
        try:
            raw_public_key = base64.b64decode(publisher.public_key_b64, validate=True)
            signature_bytes = base64.b64decode(
                str(signature.get("signature", "")), validate=True
            )
        except Exception as exc:
            raise SecurityError("Invalid Base64 signature data.") from exc
        if len(signature_bytes) != 64:
            raise SecurityError("Ed25519 signature must be 64 bytes.")
        key = Ed25519PublicKey.from_public_bytes(raw_public_key)
        try:
            key.verify(signature_bytes, SIGNATURE_DOMAIN + manifest_raw)
        except InvalidSignature as exc:
            raise SecurityError("Ed25519 package signature verification failed.") from exc
        return publisher
