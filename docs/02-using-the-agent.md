# 2. Using the agent

This guide walks through a complete sale, from the first question to the payment link, and
explains the JSON the agent prints at the end. You play the customer; the agent is "Barista".

Start the agent:

```bash
uv run coffee-agent
```

The model's wording changes from run to run. The amounts never do, because the code computes
them (see [guide 3](03-how-it-works.md)).

## Step 1: Ask about the catalog

```text
Tú: ¿Qué cafés molidos tienen?
Barista: Tenemos el Café Jinotega 250g molido, tueste medio, a C$ 147.00. ¿Te lo agrego?
```

You can ask about any product, its price, its stock, or ask for a recommendation. The catalog
has 10 products: coffees from Jinotega, Matagalpa, and Nueva Segovia, plus accessories.

## Step 2: Build the order

Say what you want, with quantities:

```text
Tú: Quiero 2 y una taza de barro
Barista: Listo. Agregué 2 Café Jinotega 250g molido y 1 Taza de barro 300ml.
         Subtotal: C$ 451.50. ¿A qué departamento lo enviamos?
```

You can also remove items (`quita la taza`) or change quantities. If you ask for more units
than are in stock, the agent tells you how many are available.

## Step 3: Quote shipping

Give the department where the order goes:

```text
Tú: Es para León
Barista: El envío a León cuesta C$ 150.00 (2-4 días hábiles). Total: C$ 601.50.
         ¿Me das tu nombre y el teléfono de tu cuenta Pocket?
```

Shipping rules:

- Managua: C$ 80, 1-2 business days.
- Any other department: C$ 150, 2-4 business days.
- Free from a C$ 1,600 subtotal.

You can write the department without accents (`esteli`), or use the aliases `RACCN` and `RACCS`
for the Caribbean coast. Places outside Nicaragua are rejected.

If you change the order after the quote, the agent quotes again, because the subtotal may now
qualify for free shipping.

## Step 4: Give your name and Pocket phone

```text
Tú: Ana López, 8888 1234
```

The phone must be a Nicaraguan mobile: 8 digits starting with 5, 7, or 8. Spaces, dashes, and
the `+505` prefix are fine. An invalid number (for example `1234`) is rejected and the agent
asks again.

## Step 5: Confirm the order

Before charging, the app (not the model) shows the summary and asks you directly:

```text
──── Confirma tu pedido ────
  2 × Café Jinotega 250g molido             C$ 294.00
  1 × Taza de barro 300ml                   C$ 157.50
  Envío a León (2-4 días hábiles)           C$ 150.00
  Total                                     C$ 601.50
  Cobro Pocket a Ana López · +50588881234
¿Confirmas el pedido? (s/n):
```

- Type `s` (or `si`, `sí`, `y`, `yes`) to generate the payment link.
- Type anything else to cancel. The agent asks what you want to change, and the order stays
  editable.

## Step 6: Get the payment link

```text
Barista: ¡Gracias, Ana! Tu link de pago: https://pocket.example/cobro/PKT-1363BCD0
```

The payment is simulated: the link uses the reserved `pocket.example` domain and nothing is
charged. Once the link exists, the order is locked and can't be changed.

## Step 7: Finish and read the JSON

Type `salir`. The agent prints the order:

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

| Field | Meaning |
|-------|---------|
| `estado` | `vacio` (no products), `abierto` (products, no link yet), or `pendiente_de_pago` (link generated). |
| `moneda` | Always `NIO` (córdobas). |
| `cliente` | Name and phone, filled when you give them in step 4. |
| `productos` | One entry per product, with unit price and line total. |
| `subtotal_nio` | Sum of the product lines. |
| `envio` | The shipping quote, or `null` if none yet. |
| `total_nio` | Subtotal plus shipping. |
| `pago` | Payment reference and link, or `null` before step 6. |

You get the JSON even if you leave in the middle of a sale; it shows the order as it was.

## Save only the order

The chat goes to stderr and the JSON to stdout, so you can save the order to a file while still
seeing the chat:

```bash
uv run coffee-agent > pedido.json
```

## Next

[Guide 3: How it works](03-how-it-works.md) explains what happens behind each message.
