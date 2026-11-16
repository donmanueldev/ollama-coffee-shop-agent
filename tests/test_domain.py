from decimal import Decimal
from pathlib import Path

import pytest

from coffee_agent.catalog import Catalog
from coffee_agent.order import Order, OrderError
from coffee_agent.shipping import InvalidPostalCode, quote_shipping

CATALOG_PATH = Path(__file__).resolve().parents[1] / "data" / "catalogo.csv"


@pytest.fixture
def catalog() -> Catalog:
    return Catalog.from_csv(CATALOG_PATH)


def test_search_ignores_accents_and_case(catalog):
    skus = {p.sku for p in catalog.search("cafe MOLIDO")}
    assert skus == {"CAF-002"}


def test_empty_search_returns_whole_catalog(catalog):
    assert len(catalog.search("")) == 10


def test_add_accumulates_quantity_and_subtotal(catalog):
    order = Order(catalog)
    order.add("caf-001", 1)
    order.add("CAF-001", 2)
    assert order.lines["CAF-001"].quantity == 3
    assert order.subtotal_mxn == Decimal("441.00")


def test_add_rejects_more_than_stock(catalog):
    order = Order(catalog)
    order.add("ACC-002", 4)
    with pytest.raises(OrderError, match="Solo hay 5"):
        order.add("ACC-002", 2)


def test_add_rejects_unknown_sku(catalog):
    with pytest.raises(OrderError, match="No existe"):
        Order(catalog).add("XXX-999", 1)


def test_remove_partial_and_whole_line(catalog):
    order = Order(catalog)
    order.add("CAF-004", 3)
    order.remove("CAF-004", 1)
    assert order.lines["CAF-004"].quantity == 2
    order.remove("CAF-004")
    assert order.lines == {}


def test_changing_cart_drops_stale_shipping_quote(catalog):
    order = Order(catalog)
    order.add("CAF-001", 1)
    order.set_shipping(quote_shipping("03100", order.subtotal_mxn))
    order.add("ACC-002", 1)
    assert order.shipping is None


def test_order_is_frozen_once_payment_link_exists(catalog):
    order = Order(catalog)
    order.add("CAF-001", 1)
    order.payment_url = "https://checkout.stripe.com/x"
    with pytest.raises(OrderError, match="no se puede modificar"):
        order.add("CAF-001", 1)


@pytest.mark.parametrize(
    ("postal_code", "subtotal", "zone", "cost"),
    [
        ("03100", "147.00", "local (CDMX)", "89.00"),
        ("16999", "147.00", "local (CDMX)", "89.00"),
        ("44100", "147.00", "nacional", "149.00"),
        ("44100", "799.99", "nacional", "149.00"),
        ("44100", "800.00", "nacional", "0.00"),
    ],
)
def test_shipping_quote(postal_code, subtotal, zone, cost):
    quote = quote_shipping(postal_code, Decimal(subtotal))
    assert (quote.zone, quote.cost_mxn) == (zone, Decimal(cost))


@pytest.mark.parametrize("postal_code", ["1234", "123456", "abcde", "00123"])
def test_shipping_rejects_invalid_postal_codes(postal_code):
    with pytest.raises(InvalidPostalCode):
        quote_shipping(postal_code, Decimal("100"))


def test_order_json_shape(catalog):
    order = Order(catalog)
    order.add("CAF-003", 2)
    order.set_shipping(quote_shipping("64000", order.subtotal_mxn))
    data = order.to_dict()
    assert data["estado"] == "abierto"
    assert data["productos"][0] == {
        "sku": "CAF-003",
        "producto": "Café micro-lote Veracruz 250g",
        "cantidad": 2,
        "precio_unitario_mxn": 238.0,
        "total_mxn": 476.0,
    }
    assert data["total_mxn"] == 625.0
