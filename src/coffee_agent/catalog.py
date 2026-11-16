import csv
import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path


@dataclass(frozen=True)
class Product:
    sku: str
    name: str
    description: str
    price_mxn: Decimal
    stock: int

    def to_dict(self) -> dict:
        return {
            "sku": self.sku,
            "producto": self.name,
            "descripcion": self.description,
            "precio_mxn": float(self.price_mxn),
            "stock": self.stock,
        }


def _normalize(text: str) -> str:
    # Customers type "cafe" or "molino" without accents; match them anyway.
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


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
                    price_mxn=Decimal(row["precio_mxn"]),
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
        words = _normalize(query).split()
        if not words:
            return self.all()
        return [
            p for p in self._by_sku.values() if all(w in _normalize(f"{p.sku} {p.name} {p.description}") for w in words)
        ]
