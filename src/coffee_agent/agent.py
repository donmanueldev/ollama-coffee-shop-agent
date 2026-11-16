import json
import re
from collections.abc import Callable

import anthropic
from anthropic.types import MessageParam, TextBlock, ToolParam, ToolResultBlockParam, ToolUseBlock

from coffee_agent.catalog import Catalog
from coffee_agent.order import Order, OrderError
from coffee_agent.shipping import InvalidDepartment, departments, quote_shipping
from coffee_agent.text import cordobas

SYSTEM_PROMPT = """\
Eres Barista, el asistente de ventas de una cafetería online en Nicaragua. Atiendes por chat, en \
español, con un tono cálido y breve. La moneda es el córdoba nicaragüense; escribe los montos \
como C$ 147.00.

Los precios, el stock, el envío y el cobro los calcula el sistema a través de tus herramientas: \
usa sus resultados y no estimes montos por tu cuenta. Agrega o quita productos con su SKU en \
cuanto el cliente lo pida. Si una herramienta devuelve un error, explícale al cliente qué pasó y \
ofrécele una alternativa.

Para cerrar la venta:
1. Pregunta a qué departamento se envía y cotiza el envío (es gratis desde C$ 1,600 de \
subtotal). Si el pedido cambia después, vuelve a cotizarlo.
2. Muestra el resumen: productos, subtotal, envío y total.
3. Pide el nombre del cliente y el teléfono de su cuenta Pocket.
4. Llama generar_link_de_pago. El sistema le muestra el resumen al cliente para que lo confirme \
antes de cobrar. Si lo confirma, comparte el link completo; si no, pregúntale qué quiere cambiar.

Catálogo (SKU | producto | descripción | precio | stock):
{catalog}
"""

TOOLS: list[ToolParam] = [
    {
        "name": "buscar_productos",
        "description": "Busca en el catálogo por palabras (nombre, descripción o SKU). "
        "Sin consulta devuelve el catálogo completo.",
        "input_schema": {
            "type": "object",
            "properties": {"consulta": {"type": "string", "description": "Ej. 'molido', 'prensa', 'Jinotega'"}},
        },
    },
    {
        "name": "agregar_producto",
        "description": "Agrega unidades de un producto al pedido.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sku": {"type": "string", "description": "SKU del producto, ej. CAF-001"},
                "cantidad": {"type": "integer", "description": "Unidades a agregar"},
            },
            "required": ["sku", "cantidad"],
        },
    },
    {
        "name": "quitar_producto",
        "description": "Quita unidades de un producto del pedido. Sin cantidad quita la línea completa.",
        "input_schema": {
            "type": "object",
            "properties": {"sku": {"type": "string"}, "cantidad": {"type": "integer"}},
            "required": ["sku"],
        },
    },
    {
        "name": "ver_pedido",
        "description": "Devuelve el pedido actual con subtotal, envío y total.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "cotizar_envio",
        "description": "Cotiza el envío del pedido actual a un departamento de Nicaragua.",
        "input_schema": {
            "type": "object",
            "properties": {"departamento": {"type": "string", "description": ", ".join(departments())}},
            "required": ["departamento"],
        },
    },
    {
        "name": "generar_link_de_pago",
        "description": "Cierra la venta con un cobro Pocket. Antes de cobrar, el sistema le pide al cliente "
        "que confirme el resumen; devuelve el link de pago o el motivo por el que no se generó.",
        "input_schema": {
            "type": "object",
            "properties": {
                "nombre": {"type": "string", "description": "Nombre del cliente"},
                "telefono": {"type": "string", "description": "Teléfono de su cuenta Pocket, 8 dígitos"},
            },
            "required": ["nombre", "telefono"],
        },
    },
]

# Nicaraguan mobile numbers: 8 digits starting with 5, 7 or 8, optionally prefixed with 505.
_PHONE = re.compile(r"(?:505)?([578]\d{7})")


def build_system_prompt(catalog: Catalog) -> str:
    # The catalog is small and stable, so it rides in the cached prompt instead of costing a tool call.
    listing = "\n".join(
        f"- {p.sku} | {p.name} | {p.description} | {cordobas(p.price_nio)} | {p.stock}" for p in catalog.all()
    )
    return SYSTEM_PROMPT.format(catalog=listing)


