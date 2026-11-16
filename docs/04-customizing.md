# 4. Customizing

This guide shows how to change what the shop sells, how shipping is priced, which model runs,
and how the agent behaves. After any change to the prompt, a tool, or the model, run the evals
([guide 5](05-testing-and-evals.md)) to check the agent still sells correctly.

## Change the products

Edit `data/catalogo.csv`:

```csv
sku,producto,descripcion,precio_nio,stock
CAF-001,Café Jinotega 250g,Tueste medio en grano,147.00,18
ACC-004,Taza de barro 300ml,Cerámica artesanal de San Juan de Oriente,157.50,15
```

| Column | Rules |
|--------|-------|
| `sku` | Unique code. The model uses it to add products, so keep it short and stable. |
| `producto` | Name shown to the customer. |
| `descripcion` | Helps the model answer questions and match searches. Wrap it in quotes if it has commas. |
| `precio_nio` | Price in córdobas, with a dot for decimals. |
| `stock` | Units available. The agent won't sell more than this. |

Restart the agent to load the changes. The whole catalog goes into the system prompt, so keep
it small (tens of products, not thousands).

Some tests check specific products (for example `CAF-002`). If you rename or remove those, update
`tests/` and the eval scenarios too.

## Change shipping rates

Edit `data/envios.csv`:

```csv
departamento,alias,costo_nio,dias_estimados
Managua,,80.00,1-2 días hábiles
Costa Caribe Norte,RACCN|RAAN|Caribe Norte,150.00,2-4 días hábiles
```

| Column | Rules |
|--------|-------|
| `departamento` | Name shown to the customer. |
| `alias` | Other accepted names, separated by `\|`. Leave empty if none. |
| `costo_nio` | Shipping cost in córdobas. |
| `dias_estimados` | Delivery time shown to the customer. |

Matching ignores accents and case, so `esteli` finds `Estelí` without an alias.

The free-shipping threshold is in code, in `src/coffee_agent/shipping.py`:

```python
FREE_SHIPPING_FROM_NIO = Decimal("1600.00")
```

If you change it, also update the amount in `SYSTEM_PROMPT` (`agent.py`) so the Barista tells
customers the right figure.

## Change the model

Pick any Ollama model that supports tool calling:

```bash
ollama pull qwen3:4b
OLLAMA_MODEL=qwen3:4b uv run coffee-agent
```

To make it the default, change `DEFAULT_MODEL` in `src/coffee_agent/__init__.py`.

What we measured on an M3 Pro:

| Model | Size | Evals passed | Time per conversation | Notes |
|-------|------|--------------|-----------------------|-------|
| `qwen3:4b-instruct` (default) | 2.5 GB | 85% | 1-50 s | Answers directly. |
| `qwen3:4b` | 2.5 GB | 100% (1 run) | 38 s - 5 min | Reasons before every reply. |
| `qwen2.5-coder:7b` | 4.7 GB | 64% | 1.5-83 s | A coding model: writes tool calls as text instead of calling them. |

Before trusting a new model, run the evals with it:

```bash
OLLAMA_MODEL=llama3.2:3b uv run python evals/run_evals.py
```

## Change the Barista's behavior

The instructions live in `SYSTEM_PROMPT` in `src/coffee_agent/agent.py`. Edit the text, then:

1. Run the evals before the change and note the score.
2. Make the change.
3. Run the evals again, ideally with `--runs 3`, since small models vary between runs.
4. Keep the change only if the score holds or improves.

A real example from this project: adding "agrégalo de inmediato, sin preguntar" to fix the
Barista asking "¿deseas agregarlo?" dropped the score from 85% to 67%, so it was reverted.
Prompt changes on small models often have side effects you only see by measuring.

## Add a tool

Say you want the Barista to answer the shop's opening hours. Four steps:

**1. Describe the tool for the model** by adding this entry to the `TOOLS` list in `agent.py`
(followed by a comma, like the others):

```python
{
    "type": "function",
    "function": {
        "name": "horario_de_atencion",
        "description": "Devuelve el horario de atención de la tienda.",
        "parameters": {"type": "object", "properties": {}},
    },
}
```

The description matters: it's how the model decides when to use the tool.

**2. Implement it** as a method in `OrderTools`, named `_tool_` plus the tool name:

```python
def _tool_horario_de_atencion(self) -> dict:
    return {"horario": "Lunes a sábado, 8:00 a 18:00"}
```

`OrderTools.run()` finds it by name. Return a dict; raise `OrderError` with a message for errors
the customer can fix, and the model will explain them.

**3. Test it** in `tests/test_agent.py` through `OrderTools.run()`:

```python
def test_opening_hours(order):
    assert "Lunes" in make_tools(order).run("horario_de_atencion", {})["horario"]
```

**4. Add an eval scenario** so you know the real model uses it (see
[guide 5](05-testing-and-evals.md#add-an-eval-scenario)), and run the evals.

## Connect a real payment gateway

The payment is simulated in `src/coffee_agent/payments.py`. To integrate a real one, replace
`create_pocket_charge()` with a function that takes the order, calls the gateway, and sets
`order.payment_reference` and `order.payment_url`. The confirmation box and the order lock keep
working as they are.

## Next

[Guide 5: Testing and evals](05-testing-and-evals.md).
