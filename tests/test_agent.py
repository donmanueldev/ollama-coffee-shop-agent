import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import stripe

from coffee_agent.agent import CoffeeShopAgent, OrderTools, parse_text_tool_calls
from coffee_agent.catalog import Catalog
from coffee_agent.order import Order
from coffee_agent.payments import create_payment_link

CATALOG_PATH = Path(__file__).resolve().parents[1] / "data" / "catalogo.csv"


class FakeSessions:
    def __init__(self, error: Exception | None = None):
        self.params = None
        self._error = error

    def create(self, params):
        if self._error:
            raise self._error
        self.params = params
        return SimpleNamespace(id="cs_test_123", url="https://checkout.stripe.com/c/pay/cs_test_123")


def fake_stripe(sessions: FakeSessions):
    return SimpleNamespace(v1=SimpleNamespace(checkout=SimpleNamespace(sessions=sessions)))


@pytest.fixture
def order() -> Order:
    return Order(Catalog.from_csv(CATALOG_PATH))


def make_tools(order: Order, sessions: FakeSessions) -> OrderTools:
    return OrderTools(order, lambda o: create_payment_link(fake_stripe(sessions), o, "https://x.test/ok"))


def run(tools: OrderTools, name: str, **args) -> dict:
    return json.loads(tools.run(name, args))


def test_full_sale_creates_checkout_with_items_and_shipping(order):
    sessions = FakeSessions()
    tools = make_tools(order, sessions)

    run(tools, "agregar_producto", sku="CAF-001", cantidad="2")  # models often send strings
    run(tools, "cotizar_envio", codigo_postal="44100")
    result = run(tools, "generar_link_de_pago", nombre="Ana", email="ana@example.com")

    assert result["link_de_pago"] == "https://checkout.stripe.com/c/pay/cs_test_123"
    item = sessions.params["line_items"][0]
    assert item["quantity"] == 2
    assert item["price_data"]["unit_amount"] == 14700
    assert sessions.params["shipping_options"][0]["shipping_rate_data"]["fixed_amount"]["amount"] == 14900
    assert sessions.params["customer_email"] == "ana@example.com"
    assert order.to_dict()["estado"] == "pendiente_de_pago"


def test_payment_link_requires_shipping_quote(order):
    sessions = FakeSessions()
    tools = make_tools(order, sessions)
    run(tools, "agregar_producto", sku="CAF-001", cantidad=1)

    result = run(tools, "generar_link_de_pago", nombre="Ana", email="ana@example.com")

    assert "cotizar el envío" in result["error"]
    assert sessions.params is None


def test_invalid_email_is_reported_to_model(order):
    tools = make_tools(order, FakeSessions())
    run(tools, "agregar_producto", sku="CAF-001", cantidad=1)
    run(tools, "cotizar_envio", codigo_postal="03100")

    assert "email válido" in run(tools, "generar_link_de_pago", nombre="Ana", email="ana@")["error"]


def test_stripe_failure_becomes_tool_error(order):
    tools = make_tools(order, FakeSessions(error=stripe.AuthenticationError("Invalid API Key")))
    run(tools, "agregar_producto", sku="CAF-001", cantidad=1)
    run(tools, "cotizar_envio", codigo_postal="03100")

    result = run(tools, "generar_link_de_pago", nombre="Ana", email="ana@example.com")

    assert "Stripe rechazó" in result["error"]
    assert order.payment_url is None


def test_bad_arguments_and_unknown_tools_do_not_crash(order):
    tools = make_tools(order, FakeSessions())
    assert "Argumentos inválidos" in run(tools, "agregar_producto", sku="CAF-001", cantidad="dos")["error"]
    assert "desconocida" in run(tools, "hackear")["error"]


def test_postal_code_sent_as_number_keeps_leading_zero(order):
    tools = make_tools(order, FakeSessions())
    run(tools, "agregar_producto", sku="CAF-001", cantidad=1)
    assert run(tools, "cotizar_envio", codigo_postal=3100)["envio"]["zona"] == "local (CDMX)"


