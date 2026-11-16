import json
import os
import sys
from functools import partial
from pathlib import Path

import anthropic

from coffee_agent.agent import CoffeeShopAgent, OrderTools
from coffee_agent.catalog import Catalog
from coffee_agent.order import Order
from coffee_agent.payments import create_pocket_charge
from coffee_agent.text import cordobas

EXIT_COMMANDS = {"salir", "exit", "quit", "adios", "adiós"}
DEFAULT_CATALOG = Path(__file__).resolve().parents[2] / "data" / "catalogo.csv"
# Cheapest Claude tier; enough for a short sales chat with a handful of tools (see evals/).
DEFAULT_MODEL = "claude-haiku-5-5"
YES_ANSWERS = {"s", "si", "sí", "y", "yes"}

say = partial(print, file=sys.stderr, flush=True)


def ask_customer_to_confirm(order: Order) -> bool:
    """Show the summary computed by the app (not by the model) and ask the customer directly."""
    say("\n──── Confirma tu pedido ────")
    for line in order.lines.values():
        say(f"  {line.quantity} × {line.product.name:<34} {cordobas(line.total_nio):>12}")
    shipping = order.shipping
    if shipping:
        label = f"Envío a {shipping.department} ({shipping.estimated_days})"
        say(f"  {label:<38} {cordobas(shipping.cost_nio):>12}")
    say(f"  {'Total':<38} {cordobas(order.total_nio):>12}")
    say(f"  Cobro Pocket a {order.customer_name} · {order.customer_phone}")
    say("¿Confirmas el pedido? (s/n): ", end="")
    try:
        return input().strip().casefold() in YES_ANSWERS
    except EOFError:
        return False


def main() -> None:
    model = os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL)
    catalog = Catalog.from_csv(Path(os.environ.get("CATALOG_PATH", DEFAULT_CATALOG)))
    # Resolves ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN, or an `ant auth login` profile.
    client = anthropic.Anthropic()
    if client.api_key is None and client.auth_token is None and client.credentials is None:
        say("Falta la clave de Anthropic. Ponla en .env (ANTHROPIC_API_KEY=...) y corre:")
        say("  uv run --env-file .env coffee-agent")
        sys.exit(1)
    order = Order(catalog)
    agent = CoffeeShopAgent(
        client=client,
        model=model,
        tools=OrderTools(order, create_pocket_charge, ask_customer_to_confirm),
    )

    # The chat goes to stderr so stdout carries only the final order JSON (pipe-friendly).
    say(f"☕ Cafetería online — modelo {model}. Escribe 'salir' para terminar.\n")
    say("Barista: ¡Hola! ¿Qué café se te antoja hoy?")
    try:
        while True:
            say("Tú: ", end="")
            try:
                text = input().strip()
            except EOFError:
                break
            if not text:
                continue
            if text.casefold() in EXIT_COMMANDS:
                break
            try:
                answer = agent.reply(text)
            except anthropic.AuthenticationError:
                say("[La API de Anthropic rechazó la clave. Revisa ANTHROPIC_API_KEY.]")
                break
            except anthropic.RateLimitError:
                say("[Límite de uso de la API alcanzado. Espera un momento y repite tu mensaje.]")
                continue
            except anthropic.APIStatusError as e:
                say(f"[La API de Anthropic respondió con un error ({e.status_code}). Repite tu mensaje.]")
                continue
            except anthropic.APIConnectionError:
                say("[No hay conexión con la API de Anthropic. Revisa tu internet y repite tu mensaje.]")
                continue
            say(f"Barista: {answer}\n")
    except KeyboardInterrupt:
        say()
    finally:
        print(json.dumps(order.to_dict(), ensure_ascii=False, indent=2))
