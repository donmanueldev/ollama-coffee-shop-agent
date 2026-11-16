# Coffee shop agent

Terminal chat agent for an online coffee shop in Nicaragua, running on a local
[Ollama](https://ollama.com) model. It answers questions about the catalog, builds the order,
quotes shipping by department, and closes the sale with a simulated Pocket payment link.
Prices are in córdobas (C$). When the chat ends, it prints the order as JSON.

Everything runs on your machine: no API keys, no cost, no internet needed.

## Requirements

- [uv](https://docs.astral.sh/uv/) (Python 3.13 is installed by uv automatically)
- [Ollama](https://ollama.com/download), open and running
- About 3 GB of disk and memory for the default model

## Setup

Download the model once:

```bash
ollama pull qwen3:4b-instruct
```

Python dependencies install on the first `uv run`.

## Usage

```bash
uv run coffee-agent
```

Chat in Spanish as a customer would. A typical sale:

```text
Barista: ¡Hola! ¿Qué café se te antoja hoy?
Tú: ¿Qué cafés molidos tienen?
Barista: Tenemos el Café Jinotega 250g molido, tueste medio, a C$ 147.00. ¿Te lo agrego?
Tú: Quiero 2 y una taza de barro
Barista: Listo. Subtotal: C$ 451.50. ¿A qué departamento lo enviamos?
Tú: Es para León
Barista: El envío a León cuesta C$ 150.00 (2-4 días hábiles). Total: C$ 601.50.
         ¿Me das tu nombre y el teléfono de tu cuenta Pocket?
Tú: Ana López, 8888 1234

──── Confirma tu pedido ────
  2 × Café Jinotega 250g molido             C$ 294.00
  1 × Taza de barro 300ml                   C$ 157.50
  Envío a León (2-4 días hábiles)           C$ 150.00
  Total                                     C$ 601.50
  Cobro Pocket a Ana López · +50588881234
¿Confirmas el pedido? (s/n): s
Barista: ¡Gracias, Ana! Tu link de pago: https://pocket.example/cobro/PKT-1363BCD0
Tú: salir
```

The model's wording changes from run to run; the amounts don't, because the code computes them.

The confirmation box comes from the app, not the model: answer `s` to generate the payment link
or `n` to keep editing the order. Before closing, the agent needs:

1. At least one product.
2. The shipping department (any of Nicaragua's 17, e.g. `Managua`, `Estelí`, `RACCN`).
3. The customer's name and Pocket phone: a Nicaraguan mobile, 8 digits starting with 5, 7, or 8,
   with or without `+505`.

End the chat with `salir`, Ctrl+D, or Ctrl+C. The order is then printed as JSON:

```json
{
  "estado": "pendiente_de_pago",
  "moneda": "NIO",
  "cliente": { "nombre": "Ana López", "telefono": "+50588881234" },
  "productos": [
    { "sku": "CAF-002", "producto": "Café Jinotega 250g molido", "cantidad": 2,
      "precio_unitario_nio": 147.0, "total_nio": 294.0 },
    { "sku": "ACC-004", "producto": "Taza de barro 300ml", "cantidad": 1,
      "precio_unitario_nio": 157.5, "total_nio": 157.5 }
  ],
  "subtotal_nio": 451.5,
  "envio": { "departamento": "León", "costo_nio": 150.0, "dias_estimados": "2-4 días hábiles" },
  "total_nio": 601.5,
  "pago": { "metodo": "Pocket (simulado)", "referencia": "PKT-1363BCD0",
            "link": "https://pocket.example/cobro/PKT-1363BCD0" }
}
```

`estado` is `vacio` (no products), `abierto` (products, no payment link yet), or
`pendiente_de_pago` (link generated).

The chat goes to stderr and the JSON to stdout, so you can save just the order:

```bash
uv run coffee-agent > pedido.json
```

### Another model

The default `qwen3:4b-instruct` answers directly. Its sibling `qwen3:4b` reasons before every
reply: more accurate, much slower. Measured with the evals on an M3 Pro:

| Model | Evals passed | Time per conversation |
|-------|--------------|-----------------------|
| `qwen3:4b-instruct` (default) | 28/33 (85%) | 1–50 s |
| `qwen3:4b` | 11/11 (1 run) | 38 s – 5 min |

The instruct model's misses: it sometimes asks "¿deseas agregarlo?" instead of adding a product
right away, and in long chats it can drop the second of two products requested together (the
confirmation box shows the order before charging, so the customer can catch it).

To use another model:

```bash
ollama pull qwen3:4b
OLLAMA_MODEL=qwen3:4b uv run coffee-agent
```

It must support tool calling. Run the evals (below) before relying on a new one.

### Troubleshooting

| Message | Fix |
|---------|-----|
| `No encuentro Ollama...` | Open the Ollama app, or run `ollama serve`. |
| `El modelo ... no está descargado` | Run the `ollama pull` it suggests. |
| Very slow first reply | Ollama is loading the model into memory; later replies are faster. |

## Editing the data

- `data/catalogo.csv`: products (SKU, name, description, price in C$, stock).
- `data/envios.csv`: shipping cost and delivery time per department, plus accepted aliases.
  Free shipping starts at a C$ 1,600 subtotal (`FREE_SHIPPING_FROM_NIO` in `shipping.py`).

The payment is simulated: the link uses the reserved `pocket.example` domain and nothing is
charged. Replace `create_pocket_charge` in `payments.py` to integrate a real gateway.

## How it works

| Module | Role |
|--------|------|
| `catalog.py` | Loads the catalog; accent-insensitive search. |
| `order.py` | Cart rules: stock limits, totals in `Decimal`, frozen once a payment link exists. |
| `shipping.py` | Shipping quote by department. |
| `payments.py` | Simulated Pocket charge. |
| `agent.py` | Tools exposed to the model, the system prompt, and the chat loop. |
| `__init__.py` | Terminal app: chat loop, confirmation box, JSON output. |

The model only talks and picks tools (`buscar_productos`, `agregar_producto`, `quitar_producto`,
`ver_pedido`, `cotizar_envio`, `generar_link_de_pago`); every price, stock check, and total is
computed in Python. The catalog is part of the system prompt, the context is raised to 16K
tokens so long chats keep the system prompt, and replies stream to the terminal as the model
writes them.

## Development checks

```bash
uv run pytest                                          # code, with a scripted model
uv run ruff check . && uv run ruff format --check .
uv run pyright
uv run python evals/run_evals.py [--runs N] [filter]   # real local model, needs Ollama
```

The evals play 11 scripted customer conversations against the local model and grade the
resulting order. Run them before and after changing the prompt, a tool, or the model.
