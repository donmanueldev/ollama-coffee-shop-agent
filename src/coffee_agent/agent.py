import json
import re
from collections.abc import Callable
from typing import Any, Protocol

from coffee_agent.catalog import Catalog
from coffee_agent.order import Order, OrderError
from coffee_agent.payments import PaymentError
from coffee_agent.shipping import InvalidPostalCode, quote_shipping

SYSTEM_PROMPT = """\
Eres Barista, el asistente de ventas de una cafetería online mexicana. Hablas en español, \
con un tono cálido y breve. Precios en pesos mexicanos (MXN).

Reglas:
- No conoces el catálogo de memoria. Antes de mencionar cualquier producto, precio, existencia \
o costo de envío DEBES llamar a la herramienta correspondiente. Nunca inventes datos.
- Para agregar o quitar productos usa el SKU exacto que devuelve buscar_productos; si no lo \
tienes, busca primero.
- Si una herramienta devuelve un error, explícaselo al cliente con tus palabras y ofrece una \
alternativa.
- Para cerrar la venta: 1) pide el código postal y cotiza el envío, 2) muestra el resumen \
(productos, subtotal, envío y total) y pide confirmación, 3) pide nombre y email, \
4) genera el link de pago y compártelo completo.
- Cuando el cliente pida un producto, llama agregar_producto de inmediato con su SKU. Cuando dé \
su código postal, llama cotizar_envio.
- El envío es gratis a partir de $800 de subtotal.
- Si el cliente cambia el pedido después de cotizar, vuelve a cotizar el envío.

Catálogo (SKU | producto | descripción | precio MXN | stock):
{catalog}
"""

TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "buscar_productos",
            "description": "Busca en el catálogo por palabras (nombre, descripción o SKU). "
            "Sin consulta devuelve el catálogo completo.",
            "parameters": {
                "type": "object",
                "properties": {"consulta": {"type": "string", "description": "Ej. 'molido', 'prensa', 'Veracruz'"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "agregar_producto",
            "description": "Agrega unidades de un producto al pedido.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sku": {"type": "string", "description": "SKU del producto, ej. CAF-001"},
                    "cantidad": {"type": "integer", "description": "Unidades a agregar"},
                },
                "required": ["sku", "cantidad"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "quitar_producto",
            "description": "Quita unidades de un producto del pedido. Sin cantidad quita la línea completa.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sku": {"type": "string"},
                    "cantidad": {"type": "integer"},
                },
                "required": ["sku"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ver_pedido",
            "description": "Devuelve el pedido actual con subtotal, envío y total.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cotizar_envio",
            "description": "Cotiza el envío del pedido actual a un código postal de México.",
            "parameters": {
                "type": "object",
                "properties": {"codigo_postal": {"type": "string", "description": "5 dígitos"}},
                "required": ["codigo_postal"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generar_link_de_pago",
            "description": "Cierra la venta: genera el link de pago de Stripe. Úsala solo después de "
            "cotizar el envío y de que el cliente confirme el resumen.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nombre": {"type": "string", "description": "Nombre del cliente"},
                    "email": {"type": "string", "description": "Email del cliente"},
                },
                "required": ["nombre", "email"],
            },
        },
    },
]

_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
# A bracketed "[Enlace de pago]" or a markdown link, written when no link exists yet.
_INVENTED_LINK = re.compile(r"\[[^\]]*(enlace|link)[^\]]*\]|\]\(https?://", re.IGNORECASE)
_INVENTED_LINK_CORRECTION = (
    "Nota del sistema: todavía no existe un link de pago y no debes inventarlo. Si el cliente ya "
    "confirmó y dio nombre y email, llama generar_link_de_pago; si no, pídele lo que falte."
)
_TOOL_NAMES = {tool["function"]["name"] for tool in TOOLS}


def build_system_prompt(catalog: Catalog) -> str:
    # The catalog is small, so the model sees it up front; without it small models invent products.
    listing = "\n".join(f"- {p.sku} | {p.name} | {p.description} | {p.price_mxn} | {p.stock}" for p in catalog.all())
    return SYSTEM_PROMPT.format(catalog=listing)


