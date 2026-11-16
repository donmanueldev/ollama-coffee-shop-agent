import csv
from dataclasses import dataclass
from decimal import Decimal
from functools import cache
from pathlib import Path

from coffee_agent.text import normalize

FREE_SHIPPING_FROM_NIO = Decimal("1600.00")
RATES_PATH = Path(__file__).resolve().parents[2] / "data" / "envios.csv"


class InvalidDepartment(ValueError):
    pass


@dataclass(frozen=True)
class ShippingRate:
    department: str
    cost_nio: Decimal
    estimated_days: str


@dataclass(frozen=True)
class ShippingQuote:
    department: str
    cost_nio: Decimal
    estimated_days: str

    def to_dict(self) -> dict:
        return {
            "departamento": self.department,
            "costo_nio": float(self.cost_nio),
            "dias_estimados": self.estimated_days,
        }


@cache
def _rates_by_name() -> dict[str, ShippingRate]:
    """Rates keyed by every accepted spelling: the department name and its aliases, normalized."""
    rates: dict[str, ShippingRate] = {}
    with RATES_PATH.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rate = ShippingRate(row["departamento"], Decimal(row["costo_nio"]), row["dias_estimados"])
            for name in [rate.department, *filter(None, row["alias"].split("|"))]:
                rates[normalize(name)] = rate
    return rates


def departments() -> list[str]:
    return sorted({rate.department for rate in _rates_by_name().values()})


def find_rate(name: str) -> ShippingRate:
    key = normalize(name).strip().removeprefix("departamento de ").removeprefix("region autonoma de la ")
    rate = _rates_by_name().get(key.strip())
    if rate is None:
        raise InvalidDepartment(f"'{name}' no es un departamento de Nicaragua. Opciones: {', '.join(departments())}.")
    return rate


def quote_shipping(department_name: str, subtotal_nio: Decimal) -> ShippingQuote:
    rate = find_rate(department_name)
    cost = Decimal("0.00") if subtotal_nio >= FREE_SHIPPING_FROM_NIO else rate.cost_nio
    return ShippingQuote(rate.department, cost, rate.estimated_days)
