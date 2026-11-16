import secrets
from collections.abc import Callable

from coffee_agent.order import Order

# Simulated Pocket charge: nothing leaves the machine. The reserved .example domain makes it
# obvious the link is not a real payment page.
SIMULATED_POCKET_URL = "https://pocket.example/cobro/{reference}"


def _new_reference() -> str:
    return f"PKT-{secrets.token_hex(4).upper()}"


def create_pocket_charge(order: Order, new_reference: Callable[[], str] = _new_reference) -> None:
    """Simulate a Pocket payment request for the order and store its reference and link."""
    order.ensure_ready_for_payment()

    reference = new_reference()
    order.payment_reference = reference
    order.payment_url = SIMULATED_POCKET_URL.format(reference=reference)
