# Coffee shop agent

A practice project: a terminal chat agent that sells coffee for an online shop in Nicaragua.
It answers questions about the catalog, builds the order, quotes shipping by department, and
closes the sale with a simulated Pocket payment link. Prices are in córdobas (C$). When the chat
ends, it prints the order as JSON.

It runs entirely on your machine with a local [Ollama](https://ollama.com) model: no API keys,
no cost, no internet.

## Quick start

```bash
ollama pull qwen3:4b-instruct   # once, about 2.5 GB
uv run coffee-agent             # start chatting; type "salir" to finish
```

Needs [uv](https://docs.astral.sh/uv/) and Ollama installed and open. The
[getting started guide](docs/01-getting-started.md) walks through it from zero.

## Documentation

Read the guides in order the first time:

| # | Guide | What you'll learn |
|---|-------|-------------------|
| 1 | [Getting started](docs/01-getting-started.md) | Install the tools, download the model, run the agent. |
| 2 | [Using the agent](docs/02-using-the-agent.md) | A full sale step by step, the confirmation box, the JSON output. |
| 3 | [How it works](docs/03-how-it-works.md) | The modules, the agent loop, tools, streaming, and why the code owns the money. |
| 4 | [Customizing](docs/04-customizing.md) | Change products, shipping rates, the model, the prompt; add a tool. |
| 5 | [Testing and evals](docs/05-testing-and-evals.md) | Unit tests, checks, and measuring the real model with evals. |
| 6 | [Troubleshooting](docs/06-troubleshooting.md) | Common errors and how to fix them. |

## Project layout

```text
data/
  catalogo.csv        products: SKU, name, description, price, stock
  envios.csv          shipping cost and delivery time per department
src/coffee_agent/
  __init__.py         terminal app: chat loop, confirmation box, JSON output
  agent.py            system prompt, tools, and the agent loop
  catalog.py          loads and searches the catalog
  order.py            cart rules and totals
  shipping.py         shipping quotes by department
  payments.py         simulated Pocket charge
  text.py             accent-insensitive matching and C$ formatting
tests/                unit tests (no model needed)
evals/run_evals.py    scripted conversations against the real model
```
