from dataclasses import dataclass, field
from decimal import Decimal

from coffee_agent.catalog import Catalog, Product
from coffee_agent.shipping import ShippingQuote


class OrderError(ValueError):
    """A request the customer can fix, e.g. unknown product or not enough stock."""


@dataclass
class OrderLine:
    product: Product
    quantity: int

    @property
    def total_mxn(self) -> Decimal:
        return self.product.price_mxn * self.quantity


@dataclass
class Order:
    catalog: Catalog
    lines: dict[str, OrderLine] = field(default_factory=dict)
    shipping: ShippingQuote | None = None
    customer_name: str | None = None
    customer_email: str | None = None
    payment_url: str | None = None
    checkout_session_id: str | None = None

    @property
    def subtotal_mxn(self) -> Decimal:
        return sum((line.total_mxn for line in self.lines.values()), Decimal("0.00"))

    @property
    def total_mxn(self) -> Decimal:
        shipping = self.shipping.cost_mxn if self.shipping else Decimal("0.00")
        return self.subtotal_mxn + shipping

    @property
    def status(self) -> str:
        if self.payment_url:
            return "pendiente_de_pago"
        return "abierto" if self.lines else "vacio"

    def add(self, sku: str, quantity: int) -> OrderLine:
        self._ensure_editable()
        product = self._product(sku)
        if quantity < 1:
            raise OrderError("La cantidad debe ser al menos 1.")
        current = self.lines[product.sku].quantity if product.sku in self.lines else 0
        if current + quantity > product.stock:
            raise OrderError(f"Solo hay {product.stock} unidades de {product.name} (ya tienes {current} en el pedido).")
        line = OrderLine(product, current + quantity)
        self.lines[product.sku] = line
        self._invalidate_shipping()
        return line

    def remove(self, sku: str, quantity: int | None = None) -> None:
        """Remove `quantity` units of a product, or the whole line when quantity is None."""
        self._ensure_editable()
        product = self._product(sku)
        line = self.lines.get(product.sku)
        if line is None:
            raise OrderError(f"{product.name} no está en el pedido.")
        if quantity is None or quantity >= line.quantity:
            del self.lines[product.sku]
        elif quantity < 1:
            raise OrderError("La cantidad debe ser al menos 1.")
        else:
            line.quantity -= quantity
        self._invalidate_shipping()

    def set_shipping(self, quote: ShippingQuote) -> None:
        self._ensure_editable()
        self.shipping = quote

    def _product(self, sku: str) -> Product:
        product = self.catalog.get(sku)
        if product is None:
            raise OrderError(f"No existe un producto con SKU '{sku}'.")
        return product

    def _ensure_editable(self) -> None:
        if self.payment_url:
            raise OrderError("El pedido ya tiene un link de pago y no se puede modificar.")

    def _invalidate_shipping(self) -> None:
        # Free-shipping eligibility depends on the subtotal, so a changed cart needs a new quote.
        self.shipping = None

    def to_dict(self) -> dict:
        return {
            "estado": self.status,
            "cliente": {"nombre": self.customer_name, "email": self.customer_email},
            "productos": [
                {
                    "sku": line.product.sku,
                    "producto": line.product.name,
                    "cantidad": line.quantity,
                    "precio_unitario_mxn": float(line.product.price_mxn),
                    "total_mxn": float(line.total_mxn),
                }
                for line in self.lines.values()
            ],
            "subtotal_mxn": float(self.subtotal_mxn),
            "envio": self.shipping.to_dict() if self.shipping else None,
            "total_mxn": float(self.total_mxn),
            "pago": {
                "link": self.payment_url,
                "stripe_checkout_session_id": self.checkout_session_id,
            },
        }