class OrderTools:
    """Executes the model's tool calls against the order."""

    def __init__(
        self,
        order: Order,
        create_payment_link: Callable[[Order], None],
        customer_confirms: Callable[[Order], bool],
    ):
        self.order = order
        self._create_payment_link = create_payment_link
        # The customer confirms through the app, not through the model, so a misread "sí" can't charge.
        self._customer_confirms = customer_confirms

    def run(self, name: str, arguments: dict) -> tuple[dict, bool]:
        """Return the tool's result and whether it is an error the model should explain."""
        handler = getattr(self, f"_tool_{name}", None)
        if handler is None:
            return {"error": f"Herramienta desconocida: {name}"}, True
        try:
            return handler(**arguments), False
        except (OrderError, InvalidDepartment) as e:
            return {"error": str(e)}, True
        except (TypeError, ValueError):
            return {"error": f"Argumentos inválidos para {name}: {arguments}"}, True

    def _tool_buscar_productos(self, consulta: str = "") -> dict:
        products = self.order.catalog.search(consulta)
        return {"resultados": [p.to_dict() for p in products]}

    def _tool_agregar_producto(self, sku: str, cantidad: int | str) -> dict:
        line = self.order.add(sku, int(cantidad))
        return {"agregado": line.product.name, "cantidad_en_pedido": line.quantity, "pedido": self.order.to_dict()}

    def _tool_quitar_producto(self, sku: str, cantidad: int | str | None = None) -> dict:
        self.order.remove(sku, int(cantidad) if cantidad not in (None, "") else None)
        return {"pedido": self.order.to_dict()}

    def _tool_ver_pedido(self) -> dict:
        return {"pedido": self.order.to_dict()}

    def _tool_cotizar_envio(self, departamento: str) -> dict:
        if not self.order.lines:
            raise OrderError("Agrega productos antes de cotizar el envío.")
        quote = quote_shipping(departamento, self.order.subtotal_nio)
        self.order.set_shipping(quote)
        return {"envio": quote.to_dict(), "total_nio": float(self.order.total_nio)}

    def _tool_generar_link_de_pago(self, nombre: str, telefono: str | int) -> dict:
        if self.order.payment_url:
            return {"link_de_pago": self.order.payment_url, "nota": "El link ya se había generado."}
        match = _PHONE.fullmatch(re.sub(r"[\s\-+()]", "", str(telefono)))
        if not match:
            raise OrderError(f"'{telefono}' no parece un número móvil de Nicaragua (8 dígitos).")
        self.order.customer_name = nombre.strip()
        self.order.customer_phone = f"+505{match.group(1)}"
        self.order.ensure_ready_for_payment()
        if not self._customer_confirms(self.order):
            raise OrderError("El cliente no confirmó el resumen. Pregúntale qué quiere cambiar.")
        self._create_payment_link(self.order)
        return {
            "link_de_pago": self.order.payment_url,
            "referencia": self.order.payment_reference,
            "total_nio": float(self.order.total_nio),
        }


class CoffeeShopAgent:
    # A runaway sequence of tool calls should end the turn, not spin forever.
    MAX_TOOL_ROUNDS = 8
    # Chat replies with short tool hops; low effort keeps latency and cost down. Re-check with the evals.
    EFFORT = "low"
    REFUSAL_REPLY = "Perdón, no puedo ayudarte con eso. ¿Te ayudo con tu pedido de café?"

    def __init__(self, client: anthropic.Anthropic, model: str, tools: OrderTools):
        self._client = client
        self._model = model
        self._tools = tools
        self._system = build_system_prompt(tools.order.catalog)
        self.messages: list[MessageParam] = []

    def reply(self, user_text: str) -> str:
        self.messages.append({"role": "user", "content": user_text})
        for _ in range(self.MAX_TOOL_ROUNDS):
            response = self._client.messages.create(
                model=self._model,
                max_tokens=16000,
                system=self._system,
                tools=TOOLS,
                messages=self.messages,
                output_config={"effort": self.EFFORT},
                # Caches tools + system + history up to the last block, so each turn pays only for what's new.
                cache_control={"type": "ephemeral"},
            )
            # Keep the full content (thinking and tool_use blocks included); the API expects it back as is.
            self.messages.append({"role": "assistant", "content": response.content})
            if response.stop_reason == "refusal":
                return self.REFUSAL_REPLY
            if response.stop_reason != "tool_use":
                return "".join(block.text for block in response.content if isinstance(block, TextBlock))
            self.messages.append({"role": "user", "content": self._run_tools(response.content)})
        return "Perdón, me enredé con tu solicitud. ¿Me la puedes repetir con otras palabras?"

    def _run_tools(self, content: list) -> list[ToolResultBlockParam]:
        results: list[ToolResultBlockParam] = []
        for block in content:
            if isinstance(block, ToolUseBlock):
                result, is_error = self._tools.run(block.name, dict(block.input))
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result, ensure_ascii=False),
                        "is_error": is_error,
                    }
                )
        return results
