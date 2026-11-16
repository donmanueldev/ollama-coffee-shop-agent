"""Run scripted customer conversations against the local Ollama model and grade the resulting order.

Unit tests prove the code; these evals measure how reliably the model drives it. Ollama must be
running with the model pulled.

    uv run python evals/run_evals.py                 # every scenario once
    uv run python evals/run_evals.py --runs 3 happy  # scenarios whose name contains "happy"
"""

import argparse
import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal

import ollama

from coffee_agent import CATALOG_PATH, DEFAULT_MODEL
from coffee_agent.agent import CoffeeShopAgent, OrderTools
from coffee_agent.catalog import Catalog
from coffee_agent.order import Order
from coffee_agent.payments import create_pocket_charge

# A check returns a failure reason, or None when the conversation met expectations.
Check = Callable[[Order, list[str]], str | None]


@dataclass
class Scenario:
    name: str
    turns: list[str]
    checks: list[Check]
    # Answers the customer gives when the shop asks them to confirm the summary before charging.
    confirmations: list[bool] = field(default_factory=lambda: [True])


def lines_are(expected: dict[str, int]) -> Check:
    def check(order: Order, _answers: list[str]) -> str | None:
        actual = {sku: line.quantity for sku, line in order.lines.items()}
        return None if actual == expected else f"productos {actual} != {expected}"

    return check


def shipping_is(department: str | None, cost: str | None = None) -> Check:
    def check(order: Order, _answers: list[str]) -> str | None:
        if department is None:
            return None if order.shipping is None else f"no debía cotizar envío ({order.shipping.department})"
        if order.shipping is None:
            return "no cotizó el envío"
        if order.shipping.department != department:
            return f"envío a {order.shipping.department} != {department}"
        if cost is not None and order.shipping.cost_nio != Decimal(cost):
            return f"costo de envío {order.shipping.cost_nio} != {cost}"
        return None

    return check


def paid(expected: bool) -> Check:
    def check(order: Order, _answers: list[str]) -> str | None:
        if expected and not order.payment_url:
            return "no generó el link de pago"
        if not expected and order.payment_url:
            return "generó un link de pago que no debía"
        return None

    return check


def last_answer_has_link(order: Order, answers: list[str]) -> str | None:
    if order.payment_url and order.payment_url not in answers[-1]:
        return "la última respuesta no incluye el link real"
    return None


_AMOUNT_WITHOUT_CORDOBAS = re.compile(r"(?<!C)\$")


def no_leaked_reasoning(_order: Order, answers: list[str]) -> str | None:
    if any("<think>" in answer or "</think>" in answer for answer in answers):
        return "la respuesta incluye el razonamiento interno del modelo"
    return None


def amounts_in_cordobas(_order: Order, answers: list[str]) -> str | None:
    if any(_AMOUNT_WITHOUT_CORDOBAS.search(answer) for answer in answers):
        return "escribió un monto con '$' en vez de 'C$'"
    return None


