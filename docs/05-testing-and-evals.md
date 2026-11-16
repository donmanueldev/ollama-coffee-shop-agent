# 5. Testing and evals

The project is checked in two different ways, because an agent has two different kinds of parts:

| | Unit tests | Evals |
|---|------------|-------|
| What they check | The code: order rules, shipping, tools, the agent loop | The real model driving the code |
| Model | A scripted fake that replays canned replies | The real model in Ollama |
| Speed | Under a second | A few minutes |
| Result | Pass or fail, always the same | A pass rate that varies a little between runs |
| Run them | On every change | When you change the prompt, a tool, or the model |

## Unit tests and checks

```bash
uv run pytest                                          # tests
uv run ruff check . && uv run ruff format --check .    # lint and formatting
uv run pyright                                         # type checking
```

All of them should pass before you commit. None needs Ollama.

The tests live in `tests/`:

- `test_domain.py`: catalog search, order rules (stock, totals, locking), shipping quotes.
- `test_agent.py`: each tool, the confirmation step, and the agent loop with a scripted model,
  including streaming.
- `test_cli.py`: how the terminal prints a streamed reply.

The scripted model (`ScriptedClient` in `test_agent.py`) replays responses you write by hand,
so the tests prove the code handles each case without depending on what a real model decides.

## Evals: measuring the real model

Unit tests can't tell you whether the model calls the right tool at the right moment. Evals
can: they play scripted customer conversations against the real model and grade the order it
leaves behind.

### Run them

Ollama must be open with the model downloaded.

```bash
uv run python evals/run_evals.py                  # all 11 scenarios once
uv run python evals/run_evals.py --runs 3         # each scenario 3 times
uv run python evals/run_evals.py happy            # only scenarios whose name contains "happy"
OLLAMA_MODEL=qwen3:4b uv run python evals/run_evals.py   # another model
```

### Read the output

```text
Modelo qwen3:4b-instruct · 11 escenarios × 1 corridas

PASS happy_path_esteli                23.9s   8 llamadas  máx  2753 tokens de prompt ·   737 de salida
FAIL invalid_department                4.1s   3 llamadas  máx  1625 tokens de prompt ·   164 de salida
     - productos {} != {'CAF-005': 1}
...
10/11 pasaron (91%) en 2.2 min
```

Each line shows a scenario, how long it took, how many model calls it made, the largest prompt
sent (to watch the 16K context limit), and how many tokens the model wrote. A failing scenario
lists why: here the customer asked for a tasting kit and it never reached the order.

### The scenarios

| Scenario | What it checks |
|----------|----------------|
| `happy_path_esteli` | A full sale: browse, add two products, ship to Estelí, pay. |
| `free_shipping_managua` | A C$ 1,680 order to Managua ships free. |
| `stock_limit` | Asking for 10 grinders (5 in stock) never oversells. |
| `product_not_in_catalog` | Asking for matcha tea adds nothing. |
| `invalid_department` | Shipping to Costa Rica is refused. |
| `change_after_quote` | Adding products after a quote triggers a new quote. |
| `remove_item` | Removing a product leaves only the rest. |
| `invalid_phone` | A 4-digit phone never gets a payment link. |
| `no_link_without_confirmation` | No link when the customer declines the summary. |
| `customer_declines_summary` | Same, after a complete order. |
| `long_conversation` | 11 questions of small talk, then a sale: the agent still remembers the catalog. |

Every scenario also fails if a reply writes an amount with `$` instead of `C$`, or if the
model's internal reasoning leaks into a reply.

### Results so far

Measured on an M3 Pro with Ollama:

| Model | Pass rate | All 11 scenarios |
|-------|-----------|------------------|
| `qwen3:4b-instruct` | 27-28 of 33 (82-85%, 3 runs) | ~2.5 min |
| `qwen3:4b` | 11 of 11 (1 run) | ~21 min |

The default model's usual misses: it asks "¿deseas agregarlo?" instead of adding a product right
away, and in long chats it sometimes drops the second of two products requested together.

### Add an eval scenario

Scenarios are in the `SCENARIOS` list in `evals/run_evals.py`. Each has a name, the customer's
messages, and checks on the final order. Add yours to the list (followed by a comma):

```python
Scenario(
    "remove_then_pay",
    [
        "Quiero una prensa francesa y un molino manual",
        "Mejor quita el molino",
        "Envío a Granada",
        "Luis Ruiz, 7777 1234",
    ],
    [lines_are({"ACC-001": 1}), shipping_is("Granada", "150"), paid(True)],
)
```

Available checks:

| Check | Passes when |
|-------|-------------|
| `lines_are({"SKU": qty, ...})` | The order has exactly these products and quantities. |
| `shipping_is("Dept", "cost")` | Shipping was quoted to that department (and cost). `shipping_is(None)` means no quote. |
| `paid(True)` / `paid(False)` | A payment link was / wasn't generated. |
| `last_answer_has_link` | The final reply includes the real payment link. |

The confirmation box answers `s` by default. To test a customer who declines, add
`confirmations=[False]` to the scenario.

Run your new scenario a few times with the filter (`uv run python evals/run_evals.py remove_then`)
before trusting it: a scenario that fails because its expectation is wrong teaches you nothing.

## Next

[Guide 6: Troubleshooting](06-troubleshooting.md).
