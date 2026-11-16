import csv
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from coffee_agent.text import normalize


@dataclass(frozen=True)
class Product:
    sku: str
    name: str
    description: str
    price_nio: Decimal
    stock: int

    def to_dict(self) -> dict:
        return {
            "sku": self.sku,
            "producto": self.name,
            "descripcion": self.description,
            "precio_nio": float(self.price_nio),
            "stock": self.stock,
        }


class Catalog:
    def __init__(self, products: list[Product]):
        self._by_sku = {p.sku: p for p in products}

    @classmethod
    def from_csv(cls, path: Path) -> "Catalog":
        with path.open(newline="", encoding="utf-8") as f:
            products = [
                Product(
                    sku=row["sku"].strip(),
                    name=row["producto"].strip(),
                    description=row["descripcion"].strip(),
                    price_nio=Decimal(row["precio_nio"]),
                    stock=int(row["stock"]),
                )
                for row in csv.DictReader(f)
            ]
        return cls(products)

    def all(self) -> list[Product]:
        return list(self._by_sku.values())

    def get(self, sku: str) -> Product | None:
        return self._by_sku.get(sku.strip().upper())

    def search(self, query: str) -> list[Product]:
        """Products whose sku, name, or description contain every word of the query."""
        words = normalize(query).split()
        if not words:
            return self.all()
        return [
            p for p in self._by_sku.values() if all(w in normalize(f"{p.sku} {p.name} {p.description}") for w in words)
        ]
