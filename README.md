# Coffee shop agent

Terminal chat agent for an online coffee shop, powered by Claude through the Anthropic API.
It reads the catalog, builds the order, quotes shipping within Nicaragua, and closes the sale with a
simulated Pocket payment link. Prices are in córdobas (NIO, C$).
When the chat ends, it prints the order as JSON.

## Run

```bash
cp .env.example .env              # add your ANTHROPIC_API_KEY
uv run --env-file .env coffee-agent
```

Type `salir` (or Ctrl+D / Ctrl+C) to end the chat. The conversation goes to **stderr** and the
order JSON to **stdout**, so you can save it:

```bash
uv run --env-file .env coffee-agent > pedido.json
```

## How it works

| Module | Role |
|--------|------|
| `catalog.py` | Loads `data/catalogo.csv`; accent-insensitive search. |
| `order.py` | Cart rules: stock limits, totals in `Decimal`, frozen once a payment link exists. |
| `shipping.py` | Shipping quote by Nicaraguan department, using `data/envios.csv`. |
| `payments.py` | Simulated Pocket charge: a `PKT-XXXXXXXX` reference and a link on the reserved `pocket.example` domain. No network calls. |
| `agent.py` | Tools exposed to the model and the chat loop. |

The model only talks; every price, stock check, and total is computed in Python through tools
(`buscar_productos`, `agregar_producto`, `quitar_producto`, `ver_pedido`, `cotizar_envio`,
`generar_link_de_pago`).

Model setup (`agent.py`):

- Model `claude-haiku-5-5` by default, the cheapest tier (override with `ANTHROPIC_MODEL`, e.g.
  `claude-sonnet-5-5` if the evals fall short), effort `low` for snappy chat.
- The catalog (`data/catalogo.csv`, Nicaraguan origins) is part of the system prompt; tools, system
  prompt, and history are prompt-cached, so each turn pays full price only for the new messages.
- A safety refusal (`stop_reason: "refusal"`) gets a polite reply instead of an empty message.
- Tool-call loops are capped at 8 rounds per message.

## Shipping rules

Rates per department live in `data/envios.csv` (name, accepted aliases such as RACCN/RACCS,
cost in C$, and delivery time). Today: Managua C$ 80 (1–2 business days), the other 16
departments C$ 150 (2–4 business days). Free shipping from a C$ 1,600 subtotal (`shipping.py`).

## Payment (simulated)

To close the sale the agent asks for the customer's name and Pocket phone number (a Nicaraguan
mobile: 8 digits starting with 5, 7, or 8, with or without `+505`). It returns a simulated payment
link; nothing is charged. Before charging, the app (not the model) shows the summary in the
terminal and asks the customer to confirm with `s`/`n`. Replace `create_pocket_charge` in `payments.py` to integrate a real gateway.

## Checks

```bash
uv run pytest                                   # code, with a scripted model
uv run ruff check . && uv run ruff format --check .
uv run pyright
uv run --env-file .env python evals/run_evals.py [--runs N] [name-filter]   # real model, billed
```

The evals play scripted customer conversations against the real model and grade the resulting
order, plus tokens and latency per scenario. Run them before and after changing the prompt,
a tool, or the model.
