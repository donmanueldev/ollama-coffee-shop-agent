import json
import os
import sys
from functools import partial
from pathlib import Path

import ollama
import stripe

from coffee_agent.agent import CoffeeShopAgent, OrderTools
from coffee_agent.catalog import Catalog
from coffee_agent.order import Order, OrderError
from coffee_agent.payments import create_payment_link

EXIT_COMMANDS = {"salir", "exit", "quit", "adios", "adiós"}
DEFAULT_CATALOG = Path(__file__).resolve().parents[2] / "data" / "catalogo.csv"


def _payment_link_factory():
    api_key = os.environ.get("STRIPE_SECRET_KEY")
    success_url = os.environ.get("STRIPE_SUCCESS_URL", "https://example.com/gracias")
    if not api_key:

        def missing_key(_order: Order) -> None:
            raise OrderError("Los pagos no están configurados (falta STRIPE_SECRET_KEY). Avisa al cliente.")

        return missing_key
    return partial(create_payment_link, stripe.StripeClient(api_key), success_url=success_url)


def main() -> None:
    model = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b")
    catalog = Catalog.from_csv(Path(os.environ.get("CATALOG_PATH", DEFAULT_CATALOG)))
    order = Order(catalog)
    agent = CoffeeShopAgent(
        client=ollama.Client(host=os.environ.get("OLLAMA_HOST")),
        model=model,
        tools=OrderTools(order, _payment_link_factory()),
    )

    # The chat goes to stderr so stdout carries only the final order JSON (pipe-friendly).
    say = partial(print, file=sys.stderr, flush=True)
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
            except (ollama.ResponseError, ConnectionError) as e:
                say(f"[No pude hablar con Ollama: {e}. ¿Está corriendo `ollama serve` y descargado {model}?]")
                continue
            say(f"Barista: {answer}\n")
    except KeyboardInterrupt:
        say()
    finally:
        print(json.dumps(order.to_dict(), ensure_ascii=False, indent=2))
