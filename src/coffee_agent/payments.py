from decimal import Decimal

import stripe

from coffee_agent.order import Order, OrderError


class PaymentError(RuntimeError):
    pass


def _cents(amount: Decimal) -> int:
    return int((amount * 100).to_integral_value())


def create_payment_link(client: stripe.StripeClient, order: Order, success_url: str) -> None:
    """Create a Stripe Checkout session for the order and store its URL on the order.

    Checkout Sessions accept inline prices, so the catalog doesn't need to be mirrored in Stripe.
    """
    if not order.lines:
        raise OrderError("El pedido está vacío.")
    if order.shipping is None:
        raise OrderError("Falta cotizar el envío antes de generar el link de pago.")
    if not order.customer_email:
        raise OrderError("Falta el email del cliente.")

    line_items = [
        {
            "quantity": line.quantity,
            "price_data": {
                "currency": "mxn",
                "unit_amount": _cents(line.product.price_mxn),
                "product_data": {"name": line.product.name, "metadata": {"sku": line.product.sku}},
            },
        }
        for line in order.lines.values()
    ]
    shipping = order.shipping
    try:
        session = client.v1.checkout.sessions.create(
            params={
                "mode": "payment",
                "line_items": line_items,
                "customer_email": order.customer_email,
                "success_url": success_url,
                "shipping_options": [
                    {
                        "shipping_rate_data": {
                            "type": "fixed_amount",
                            "display_name": f"Envío {shipping.zone} ({shipping.estimated_days})",
                            "fixed_amount": {"amount": _cents(shipping.cost_mxn), "currency": "mxn"},
                        }
                    }
                ],
                "metadata": {
                    "codigo_postal": shipping.postal_code,
                    "cliente": order.customer_name or "",
                },
            }
        )
    except stripe.StripeError as e:
        raise PaymentError(f"Stripe rechazó la solicitud: {e.user_message or e}") from e

    order.payment_url = session.url
    order.checkout_session_id = session.id