def _msg(content="", tool_calls=None):
    return SimpleNamespace(message=SimpleNamespace(role="assistant", content=content, tool_calls=tool_calls))


def _call(name, **arguments):
    return SimpleNamespace(function=SimpleNamespace(name=name, arguments=arguments))


class ScriptedClient:
    def __init__(self, responses):
        self._responses = iter(responses)

    def chat(self, *, model, messages, tools, options):
        return next(self._responses)


def test_agent_executes_tool_calls_then_answers(order):
    client = ScriptedClient(
        [_msg(tool_calls=[_call("agregar_producto", sku="ACC-001", cantidad=1)]), _msg("Listo, agregué la prensa.")]
    )
    agent = CoffeeShopAgent(client, "test-model", make_tools(order, FakeSessions()))

    assert agent.reply("quiero una prensa") == "Listo, agregué la prensa."
    assert order.lines["ACC-001"].quantity == 1
    assert agent.messages[-2]["role"] == "tool"


def test_agent_stops_runaway_tool_loops(order):
    loop = [_msg(tool_calls=[_call("ver_pedido")])] * CoffeeShopAgent.MAX_TOOL_ROUNDS
    agent = CoffeeShopAgent(ScriptedClient(loop), "test-model", make_tools(order, FakeSessions()))

    assert "repetir" in agent.reply("hola")


def test_agent_runs_tool_calls_written_as_text(order):
    client = ScriptedClient(
        [_msg('{"name": "agregar_producto", "arguments": {"sku": "CAF-002", "cantidad": 2}}'), _msg("Agregado.")]
    )
    agent = CoffeeShopAgent(client, "test-model", make_tools(order, FakeSessions()))

    assert agent.reply("quiero 2 molidos") == "Agregado."
    assert order.lines["CAF-002"].quantity == 2


def test_parse_text_tool_calls_handles_fences_and_ignores_other_json():
    content = (
        "```json\n"
        '{"name": "buscar_productos", "arguments": {"consulta": "molido"}}\n'
        '{"name": "borrar_todo", "arguments": {}}\n'
        "```"
    )
    assert parse_text_tool_calls(content) == [("buscar_productos", {"consulta": "molido"})]
    assert parse_text_tool_calls("Tenemos café {rico} y barato") == []


def test_system_prompt_lists_catalog(order):
    agent = CoffeeShopAgent(ScriptedClient([]), "test-model", make_tools(order, FakeSessions()))
    prompt = agent.messages[0]["content"]
    assert "CAF-002 | Café Chiapas 250g molido | Tueste medio molido | 147.00 | 25" in prompt


def test_agent_appends_payment_link_when_model_omits_it(order):
    tools = make_tools(order, FakeSessions())
    run(tools, "agregar_producto", sku="CAF-001", cantidad=1)
    run(tools, "cotizar_envio", codigo_postal="03100")
    client = ScriptedClient(
        [
            _msg(tool_calls=[_call("generar_link_de_pago", nombre="Ana", email="ana@example.com")]),
            _msg("Aquí tienes tu enlace: [Enlace de pago]"),
        ]
    )
    agent = CoffeeShopAgent(client, "test-model", tools)

    assert agent.reply("confirmo").endswith("Link de pago: https://checkout.stripe.com/c/pay/cs_test_123")


def test_agent_corrects_invented_payment_link(order):
    tools = make_tools(order, FakeSessions())
    run(tools, "agregar_producto", sku="CAF-001", cantidad=1)
    run(tools, "cotizar_envio", codigo_postal="03100")
    client = ScriptedClient(
        [
            _msg("Gracias Ana, aquí está tu link: [Enlace de pago]"),
            _msg(tool_calls=[_call("generar_link_de_pago", nombre="Ana", email="ana@example.com")]),
            _msg("Listo: https://checkout.stripe.com/c/pay/cs_test_123"),
        ]
    )
    agent = CoffeeShopAgent(client, "test-model", tools)

    assert agent.reply("confirmo, Ana, ana@example.com") == "Listo: https://checkout.stripe.com/c/pay/cs_test_123"
    assert all("[Enlace de pago]" not in str(getattr(m, "content", m)) for m in agent.messages)