SCENARIOS = [
    Scenario(
        "happy_path_esteli",
        [
            "Hola, ¿qué cafés molidos tienen?",
            "Quiero 2 del Jinotega molido y una prensa francesa",
            "Es para Estelí",
            "Sí, confirmo. Soy Ana López, mi Pocket es 8888 1234",
        ],
        [lines_are({"CAF-002": 2, "ACC-001": 1}), shipping_is("Estelí", "150"), paid(True), last_answer_has_link],
    ),
    Scenario(
        "free_shipping_managua",
        [
            "Quiero 4 molinos manuales",
            "Envíamelo a Managua",
            "Todo bien. Carlos Pérez, 7777 4321",
        ],
        [lines_are({"ACC-002": 4}), shipping_is("Managua", "0"), paid(True)],
    ),
    Scenario(
        "stock_limit",
        ["Quiero 10 molinos manuales"],
        [lambda o, _a: None if o.lines.get("ACC-002") is None or o.lines["ACC-002"].quantity <= 5 else "excedió stock"],
    ),
    Scenario(
        "product_not_in_catalog",
        ["¿Tienen té matcha? Agrégame uno"],
        [lines_are({})],
    ),
    Scenario(
        "invalid_department",
        ["Quiero un kit de degustación", "Envíalo a San José, Costa Rica"],
        [lines_are({"CAF-005": 1}), shipping_is(None), paid(False)],
    ),
    Scenario(
        "change_after_quote",
        [
            "Quiero una taza de barro",
            "Envío a León",
            "Mejor agrégame también 4 molinos manuales",
            "Confirmo, María Ruiz, 5555 0000",
        ],
        [lines_are({"ACC-004": 1, "ACC-002": 4}), shipping_is("León", "0"), paid(True)],
    ),
    Scenario(
        "remove_item",
        [
            "Agrégame 2 cajas de café filtrado y un V60 de filtros",
            "Quita los filtros, solo las cajas",
        ],
        [lines_are({"CAF-004": 2})],
    ),
    Scenario(
        "invalid_phone",
        ["Quiero 1 café Jinotega en grano", "Para Granada", "Confirmo. Luis, mi número es 1234"],
        [lines_are({"CAF-001": 1}), paid(False)],
    ),
    Scenario(
        "no_link_without_confirmation",
        ["Quiero 1 café Jinotega en grano para Managua. Soy Ana, Pocket 8888 1234"],
        [paid(False)],
        confirmations=[False],
    ),
    Scenario(
        "customer_declines_summary",
        ["Quiero 1 café Jinotega en grano", "Para Masaya", "Ana, 8888 1234, genera el link"],
        [paid(False)],
        confirmations=[False],
    ),
    Scenario(
        "long_conversation",
        [
            "Hola, ¿qué venden?",
            "¿Qué diferencia hay entre el Jinotega y el de Nueva Segovia?",
            "¿El de Nueva Segovia es en grano o molido?",
            "¿Qué trae el kit de degustación?",
            "¿La prensa francesa es de vidrio?",
            "¿El molino es eléctrico?",
            "¿De dónde es la taza de barro?",
            "¿Cómo funciona la suscripción?",
            "¿Qué filtros tienen?",
            "¿Cuál me recomiendas para empezar?",
            "¿Tienen sobres individuales?",
            "Ok, agrégame una taza de barro y un kit de degustación",
            "Envío a Rivas",
            "Confirmo, Pedro Gómez, 8123 4567",
        ],
        [
            lines_are({"ACC-004": 1, "CAF-005": 1}),
            shipping_is("Rivas", "150"),
            paid(True),
        ],
    ),
]


class MeteredClient:
    """Wraps ollama.Client to record tokens and latency per call, to watch context size and speed."""

    def __init__(self, client: ollama.Client):
        self._client = client
        self.calls = 0
        self.seconds = 0.0
        self.max_prompt_tokens = self.output_tokens = 0

    def chat(self, **request) -> ollama.ChatResponse:
        started = time.monotonic()
        response = self._client.chat(**request)
        self.seconds += time.monotonic() - started
        self.calls += 1
        self.max_prompt_tokens = max(self.max_prompt_tokens, response.prompt_eval_count or 0)
        self.output_tokens += response.eval_count or 0
        return response


@dataclass
class Result:
    scenario: str
    failures: list[str]
    meter: MeteredClient


def run_scenario(scenario: Scenario, client: ollama.Client, model: str) -> Result:
    order = Order(Catalog.from_csv(CATALOG_PATH))
    metered = MeteredClient(client)
    confirmations = iter(scenario.confirmations)
    tools = OrderTools(order, create_pocket_charge, lambda _order: next(confirmations, True))
    agent = CoffeeShopAgent(metered, model, tools)  # type: ignore[arg-type]
    answers = [agent.reply(turn) for turn in scenario.turns]
    checks = [*scenario.checks, amounts_in_cordobas, no_leaked_reasoning]
    failures = [reason for check in checks if (reason := check(order, answers))]
    return Result(scenario.name, failures, metered)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("filter", nargs="?", default="", help="run only scenarios whose name contains this")
    parser.add_argument("--runs", type=int, default=1)
    args = parser.parse_args()

    model = os.environ.get("OLLAMA_MODEL", DEFAULT_MODEL)
    client = ollama.Client()
    scenarios = [s for s in SCENARIOS if args.filter in s.name]
    print(f"Modelo {model} · {len(scenarios)} escenarios × {args.runs} corridas\n")

    passed = total = 0
    seconds = 0.0
    for scenario in scenarios:
        for _ in range(args.runs):
            result = run_scenario(scenario, client, model)
            total += 1
            passed += not result.failures
            meter = result.meter
            seconds += meter.seconds
            status = "PASS" if not result.failures else "FAIL"
            print(
                f"{status} {result.scenario:<30} {meter.seconds:6.1f}s  {meter.calls:2d} llamadas"
                f"  máx {meter.max_prompt_tokens:5d} tokens de prompt · {meter.output_tokens:5d} de salida"
            )
            for reason in result.failures:
                print(f"     - {reason}")
    print(f"\n{passed}/{total} pasaron ({passed / total:.0%}) en {seconds / 60:.1f} min")


if __name__ == "__main__":
    main()
