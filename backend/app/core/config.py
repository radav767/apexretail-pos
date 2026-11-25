from dataclasses import dataclass
from functools import lru_cache
from os import environ
from typing import Literal
from urllib.parse import urlsplit

from pydantic import ValidationError,SecretStr,model_validator
from pydantic_settings import BaseSettings
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


def validate_jwt_secret(value: str, algorithm: str = 'HS256') -> str:
    # A length floor is not an entropy estimate. Operators must still supply
    # independently generated random keys; never silently substitute a key.
    if (not isinstance(value, str) or not value.strip()
            or len(value.encode('utf-8')) < {'HS384': 48, 'HS512': 64}.get(algorithm, 32)
            or value.strip() == 'CHANGE_THIS_TO_A_LONG_RANDOM_SECRET'):
        raise ValueError('JWT_SECRET must meet the signing algorithm key length floor (at least 32 bytes) and must not use the default placeholder')
    if not algorithm or algorithm.lower() == 'none':
        raise ValueError('JWT_ALGORITHM must specify a signed token algorithm')
    return value


class Settings(BaseSettings):
    app_name: str = "ApexRetail POS"
    app_env: str = "production"
    database_url: str
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 1440
    subscription_offline_grace_hours: int = 72
    subscription_provider_name: str | None = None
    subscription_provider_checkout_base_url: str | None = None
    subscription_provider_webhook_secret: str | None = None
    subscription_webhook_signature_header: str = "x-apex-signature"
    paynow_integration_id: str | None = None
    paynow_integration_key: str | None = None
    paynow_return_url: str | None = None
    paynow_result_url: str | None = None
    entitlement_signing_algorithm: str = "RS256"
    entitlement_private_key: str | None = None
    entitlement_public_key: str | None = None
    entitlement_active_key_id: str | None = None
    entitlement_signing_key_file: str | None = None
    entitlement_signing_key_credential: str | None = None
    entitlement_public_keyring_file: str | None = None
    entitlement_legacy_key_id: str | None = None
    entitlement_legacy_accept_until: str | None = None
    entitlement_max_token_lifetime_seconds: int = 43200
    entitlement_max_offline_grace_seconds: int = 259200
    product_image_root: str = "/var/lib/apexretail/product-images"
    product_image_max_bytes: int = 5242880
    platform_mfa_key: SecretStr | None = None
    backoffice_origin: str = 'https://backoffice.apexpos.cloud'
    business_email_mode: Literal['disabled', 'sink'] = 'disabled'
    business_email_key: SecretStr | None = None
    document_delivery_mode: Literal['disabled','sink'] = 'disabled'
    document_delivery_key: SecretStr | None = None
    split_checkout_mode: Literal['disabled','test'] = 'disabled'
    quotation_pricing_mode: Literal['disabled','test'] = 'disabled'

    @model_validator(mode='after')
    def validate_jwt_configuration(self):
        validate_jwt_secret(self.jwt_secret, self.jwt_algorithm)
        origin = urlsplit(self.backoffice_origin)
        if origin.scheme != 'https' or not origin.hostname or origin.username or origin.password or origin.path or origin.query or origin.fragment:
            raise ValueError('BACKOFFICE_ORIGIN must be an HTTPS origin without path or credentials')
        if self.business_email_mode == 'sink' and (self.app_env != 'test' or not self.business_email_key):
            raise ValueError('Business email sink requires APP_ENV=test and an explicit encryption key')
        if self.business_email_mode == 'sink':
            from cryptography.fernet import Fernet
            try: Fernet(self.business_email_key.get_secret_value().encode())
            except (ValueError, TypeError): raise ValueError('BUSINESS_EMAIL_KEY must be a valid Fernet key') from None
        if self.document_delivery_mode=='sink':
            if self.app_env!='test' or not self.document_delivery_key:raise ValueError('Document sink requires APP_ENV=test and an explicit test encryption key')
            from cryptography.fernet import Fernet
            try:Fernet(self.document_delivery_key.get_secret_value().encode())
            except (ValueError,TypeError):raise ValueError('DOCUMENT_DELIVERY_KEY must be a valid Fernet key') from None
        if self.split_checkout_mode=='test' and self.app_env!='test':raise ValueError('Split checkout test mode requires APP_ENV=test; production acceptance remains disabled')
        if self.quotation_pricing_mode=='test' and self.app_env!='test':raise ValueError('Saved quotation pricing test mode requires APP_ENV=test')
        return self

    class Config:
        env_file = ".env"
        hide_input_in_errors = True


@dataclass(frozen=True)
class DatabaseURLs:
    raw: str
    async_url: str
    alembic_url: str
    database_name: str | None

    @property
    def redacted_async_url(self) -> str:
        return _redact_database_url(self.async_url)

    @property
    def redacted_alembic_url(self) -> str:
        return _redact_database_url(self.alembic_url)


def _redact_database_url(database_url: str) -> str:
    return make_url(database_url).render_as_string(hide_password=True)


def _normalize_async_driver(drivername: str) -> str:
    if drivername in {"postgresql+asyncpg", "postgres+asyncpg"}:
        return drivername
    if drivername in {
        "postgresql",
        "postgres",
        "postgresql+psycopg2",
        "postgres+psycopg2",
    }:
        return "postgresql+asyncpg"
    raise RuntimeError(
        "DATABASE_URL must use a supported PostgreSQL dialect. "
        f"Received driver '{drivername}'."
    )


def _normalize_alembic_driver(drivername: str) -> str:
    if drivername in {
        "postgresql",
        "postgres",
        "postgresql+psycopg2",
        "postgres+psycopg2",
    }:
        return "postgresql+psycopg2"
    if drivername in {"postgresql+asyncpg", "postgres+asyncpg"}:
        return "postgresql+psycopg2"
    raise RuntimeError(
        "DATABASE_URL must use a supported PostgreSQL dialect. "
        f"Received driver '{drivername}'."
    )


def _load_raw_database_url(
    *,
    explicit_url: str | None = None,
    env: dict[str, str] | None = None,
) -> str:
    if explicit_url:
        return explicit_url

    if env is not None:
        return env.get("DATABASE_URL", "")

    env_database_url = environ.get("DATABASE_URL")
    if env_database_url:
        return env_database_url

    try:
        return Settings().database_url
    except ValidationError as exc:
        raise RuntimeError(
            "DATABASE_URL is required. Set it explicitly or provide it in backend/.env."
        ) from exc


def resolve_database_urls(
    *,
    explicit_url: str | None = None,
    env: dict[str, str] | None = None,
) -> DatabaseURLs:
    raw_url = _load_raw_database_url(explicit_url=explicit_url, env=env).strip()
    if not raw_url:
        raise RuntimeError(
            "DATABASE_URL is empty. Set it explicitly or provide it in backend/.env."
        )

    try:
        parsed = make_url(raw_url)
    except ArgumentError as exc:
        raise RuntimeError(
            f"Malformed DATABASE_URL: {raw_url!r}. Expected a valid SQLAlchemy URL."
        ) from exc

    async_url = parsed.set(
        drivername=_normalize_async_driver(parsed.drivername)
    ).render_as_string(hide_password=False)
    alembic_url = parsed.set(
        drivername=_normalize_alembic_driver(parsed.drivername)
    ).render_as_string(hide_password=False)

    return DatabaseURLs(
        raw=raw_url,
        async_url=async_url,
        alembic_url=alembic_url,
        database_name=parsed.database,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