def parse_text_tool_calls(content: str) -> list[tuple[str, dict]]:
    """Find tool calls a model wrote as plain JSON text, e.g. {"name": ..., "arguments": {...}}.

    Some local models (qwen2.5-coder among them) emit calls this way instead of using the
    native tool-call format, so Ollama returns them as ordinary content.
    """
    decoder = json.JSONDecoder()
    calls = []
    index = content.find("{")
    while index != -1:
        try:
            value, end = decoder.raw_decode(content, index)
        except json.JSONDecodeError:
            index = content.find("{", index + 1)
            continue
        if isinstance(value, dict) and value.get("name") in _TOOL_NAMES:
            arguments = value.get("arguments") or value.get("parameters") or {}
            calls.append((value["name"], arguments if isinstance(arguments, dict) else {}))
        index = content.find("{", end)
    return calls


class ChatClient(Protocol):
    def chat(self, *, model: str, messages: list, tools: list, options: dict) -> Any: ...


class OrderTools:
    """Executes the model's tool calls against the order. Returns JSON strings for the model."""

    def __init__(self, order: Order, create_payment_link: Callable[[Order], None]):
        self.order = order
        self._create_payment_link = create_payment_link

    def run(self, name: str, arguments: dict) -> str:
        handler = getattr(self, f"_tool_{name}", None)
        if handler is None:
            return json.dumps({"error": f"Herramienta desconocida: {name}"})
        try:
            result = handler(**arguments)
        except (OrderError, InvalidPostalCode, PaymentError) as e:
            result = {"error": str(e)}
        except (TypeError, ValueError):
            result = {"error": f"Argumentos inválidos para {name}: {arguments}"}
        return json.dumps(result, ensure_ascii=False)

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

    def _tool_cotizar_envio(self, codigo_postal: str | int) -> dict:
        if not self.order.lines:
            raise OrderError("Agrega productos antes de cotizar el envío.")
        quote = quote_shipping(str(codigo_postal).zfill(5), self.order.subtotal_mxn)
        self.order.set_shipping(quote)
        return {"envio": quote.to_dict(), "total_mxn": float(self.order.total_mxn)}

    def _tool_generar_link_de_pago(self, nombre: str, email: str) -> dict:
        if self.order.payment_url:
            return {"link_de_pago": self.order.payment_url, "nota": "El link ya se había generado."}
        email = email.strip()
        if not _EMAIL.fullmatch(email):
            raise OrderError(f"'{email}' no parece un email válido.")
        self.order.customer_name = nombre.strip()
        self.order.customer_email = email
        self._create_payment_link(self.order)
        return {"link_de_pago": self.order.payment_url, "total_mxn": float(self.order.total_mxn)}


class CoffeeShopAgent:
    # Small local models sometimes loop on tool calls; cap the rounds per customer message.
    MAX_TOOL_ROUNDS = 8

    # Deterministic output makes small models follow the tool protocol more reliably.
    OPTIONS = {"temperature": 0}

    def __init__(self, client: ChatClient, model: str, tools: OrderTools):
        self._client = client
        self._model = model
        self._tools = tools
        self.messages: list = [{"role": "system", "content": build_system_prompt(tools.order.catalog)}]

    def reply(self, user_text: str) -> str:
        self.messages.append({"role": "user", "content": user_text})
        corrected = False
        for _ in range(self.MAX_TOOL_ROUNDS):
            response = self._client.chat(model=self._model, messages=self.messages, tools=TOOLS, options=self.OPTIONS)
            message = response.message
            self.messages.append(message)
            if message.tool_calls:
                calls = [(c.function.name, dict(c.function.arguments or {})) for c in message.tool_calls]
            else:
                calls = parse_text_tool_calls(message.content or "")
            if not calls:
                answer = message.content or ""
                if not corrected and self._invents_payment_link(answer):
                    corrected = True
                    self.messages[-1] = {"role": "user", "content": _INVENTED_LINK_CORRECTION}
                    continue
                return self._with_payment_link(answer)
            for name, arguments in calls:
                result = self._tools.run(name, arguments)
                self.messages.append({"role": "tool", "tool_name": name, "content": result})
        return "Perdón, me enredé con tu solicitud. ¿Me la puedes repetir con otras palabras?"

    def _with_payment_link(self, answer: str) -> str:
        # Small models sometimes write "[link de pago]" instead of the URL; the customer must get it.
        url = self._tools.order.payment_url
        if url and url not in answer:
            return f"{answer}\n\nLink de pago: {url}"
        return answer

    def _invents_payment_link(self, answer: str) -> bool:
        return self._tools.order.payment_url is None and bool(_INVENTED_LINK.search(answer))
