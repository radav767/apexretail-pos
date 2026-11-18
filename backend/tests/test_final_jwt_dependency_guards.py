"""JWT replacement regressions, legacy wire compatibility and synthetic attacks."""
import base64
import hashlib
import hmac
import json
import unittest
import importlib.metadata
from pathlib import Path
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import jwt
from jwt import PyJWTError as JWTError
from app.auth.security import (decode_access_token, create_access_token,
                               decode_offline_shift_token, create_offline_shift_token)


class JwtDependencyGuards(unittest.TestCase):
    def test_vulnerable_dependency_chain_is_absent_from_clean_environment(self):
        for package in ('ecdsa','python-jose','rsa','pyasn1'):
            with self.subTest(package=package),self.assertRaises(importlib.metadata.PackageNotFoundError):
                importlib.metadata.version(package)
        self.assertEqual(importlib.metadata.version('PyJWT'),'2.15.1')
        self.assertTrue(jwt.algorithms.has_crypto)

    def test_legacy_user_employee_and_offline_tokens_preserve_claims(self):
        fixture=json.loads((Path(__file__).parent/'fixtures/legacy-jose-tokens.json').read_text())
        with patch('app.auth.security.get_settings',return_value=SimpleNamespace(jwt_secret=fixture['secret'],jwt_algorithm='HS256')):
            for kind in ('access','employee'):
                self.assertEqual(decode_access_token(fixture['tokens'][kind]),fixture['claims'][kind])
            self.assertEqual(decode_offline_shift_token(fixture['tokens']['offline']),fixture['claims']['offline'])
            fresh=create_access_token('synthetic-user','fixture@example.invalid')
            self.assertEqual(decode_access_token(fresh)['token_type'],'user')

    def test_expired_offline_claims_only_accepted_by_explicit_recovery_policy(self):
        secret='synthetic-test-secret-long-enough-for-hmac-123456789'
        with patch('app.auth.security.get_settings',return_value=SimpleNamespace(jwt_secret=secret,jwt_algorithm='HS256')):
            token=jwt.encode({'sub':'synthetic-shift','token_type':'offline_shift','exp':1},secret,algorithm='HS256')
            with self.assertRaises(JWTError):decode_offline_shift_token(token)
            self.assertEqual(decode_offline_shift_token(token,verify_expiration=False)['sub'],'synthetic-shift')

    def test_unsigned_wrong_secret_wrong_algorithm_malformed_and_expired_fail(self):
        secret='synthetic-test-secret-long-enough-for-hmac-123456789'
        with patch('app.auth.security.get_settings',return_value=SimpleNamespace(jwt_secret=secret,jwt_algorithm='HS256')):
            cases=[jwt.encode({'sub':'fake'},None,algorithm='none'),
                   jwt.encode({'sub':'fake'},secret+'wrong',algorithm='HS256'),
                   jwt.encode({'sub':'fake'},secret,algorithm='HS512'),
                   jwt.encode({'sub':'fake','exp':1},secret,algorithm='HS256'),
                   jwt.encode({'sub':'fake','exp':[]},secret,algorithm='HS256'),
                   'invalid.token', '!!!!.!!!!.!!!!']
            for token in cases:
                with self.subTest(token=token[:12]),self.assertRaises(JWTError):decode_access_token(token)

    def test_der_public_key_cannot_authorize_hmac_token_under_rsa_policy(self):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public = key.public_key()
        der = public.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
        pem = public.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        encode = lambda value: base64.urlsafe_b64encode(value).rstrip(b'=')
        body = encode(json.dumps({'alg': 'HS256', 'typ': 'JWT'}).encode()) + b'.' + encode(json.dumps({'sub': 'synthetic-not-real'}).encode())
        forged = (body + b'.' + encode(hmac.new(der, body, hashlib.sha256).digest())).decode()
        with patch('app.auth.security.get_settings', return_value=SimpleNamespace(jwt_secret=pem, jwt_algorithm='RS256')):
            with self.assertRaises(JWTError): decode_access_token(forged)
