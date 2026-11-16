import re
from dataclasses import dataclass
from decimal import Decimal

FREE_SHIPPING_FROM_MXN = Decimal("800.00")
LOCAL_RATE_MXN = Decimal("89.00")
NATIONAL_RATE_MXN = Decimal("149.00")

# Mexican postal codes 01000–16999 belong to Mexico City, where the shop ships from.
_LOCAL_PREFIXES = range(1, 17)


class InvalidPostalCode(ValueError):
    pass


@dataclass(frozen=True)
class ShippingQuote:
    postal_code: str
    zone: str
    cost_mxn: Decimal
    estimated_days: str

    def to_dict(self) -> dict:
        return {
            "codigo_postal": self.postal_code,
            "zona": self.zone,
            "costo_mxn": float(self.cost_mxn),
            "dias_estimados": self.estimated_days,
        }


def quote_shipping(postal_code: str, subtotal_mxn: Decimal) -> ShippingQuote:
    postal_code = postal_code.strip()
    if not re.fullmatch(r"\d{5}", postal_code) or postal_code.startswith("00"):
        raise InvalidPostalCode(f"'{postal_code}' no es un código postal mexicano válido (5 dígitos).")

    if int(postal_code[:2]) in _LOCAL_PREFIXES:
        zone, cost, days = "local (CDMX)", LOCAL_RATE_MXN, "1-2 días hábiles"
    else:
        zone, cost, days = "nacional", NATIONAL_RATE_MXN, "3-5 días hábiles"

    if subtotal_mxn >= FREE_SHIPPING_FROM_MXN:
        cost = Decimal("0.00")
    return ShippingQuote(postal_code, zone, cost, days)
