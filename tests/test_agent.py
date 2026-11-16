import json
from types import SimpleNamespace

import pytest

from coffee_agent import CATALOG_PATH
from coffee_agent.agent import CoffeeShopAgent, OrderTools
from coffee_agent.catalog import Catalog
from coffee_agent.order import Order
from coffee_agent.payments import create_pocket_charge

POCKET_URL = "https://pocket.example/cobro/PKT-TEST01"


@pytest.fixture
def order() -> Order:
    return Order(Catalog.from_csv(CATALOG_PATH))


def make_tools(order: Order, confirms: bool = True) -> OrderTools:
    return OrderTools(order, lambda o: create_pocket_charge(o, new_reference=lambda: "PKT-TEST01"), lambda _o: confirms)


def run(tools: OrderTools, name: str, **args) -> dict:
    return tools.run(name, args)


def ready_to_pay(order: Order, confirms: bool = True) -> OrderTools:
    tools = make_tools(order, confirms)
    run(tools, "agregar_producto", sku="CAF-001", cantidad=1)
    run(tools, "cotizar_envio", departamento="Managua")
    return tools


def test_full_sale_creates_simulated_pocket_charge(order):
    tools = make_tools(order)

    run(tools, "agregar_producto", sku="CAF-001", cantidad="2")  # models often send strings
    run(tools, "cotizar_envio", departamento="León")
    result = run(tools, "generar_link_de_pago", nombre="Ana", telefono="+505 8888-1234")

    assert result == {"link_de_pago": POCKET_URL, "referencia": "PKT-TEST01", "total_nio": 444.0}
    data = order.to_dict()
    assert data["estado"] == "pendiente_de_pago"
    assert data["cliente"] == {"nombre": "Ana", "telefono": "+50588881234"}
    assert data["pago"] == {"metodo": "Pocket (simulado)", "referencia": "PKT-TEST01", "link": POCKET_URL}


def test_default_reference_is_unique_pocket_style(order):
    tools = OrderTools(order, create_pocket_charge, lambda _o: True)
    run(tools, "agregar_producto", sku="CAF-001", cantidad=1)
    run(tools, "cotizar_envio", departamento="Managua")

    reference = run(tools, "generar_link_de_pago", nombre="Ana", telefono="88881234")["referencia"]

    assert reference.startswith("PKT-") and len(reference) == 12
    assert order.payment_url.endswith(reference)


def test_payment_link_requires_shipping_quote(order):
    tools = make_tools(order)
    run(tools, "agregar_producto", sku="CAF-001", cantidad=1)

    result = run(tools, "generar_link_de_pago", nombre="Ana", telefono="88881234")

    assert "cotizar el envío" in result["error"]
    assert order.payment_url is None


@pytest.mark.parametrize("phone", ["1234", "22223333", "888812345", "ana@example.com"])
def test_invalid_phone_is_reported_to_model(order, phone):
    tools = ready_to_pay(order)

    assert "móvil de Nicaragua" in run(tools, "generar_link_de_pago", nombre="Ana", telefono=phone)["error"]
    assert order.payment_url is None


def test_unknown_department_is_reported_to_model(order):
    tools = make_tools(order)
    run(tools, "agregar_producto", sku="CAF-001", cantidad=1)

    assert "no es un departamento" in run(tools, "cotizar_envio", departamento="Ometepe")["error"]


def test_bad_arguments_and_unknown_tools_do_not_crash(order):
    tools = make_tools(order)
    assert "Argumentos inválidos" in run(tools, "agregar_producto", sku="CAF-001", cantidad="dos")["error"]
    assert "desconocida" in run(tools, "hackear")["error"]


def _text(content: str):
    return SimpleNamespace(message=SimpleNamespace(role="assistant", content=content, tool_calls=None))


def _tool_calls(*calls: tuple[str, dict]):
    tool_calls = [SimpleNamespace(function=SimpleNamespace(name=name, arguments=args)) for name, args in calls]
    return SimpleNamespace(message=SimpleNamespace(role="assistant", content="", tool_calls=tool_calls))


class ScriptedClient:
    """Stands in for ollama.Client: replays canned responses and records each request."""

    def __init__(self, responses):
        self._responses = iter(responses)
        self.requests: list[dict] = []

    def chat(self, **request):
        self.requests.append({**request, "messages": list(request["messages"])})
        return next(self._responses)


def make_agent(order: Order, responses, confirms: bool = True) -> tuple[CoffeeShopAgent, ScriptedClient]:
    client = ScriptedClient(responses)
    return CoffeeShopAgent(client, "test-model", make_tools(order, confirms)), client  # type: ignore[arg-type]


def test_agent_executes_tool_calls_then_answers(order):
    agent, client = make_agent(
        order,
        [_tool_calls(("agregar_producto", {"sku": "ACC-001", "cantidad": 1})), _text("Listo, agregué la prensa.")],
    )

    assert agent.reply("quiero una prensa") == "Listo, agregué la prensa."
    assert order.lines["ACC-001"].quantity == 1
    tool_message = client.requests[1]["messages"][-1]
    assert tool_message["role"] == "tool"
    assert tool_message["tool_name"] == "agregar_producto"


def test_several_tool_calls_in_one_reply_all_run(order):
    agent, client = make_agent(
        order,
        [
            _tool_calls(
                ("agregar_producto", {"sku": "CAF-002", "cantidad": 2}),
                ("agregar_producto", {"sku": "ACC-001", "cantidad": 1}),
            ),
            _text("Agregados."),
        ],
    )

    agent.reply("2 molidos y una prensa")

    assert [m["role"] for m in client.requests[1]["messages"][-2:]] == ["tool", "tool"]
    assert {sku: line.quantity for sku, line in order.lines.items()} == {"CAF-002": 2, "ACC-001": 1}


def test_tool_errors_reach_the_model(order):
    agent, client = make_agent(
        order, [_tool_calls(("agregar_producto", {"sku": "XXX-1", "cantidad": 1})), _text("No tenemos ese producto.")]
    )

    agent.reply("quiero XXX-1")

    assert "No existe" in json.loads(client.requests[1]["messages"][-1]["content"])["error"]


def test_agent_stops_runaway_tool_loops(order):
    loop = [_tool_calls(("ver_pedido", {}))] * CoffeeShopAgent.MAX_TOOL_ROUNDS
    agent, _client = make_agent(order, loop)

    assert "repetir" in agent.reply("hola")


def test_request_sends_catalog_with_large_context(order):
    agent, client = make_agent(order, [_text("Hola")])
    agent.reply("hola")

    request = client.requests[0]
    system_prompt = request["messages"][0]["content"]
    assert "CAF-002 | Café Jinotega 250g molido | Tueste medio molido | C$ 147.00 | 25" in system_prompt
    # Leaving `think` unset lets Ollama keep a reasoning model's thoughts out of the reply text.
    assert "think" not in request
    assert request["options"]["num_ctx"] >= 8192


def test_customer_declining_summary_blocks_the_charge(order):
    tools = ready_to_pay(order, confirms=False)

    result = run(tools, "generar_link_de_pago", nombre="Ana", telefono="88881234")

    assert "no confirmó" in result["error"]
    assert order.payment_url is None


def test_confirmation_is_not_asked_for_an_incomplete_order(order):
    asked = []
    tools = OrderTools(order, create_pocket_charge, lambda o: asked.append(o) or True)
    run(tools, "agregar_producto", sku="CAF-001", cantidad=1)

    assert "cotizar el envío" in run(tools, "generar_link_de_pago", nombre="Ana", telefono="88881234")["error"]
    assert asked == []
