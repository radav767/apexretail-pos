from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
import hashlib
from typing import Any
from urllib.parse import parse_qsl


PAYNOW_INITIATE_URL = "https://www.paynow.co.zw/interface/initiatetransaction"
MONEY_QUANTUM = Decimal("0.01")


class PaynowError(Exception):
    pass


@dataclass(frozen=True)
class PaynowCredentials:
    integration_id: str
    integration_key: str
    return_url: str
    result_url: str

    @property
    def configured(self) -> bool:
        return all(
            [
                self.integration_id.strip(),
                self.integration_key.strip(),
                self.return_url.strip(),
                self.result_url.strip(),
            ]
        )


@dataclass(frozen=True)
class PaynowInitiationResult:
    status: str
    browser_url: str
    poll_url: str
    paynow_reference: str
    hash_value: str
    raw_fields: dict[str, str]


def quantize_amount(value: Decimal | str | int | float) -> Decimal:
    return Decimal(str(value)).quantize(
        MONEY_QUANTUM,
        rounding=ROUND_HALF_UP,
    )


def build_hash(
    pairs: Iterable[tuple[str, Any]],
    integration_key: str,
) -> str:
    payload = "".join(
        str(value if value is not None else "")
        for key, value in pairs
        if key.lower() != "hash"
    )
    payload += integration_key
    return hashlib.sha512(
        payload.encode("utf-8")
    ).hexdigest().upper()


def validate_hash(
    pairs: Iterable[tuple[str, Any]],
    integration_key: str,
) -> bool:
    pair_list = list(pairs)
    provided_hash = next(
        (
            str(value)
            for key, value in pair_list
            if key.lower() == "hash"
        ),
        "",
    ).strip()
    if not provided_hash:
        return False
    expected_hash = build_hash(
        pair_list,
        integration_key,
    )
    return provided_hash.upper() == expected_hash.upper()


def parse_form_body(body: bytes) -> list[tuple[str, str]]:
    return parse_qsl(
        body.decode("utf-8"),
        keep_blank_values=True,
    )


def fields_from_pairs(
    pairs: Iterable[tuple[str, str]],
) -> dict[str, str]:
    return {
        str(key): str(value)
        for key, value in pairs
    }


def normalize_payment_status(status: str | None) -> str:
    normalized = str(status or "").strip().lower()
    if normalized == "paid":
        return "paid"
    if normalized in {"cancelled", "canceled"}:
        return "cancelled"
    if normalized in {"failed", "error"}:
        return "failed"
    if normalized in {"created", "sent", "ok", "pending", "waiting"}:
        return "pending"
    if "cancel" in normalized:
        return "cancelled"
    if "fail" in normalized:
        return "failed"
    return "pending"


def parse_initiation_response(
    body: bytes,
    integration_key: str,
) -> PaynowInitiationResult:
    pairs = parse_form_body(body)
    if not pairs:
        raise PaynowError("Paynow returned an empty response.")
    if not validate_hash(pairs, integration_key):
        raise PaynowError("Paynow returned an invalid response signature.")

    fields = fields_from_pairs(pairs)
    status = fields.get("status", "")
    browser_url = fields.get("browserurl", "")
    poll_url = fields.get("pollurl", "")
    paynow_reference = fields.get("paynowreference", "")

    if normalize_payment_status(status) == "failed":
        raise PaynowError("Paynow could not start the payment.")
    if not browser_url or not poll_url or not paynow_reference:
        raise PaynowError("Paynow response is missing required payment links.")

    return PaynowInitiationResult(
        status=status,
        browser_url=browser_url,
        poll_url=poll_url,
        paynow_reference=paynow_reference,
        hash_value=fields.get("hash", ""),
        raw_fields=fields,
    )
