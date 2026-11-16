import unicodedata
from decimal import Decimal


def normalize(text: str) -> str:
    """Lowercase and strip accents, so "cafe" matches "Café" and "esteli" matches "Estelí"."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def cordobas(amount: Decimal) -> str:
    return f"C$ {amount:,.2f}"
