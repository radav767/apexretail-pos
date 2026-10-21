"""Regression mitigations for unpatched dependency advisories; synthetic keys."""
import base64
import hashlib
import hmac
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import JWTError
from jose.backends import ECKey, RSAKey
from app.auth.security import decode_access_token


class JwtDependencyGuards(unittest.TestCase):
    def test_cryptography_backend_not_python_ecdsa_is_selected(self):
        self.assertEqual(ECKey.__module__, 'jose.backends.cryptography_backend')
        self.assertEqual(RSAKey.__module__, 'jose.backends.cryptography_backend')

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
