from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import jwt

from app.auth.security import (
    ENTITLEMENT_AUDIENCE,
    ENTITLEMENT_ISSUER,
    EntitlementVerificationError,
    create_entitlement_snapshot_token,
    decode_entitlement_token,
)


UTC = timezone.utc
COMPANY_ID = "69c2ce14-8e9f-46dc-b144-54e209a0c3df"


def generate_keypair() -> tuple[str, str]:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public_pem = private.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private_pem, public_pem


class EntitlementKeyRotationTest(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory(prefix="apex-entitlement-test-")
        self.addCleanup(self.directory.cleanup)
        self.now = datetime.now(UTC).replace(microsecond=0)
        self.old_private, self.old_public = generate_keypair()
        self.new_private, self.new_public = generate_keypair()
        self.signing_path = Path(self.directory.name) / "signing.pem"
        self.keyring_path = Path(self.directory.name) / "keyring.json"
        self._write_private(self.new_private)
        self._write_keyring()

    def _write_private(self, value: str):
        self.signing_path.write_text(value, encoding="utf-8")
        self.signing_path.chmod(0o600)

    def _write_keyring(self, *, old_deadline=None, legacy_deadline=None):
        old_deadline = old_deadline or self.now + timedelta(hours=2)
        legacy_deadline = legacy_deadline or self.now + timedelta(hours=1)
        payload = {
            "version": 1,
            "max_token_lifetime_seconds": 43200,
            "max_offline_grace_seconds": 259200,
            "keys": [
                {
                    "kid": "legacy-2026",
                    "public_key_pem": self.old_public,
                    "accept_until": old_deadline.isoformat(),
                },
                {
                    "kid": "active-2026",
                    "public_key_pem": self.new_public,
                },
            ],
            "legacy_no_kid": {
                "kid": "legacy-2026",
                "accept_until": legacy_deadline.isoformat(),
            },
        }
        self.keyring_path.write_text(json.dumps(payload), encoding="utf-8")

    def settings(self, *, kid="active-2026"):
        return SimpleNamespace(
            jwt_secret="unused",
            jwt_algorithm="HS256",
            entitlement_signing_algorithm="RS256",
            entitlement_private_key=None,
            entitlement_public_key=None,
            entitlement_active_key_id=kid,
            entitlement_signing_key_file=str(self.signing_path),
            entitlement_signing_key_credential=None,
            entitlement_public_keyring_file=str(self.keyring_path),
            entitlement_legacy_key_id=None,
            entitlement_legacy_accept_until=None,
            entitlement_max_token_lifetime_seconds=43200,
            entitlement_max_offline_grace_seconds=259200,
        )

    def claims(self, **overrides):
        claims = {
            "sub": COMPANY_ID,
            "company_id": COMPANY_ID,
            "status": "active",
            "plan": "monthly",
            "offline_grace_expires_at": (self.now + timedelta(hours=4)).isoformat(),
            "token_type": "entitlement",
            "iat": int(self.now.timestamp()),
            "exp": int((self.now + timedelta(hours=1)).timestamp()),
            "iss": ENTITLEMENT_ISSUER,
            "aud": ENTITLEMENT_AUDIENCE,
        }
        claims.update(overrides)
        return claims

    def encode(self, private_key, *, kid="active-2026", claims=None, algorithm="RS256"):
        headers = {"typ": "JWT"}
        if kid is not None:
            headers["kid"] = kid
        return jwt.encode(
            claims or self.claims(), private_key, algorithm=algorithm, headers=headers
        )

    def decode(self, token):
        with patch("app.auth.security.get_settings", return_value=self.settings()):
            return decode_entitlement_token(
                token, expected_company_id=COMPANY_ID, now=self.now
            )

    def assert_category(self, token, category):
        with self.assertRaises(EntitlementVerificationError) as raised:
            self.decode(token)
        self.assertEqual(raised.exception.category, category)

    def test_new_token_has_kid_and_validates(self):
        with patch("app.auth.security.get_settings", return_value=self.settings()):
            token = create_entitlement_snapshot_token(
                company_id=COMPANY_ID,
                status="active",
                plan="monthly",
                offline_grace_expires_at=self.now + timedelta(hours=4),
                snapshot_expires_at=self.now + timedelta(hours=1),
                issued_at=self.now,
            )
            claims = decode_entitlement_token(
                token, expected_company_id=COMPANY_ID, now=self.now
            )
        self.assertEqual(jwt.get_unverified_header(token)["kid"], "active-2026")
        self.assertEqual(claims["company_id"], COMPANY_ID)

    def test_original_jose_rsa_token_verifies_with_replacement(self):
        fixture=json.loads((Path(__file__).parent/'fixtures/legacy-jose-tokens.json').read_text())
        settings=self.settings()
        settings.entitlement_public_keyring_file=None
        settings.entitlement_public_key=fixture['public_key']
        settings.entitlement_legacy_key_id='synthetic-legacy'
        settings.entitlement_legacy_accept_until='2026-10-23T00:00:00+00:00'
        with patch('app.auth.security.get_settings',return_value=settings):
            claims=decode_entitlement_token(fixture['tokens']['entitlement'],
                       expected_company_id='synthetic-company',
                       now=datetime.fromtimestamp(fixture['claims']['entitlement']['iat'],UTC))
        self.assertEqual(claims,fixture['claims']['entitlement'])

    def test_valid_old_kid_and_bounded_no_kid_legacy(self):
        old_token = self.encode(self.old_private, kid="legacy-2026")
        legacy_claims = self.claims()
        for field in ("iat", "iss", "aud"):
            legacy_claims.pop(field)
        legacy_token = self.encode(self.old_private, kid=None, claims=legacy_claims)
        self.assertEqual(self.decode(old_token)["company_id"], COMPANY_ID)
        self.assertEqual(self.decode(legacy_token)["company_id"], COMPANY_ID)

        self._write_keyring(legacy_deadline=self.now - timedelta(seconds=1),
                            old_deadline=self.now + timedelta(hours=2))
        self.assert_category(legacy_token, "legacy_key_retired")

    def test_unknown_kid_algorithm_confusion_and_tampering_fail_closed(self):
        self.assert_category(
            self.encode(self.new_private, kid="unknown-2026"), "unknown_key_id"
        )
        hs_token = jwt.encode(
            self.claims(), "synthetic-test-secret", algorithm="HS256",
            headers={"kid": "active-2026", "typ": "JWT"},
        )
        self.assert_category(hs_token, "algorithm_mismatch")
        token = self.encode(self.new_private)
        parts = token.split(".")
        parts[2] = ("A" if parts[2][0] != "A" else "B") + parts[2][1:]
        self.assert_category(".".join(parts), "invalid_signature")

    def test_expiry_lifetime_grace_company_and_retirement_policies(self):
        self.assert_category(
            self.encode(self.new_private, claims=self.claims(
                exp=int((self.now - timedelta(seconds=1)).timestamp())
            )), "snapshot_expired"
        )
        self.assert_category(
            self.encode(self.new_private, claims=self.claims(
                exp=int((self.now + timedelta(days=30)).timestamp())
            )), "token_lifetime_exceeded"
        )
        self.assert_category(
            self.encode(self.new_private, claims=self.claims(
                offline_grace_expires_at=(self.now + timedelta(days=30)).isoformat()
            )), "offline_grace_exceeded"
        )
        other_company = "63cf8fd8-70b1-4f31-a4d6-d2b332a271b7"
        self.assert_category(
            self.encode(self.new_private, claims=self.claims(
                sub=other_company, company_id=other_company
            )), "company_mismatch"
        )
        self._write_keyring(old_deadline=self.now - timedelta(seconds=1),
                            legacy_deadline=self.now - timedelta(seconds=1))
        self.assert_category(
            self.encode(self.old_private, kid="legacy-2026"), "key_retired"
        )

    def test_systemd_credential_loading_uses_protected_test_file(self):
        credential_settings = self.settings()
        credential_settings.entitlement_signing_key_file = None
        credential_settings.entitlement_signing_key_credential = "entitlement-signing.pem"
        credential_path = Path(self.directory.name) / "entitlement-signing.pem"
        credential_path.write_text(self.new_private, encoding="utf-8")
        credential_path.chmod(0o600)
        with patch.dict(os.environ, {"CREDENTIALS_DIRECTORY": self.directory.name}), \
             patch("app.auth.security.get_settings", return_value=credential_settings):
            token = create_entitlement_snapshot_token(
                company_id=COMPANY_ID, status="active", plan="monthly",
                offline_grace_expires_at=self.now + timedelta(hours=4),
                snapshot_expires_at=self.now + timedelta(hours=1), issued_at=self.now,
            )
        self.assertEqual(jwt.get_unverified_header(token)["kid"], "active-2026")
