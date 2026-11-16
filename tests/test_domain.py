from decimal import Decimal

import pytest

from coffee_agent import CATALOG_PATH
from coffee_agent.catalog import Catalog
from coffee_agent.order import Order, OrderError
from coffee_agent.shipping import InvalidDepartment, departments, quote_shipping
from coffee_agent.text import cordobas


@pytest.fixture
def catalog() -> Catalog:
    return Catalog.from_csv(CATALOG_PATH)


def test_search_ignores_accents_and_case(catalog):
    skus = {p.sku for p in catalog.search("jinotega MOLIDO")}
    assert skus == {"CAF-002"}


def test_empty_search_returns_whole_catalog(catalog):
    assert len(catalog.search("")) == 10


def test_add_accumulates_quantity_and_subtotal(catalog):
    order = Order(catalog)
    order.add("caf-001", 1)
    order.add("CAF-001", 2)
    assert order.lines["CAF-001"].quantity == 3
    assert order.subtotal_nio == Decimal("441.00")


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
    order.set_shipping(quote_shipping("Managua", order.subtotal_nio))
    order.add("ACC-002", 1)
    assert order.shipping is None


def test_order_is_frozen_once_payment_link_exists(catalog):
    order = Order(catalog)
    order.add("CAF-001", 1)
    order.payment_url = "https://pocket.example/cobro/PKT-1"
    with pytest.raises(OrderError, match="no se puede modificar"):
        order.add("CAF-001", 1)


@pytest.mark.parametrize(
    ("department", "subtotal", "cost", "days"),
    [
        ("Managua", "147.00", "80.00", "1-2 días hábiles"),
        ("managua", "147.00", "80.00", "1-2 días hábiles"),
        ("Esteli", "147.00", "150.00", "2-4 días hábiles"),
        ("Departamento de León", "1599.99", "150.00", "2-4 días hábiles"),
        ("RACCN", "1600.00", "0.00", "2-4 días hábiles"),
        ("Managua", "1600.00", "0.00", "1-2 días hábiles"),
    ],
)
def test_shipping_quote(department, subtotal, cost, days):
    quote = quote_shipping(department, Decimal(subtotal))
    assert (quote.cost_nio, quote.estimated_days) == (Decimal(cost), days)


def test_rates_cover_all_17_departments():
    assert len(departments()) == 17
    assert "Río San Juan" in departments()


def test_shipping_resolves_department_display_name():
    assert quote_shipping("rio san juan", Decimal("100")).department == "Río San Juan"
    assert quote_shipping("Caribe Sur", Decimal("100")).department == "Costa Caribe Sur"


@pytest.mark.parametrize("department", ["", "Ometepe", "12345"])
def test_shipping_rejects_unknown_departments(department):
    with pytest.raises(InvalidDepartment, match="Opciones"):
        quote_shipping(department, Decimal("100"))


def test_order_json_shape(catalog):
    order = Order(catalog)
    order.add("CAF-003", 2)
    order.set_shipping(quote_shipping("Granada", order.subtotal_nio))
    data = order.to_dict()
    assert data["estado"] == "abierto"
    assert data["moneda"] == "NIO"
    assert data["productos"][0] == {
        "sku": "CAF-003",
        "producto": "Café micro-lote Nueva Segovia 250g",
        "cantidad": 2,
        "precio_unitario_nio": 238.0,
        "total_nio": 476.0,
    }
    assert data["total_nio"] == 626.0


def test_cordobas_format():
    assert cordobas(Decimal("1600")) == "C$ 1,600.00"
