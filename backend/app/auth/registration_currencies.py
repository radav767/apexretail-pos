from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class RegistrationCurrencyDefinition:
    code: str
    display_name: str
    symbol: str
    decimal_places: int


# Registration uses an explicit, server-owned catalog so a client cannot pair
# a known currency code with a misleading symbol or precision. Additional
# accepted currencies remain company-configurable after registration.
REGISTRATION_CURRENCIES = (
    RegistrationCurrencyDefinition("USD", "US Dollar", "$", 2),
    RegistrationCurrencyDefinition("EUR", "Euro", "€", 2),
    RegistrationCurrencyDefinition("GBP", "Pound Sterling", "£", 2),
    RegistrationCurrencyDefinition("ZAR", "South African Rand", "R", 2),
    RegistrationCurrencyDefinition("ZWG", "Zimbabwe Gold", "ZiG", 2),
    RegistrationCurrencyDefinition("BWP", "Botswana Pula", "P", 2),
    RegistrationCurrencyDefinition("NAD", "Namibian Dollar", "N$", 2),
    RegistrationCurrencyDefinition("ZMW", "Zambian Kwacha", "K", 2),
    RegistrationCurrencyDefinition("MZN", "Mozambican Metical", "MT", 2),
    RegistrationCurrencyDefinition("KES", "Kenyan Shilling", "KSh", 2),
    RegistrationCurrencyDefinition("NGN", "Nigerian Naira", "₦", 2),
    RegistrationCurrencyDefinition("GHS", "Ghanaian Cedi", "GH₵", 2),
    RegistrationCurrencyDefinition("AUD", "Australian Dollar", "A$", 2),
    RegistrationCurrencyDefinition("CAD", "Canadian Dollar", "C$", 2),
    RegistrationCurrencyDefinition("JPY", "Japanese Yen", "¥", 0),
)

REGISTRATION_CURRENCY_BY_CODE = {
    currency.code: currency for currency in REGISTRATION_CURRENCIES
}


def serialize_registration_currencies() -> list[dict[str, str | int]]:
    return [asdict(currency) for currency in REGISTRATION_CURRENCIES]
