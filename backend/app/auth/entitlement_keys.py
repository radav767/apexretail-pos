from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import re
from typing import Any


UTC = timezone.utc
KID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
logger = logging.getLogger(__name__)


class EntitlementKeyConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class EntitlementPublicKey:
    kid: str
    public_key_pem: str
    accept_until: datetime | None


@dataclass(frozen=True)
class EntitlementKeyring:
    keys: dict[str, EntitlementPublicKey]
    legacy_key_id: str | None
    legacy_accept_until: datetime | None
    max_token_lifetime_seconds: int
    max_offline_grace_seconds: int


def safe_kid(value: object) -> str | None:
    candidate = str(value or "").strip()
    return candidate if KID_PATTERN.fullmatch(candidate) else None


def _parse_deadline(value: object, field: str) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise EntitlementKeyConfigurationError(
            f"{field} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise EntitlementKeyConfigurationError(f"{field} must include a timezone")
    return parsed.astimezone(UTC)


def _positive_int(value: Any, field: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise EntitlementKeyConfigurationError(f"{field} must be an integer") from exc
    if parsed <= 0:
        raise EntitlementKeyConfigurationError(f"{field} must be positive")
    return parsed


def _read_text_file(path_value: str, description: str) -> str:
    path = Path(path_value).expanduser()
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise EntitlementKeyConfigurationError(
            f"Unable to read configured {description} file"
        ) from exc


def _read_private_key_file(path_value: str) -> str:
    path = Path(path_value).expanduser()
    try:
        mode = path.stat().st_mode & 0o777
    except OSError as exc:
        raise EntitlementKeyConfigurationError(
            "Unable to inspect configured entitlement signing key file"
        ) from exc
    if mode & 0o077:
        raise EntitlementKeyConfigurationError(
            "Entitlement signing key file must not be accessible by group or others"
        )
    return _read_text_file(str(path), "entitlement signing key")


def load_signing_key(settings: Any) -> str:
    credential_name = str(
        getattr(settings, "entitlement_signing_key_credential", "") or ""
    ).strip()
    configured_path = str(
        getattr(settings, "entitlement_signing_key_file", "") or ""
    ).strip()

    if credential_name:
        if Path(credential_name).name != credential_name:
            raise EntitlementKeyConfigurationError(
                "ENTITLEMENT_SIGNING_KEY_CREDENTIAL must be a credential filename"
            )
        credentials_directory = os.environ.get("CREDENTIALS_DIRECTORY", "").strip()
        if not credentials_directory:
            raise EntitlementKeyConfigurationError(
                "CREDENTIALS_DIRECTORY is required for the configured signing credential"
            )
        configured_path = str(Path(credentials_directory) / credential_name)

    if configured_path:
        key = _read_private_key_file(configured_path)
    else:
        # Compatibility only. Operators should migrate this deprecated inline value
        # to a protected file or systemd credential before rotation.
        key = str(getattr(settings, "entitlement_private_key", "") or "")
        if key:
            logger.warning(
                "entitlement_inline_private_key_deprecated migrate_to=protected_file_or_credential"
            )

    if "PRIVATE KEY" not in key or "PUBLIC KEY" in key:
        raise EntitlementKeyConfigurationError(
            "Configured entitlement signing key is not a private PEM key"
        )
    return key.strip()


def _keyring_from_payload(payload: dict[str, Any], settings: Any) -> EntitlementKeyring:
    if payload.get("version") != 1:
        raise EntitlementKeyConfigurationError(
            "Entitlement public keyring version must be 1"
        )
    raw_keys = payload.get("keys")
    if not isinstance(raw_keys, list) or not raw_keys:
        raise EntitlementKeyConfigurationError(
            "Entitlement public keyring must contain at least one key"
        )

    keys: dict[str, EntitlementPublicKey] = {}
    for raw_key in raw_keys:
        if not isinstance(raw_key, dict):
            raise EntitlementKeyConfigurationError("Invalid entitlement key entry")
        kid = safe_kid(raw_key.get("kid"))
        if not kid:
            raise EntitlementKeyConfigurationError(
                "Entitlement key IDs must use 1-64 letters, numbers, '.', '_' or '-'"
            )
        if kid in keys:
            raise EntitlementKeyConfigurationError(
                f"Duplicate entitlement key ID: {kid}"
            )
        public_key = str(raw_key.get("public_key_pem") or "").replace("\\n", "\n").strip()
        if "-----BEGIN PUBLIC KEY-----" not in public_key or "PRIVATE KEY" in public_key:
            raise EntitlementKeyConfigurationError(
                f"Entitlement key {kid} is not a public PEM key"
            )
        keys[kid] = EntitlementPublicKey(
            kid=kid,
            public_key_pem=public_key,
            accept_until=_parse_deadline(
                raw_key.get("accept_until"), f"keys[{kid}].accept_until"
            ),
        )

    legacy = payload.get("legacy_no_kid")
    legacy_key_id = None
    legacy_accept_until = None
    if legacy is not None:
        if not isinstance(legacy, dict):
            raise EntitlementKeyConfigurationError("legacy_no_kid must be an object")
        legacy_key_id = safe_kid(legacy.get("kid"))
        if not legacy_key_id or legacy_key_id not in keys:
            raise EntitlementKeyConfigurationError(
                "legacy_no_kid must designate a key present in the keyring"
            )
        legacy_accept_until = _parse_deadline(
            legacy.get("accept_until"), "legacy_no_kid.accept_until"
        )
        if legacy_accept_until is None:
            raise EntitlementKeyConfigurationError(
                "legacy_no_kid requires a bounded accept_until timestamp"
            )
        key_deadline = keys[legacy_key_id].accept_until
        if key_deadline and legacy_accept_until > key_deadline:
            raise EntitlementKeyConfigurationError(
                "Legacy acceptance cannot extend beyond its key retirement deadline"
            )

    return EntitlementKeyring(
        keys=keys,
        legacy_key_id=legacy_key_id,
        legacy_accept_until=legacy_accept_until,
        max_token_lifetime_seconds=_positive_int(
            payload.get(
                "max_token_lifetime_seconds",
                getattr(settings, "entitlement_max_token_lifetime_seconds", 43200),
            ),
            "max_token_lifetime_seconds",
        ),
        max_offline_grace_seconds=_positive_int(
            payload.get(
                "max_offline_grace_seconds",
                getattr(settings, "entitlement_max_offline_grace_seconds", 259200),
            ),
            "max_offline_grace_seconds",
        ),
    )


def load_public_keyring(settings: Any) -> EntitlementKeyring:
    path = str(
        getattr(settings, "entitlement_public_keyring_file", "") or ""
    ).strip()
    if path:
        try:
            payload = json.loads(_read_text_file(path, "entitlement public keyring"))
        except json.JSONDecodeError as exc:
            raise EntitlementKeyConfigurationError(
                "Entitlement public keyring is not valid JSON"
            ) from exc
        if not isinstance(payload, dict):
            raise EntitlementKeyConfigurationError(
                "Entitlement public keyring root must be an object"
            )
        return _keyring_from_payload(payload, settings)

    # Explicit compatibility adapter for an existing single public key. It is
    # accepted only when an operator supplies both a designated legacy key ID
    # and a bounded deadline; no implicit legacy trust is created.
    public_key = str(getattr(settings, "entitlement_public_key", "") or "").strip()
    legacy_kid = safe_kid(getattr(settings, "entitlement_legacy_key_id", None))
    legacy_deadline = getattr(settings, "entitlement_legacy_accept_until", None)
    if public_key and legacy_kid and legacy_deadline:
        payload = {
            "version": 1,
            "keys": [
                {
                    "kid": legacy_kid,
                    "public_key_pem": public_key,
                    "accept_until": legacy_deadline,
                }
            ],
            "legacy_no_kid": {
                "kid": legacy_kid,
                "accept_until": legacy_deadline,
            },
        }
        return _keyring_from_payload(payload, settings)

    raise EntitlementKeyConfigurationError(
        "A public entitlement keyring is required; legacy single-key verification "
        "also requires an explicit key ID and acceptance deadline"
    )
