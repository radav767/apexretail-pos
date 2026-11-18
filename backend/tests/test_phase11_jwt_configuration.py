"""Fail closed on unsafe business JWT configuration, without real settings."""
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from pydantic import ValidationError

from app.auth.security import (
    create_access_token, create_employee_access_token, create_offline_shift_token,
    decode_access_token, decode_offline_shift_token,
)
from app.core.config import Settings


class JwtConfigurationTests(unittest.TestCase):
    secret = 'synthetic-configuration-test-key-0123456789'

    def test_invalid_sink_key_fails_at_configuration_for_all_accounts(self):
        with self.assertRaises(ValidationError):
            Settings(database_url='postgresql://synthetic@localhost/unreachable', jwt_secret=self.secret,
                     app_env='test', business_email_mode='sink', business_email_key='invalid-test-key', _env_file=None)

    def settings(self, secret):
        return Settings(database_url='postgresql://synthetic@localhost/unreachable',
                        jwt_secret=secret, _env_file=None)

    def test_blank_short_and_placeholder_configuration_fails_without_secret_in_error(self):
        for secret in ('', ' ' * 64, 'short-test-secret', 'CHANGE_THIS_TO_A_LONG_RANDOM_SECRET'):
            with self.subTest(secret=secret):
                with self.assertRaises(ValidationError) as error:
                    self.settings(secret)
                self.assertNotIn('input_value', str(error.exception))

    def test_valid_configuration_preserves_exact_key_bytes_and_legacy_tokens(self):
        settings = self.settings(self.secret)
        self.assertEqual(settings.jwt_secret, self.secret)
        with patch('app.auth.security.get_settings', return_value=settings):
            token = create_access_token('synthetic-user', 'owner@example.invalid')
            self.assertEqual(decode_access_token(token)['sub'], 'synthetic-user')
            token = create_employee_access_token(employee_id='synthetic-employee',
                                                company_id='synthetic-company', role='cashier')
            self.assertEqual(decode_access_token(token)['token_type'], 'employee')
            token = create_offline_shift_token(shift_id='shift', company_id='company',
                                              branch_id='branch', device_id='device',
                                              employee_id='employee', opened_at='2026-11-18T00:00:00Z')
            self.assertEqual(decode_offline_shift_token(token)['shift_id'], 'shift')

    def test_signing_and_both_decoders_cannot_use_fallback_even_if_settings_are_bypassed(self):
        for secret in ('', ' ', 'short', 'CHANGE_THIS_TO_A_LONG_RANDOM_SECRET'):
            with self.subTest(secret=secret), patch('app.auth.security.get_settings',
                    return_value=SimpleNamespace(jwt_secret=secret, jwt_algorithm='HS256')):
                with self.assertRaises(ValueError):
                    create_access_token('user', 'owner@example.invalid')
                with self.assertRaises(ValueError):
                    decode_access_token('irrelevant-token')
                with self.assertRaises(ValueError):
                    decode_offline_shift_token('irrelevant-token', verify_expiration=False)

    def test_hmac_algorithm_strength_floors_and_unsigned_configuration(self):
        for algorithm, length in (('HS256', 32), ('HS384', 48), ('HS512', 64)):
            with self.subTest(algorithm=algorithm):
                with self.assertRaises(ValidationError):
                    Settings(database_url='postgresql://synthetic@localhost/unreachable',
                             jwt_secret='s' * (length - 1), jwt_algorithm=algorithm, _env_file=None)
                settings = Settings(database_url='postgresql://synthetic@localhost/unreachable',
                                    jwt_secret='s' * length, jwt_algorithm=algorithm, _env_file=None)
                with patch('app.auth.security.get_settings', return_value=settings):
                    self.assertEqual(decode_access_token(create_access_token('user', 'test@example.invalid'))['sub'], 'user')
        for algorithm in ('', 'none', 'None'):
            with self.subTest(algorithm=algorithm), self.assertRaises(ValidationError):
                Settings(database_url='postgresql://synthetic@localhost/unreachable',
                         jwt_secret=self.secret, jwt_algorithm=algorithm, _env_file=None)
