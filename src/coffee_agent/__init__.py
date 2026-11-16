import json
import os
import sys
from functools import partial
from pathlib import Path

import ollama

from coffee_agent.agent import CoffeeShopAgent, OrderTools
from coffee_agent.catalog import Catalog
from coffee_agent.order import Order
from coffee_agent.payments import create_pocket_charge
from coffee_agent.text import cordobas

EXIT_COMMANDS = {"salir", "exit", "quit", "adios", "adiós"}
CATALOG_PATH = Path(__file__).resolve().parents[2] / "data" / "catalogo.csv"
# Light enough for a laptop and passes the evals (see evals/); override with OLLAMA_MODEL.
DEFAULT_MODEL = "qwen3:4b"
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
    model = os.environ.get("OLLAMA_MODEL", DEFAULT_MODEL)
    order = Order(Catalog.from_csv(CATALOG_PATH))
    agent = CoffeeShopAgent(
        # Talks to the local Ollama server (http://localhost:11434, or OLLAMA_HOST if set).
        client=ollama.Client(),
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
            except ConnectionError:
                say("[No encuentro Ollama. Ábrelo (o corre `ollama serve`) y repite tu mensaje.]")
                continue
            except ollama.ResponseError as e:
                if e.status_code == 404:
                    say(f"[El modelo {model} no está descargado. Corre `ollama pull {model}`.]")
                    break
                say(f"[Ollama respondió con un error: {e.error}. Repite tu mensaje.]")
                continue
            say(f"Barista: {answer}\n")
    except KeyboardInterrupt:
        say()
    finally:
        print(json.dumps(order.to_dict(), ensure_ascii=False, indent=2))
