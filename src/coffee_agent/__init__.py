import json
import os
import sys
from pathlib import Path

import httpx
import ollama

from coffee_agent.agent import CoffeeShopAgent, OrderTools
from coffee_agent.catalog import Catalog
from coffee_agent.order import Order
from coffee_agent.payments import create_pocket_charge
from coffee_agent.text import cordobas

EXIT_COMMANDS = {"salir", "exit", "quit", "adios", "adiós"}
CATALOG_PATH = Path(__file__).resolve().parents[2] / "data" / "catalogo.csv"
# Answers without a reasoning step: 85% of the evals in ~15 s per conversation. The reasoning
# variant (qwen3:4b) passed them all but took minutes per conversation. Override with OLLAMA_MODEL.
DEFAULT_MODEL = "qwen3:4b-instruct"
YES_ANSWERS = {"s", "si", "sí", "y", "yes"}


def say(*values: object, end: str = "\n") -> None:
    """Write chat output to stderr, keeping stdout for the final order JSON."""
    print(*values, end=end, file=sys.stderr, flush=True)


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


class StreamedReply:
    """Prints the Barista's reply as it streams, opening the "Barista:" line only once text arrives.

    Tools can print in the middle of a turn (the confirmation box), so the prefix waits for real text.
    """

    def __init__(self) -> None:
        self.started = False

    def __call__(self, piece: str) -> None:
        if not self.started:
            say("Barista: ", end="")
            self.started = True
        say(piece, end="")

    def end(self, answer: str = "") -> None:
        if not self.started and answer:
            # Replies that didn't come from the model, e.g. the fallback after too many tool calls.
            say(f"Barista: {answer}", end="")
            self.started = True
        if self.started:
            say("\n")


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
            reply = StreamedReply()
            try:
                answer = agent.reply(text, on_text=reply)
            # Streaming surfaces a stopped server as httpx.ConnectError rather than ConnectionError.
            except (ConnectionError, httpx.ConnectError):
                reply.end()
                say("[No encuentro Ollama. Ábrelo (o corre `ollama serve`) y repite tu mensaje.]")
                continue
            except ollama.ResponseError as e:
                reply.end()
                if e.status_code == 404:
                    say(f"[El modelo {model} no está descargado. Corre `ollama pull {model}`.]")
                    break
                say(f"[Ollama respondió con un error: {e.error}. Repite tu mensaje.]")
                continue
            reply.end(answer)
    except KeyboardInterrupt:
        say()
    finally:
        print(json.dumps(order.to_dict(), ensure_ascii=False, indent=2))
