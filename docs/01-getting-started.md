# 1. Getting started

This guide takes you from a fresh machine to your first conversation with the agent.
It takes about 10 minutes, most of it downloading the model.

## Step 1: Install uv

[uv](https://docs.astral.sh/uv/) manages Python and the project's dependencies. You don't need
to install Python yourself: uv downloads the right version (3.13) the first time you run the project.

```bash
brew install uv            # macOS with Homebrew
# or: curl -LsSf https://astral.sh/uv/install.sh | sh
uv --version               # check it's installed
```

## Step 2: Install Ollama

[Ollama](https://ollama.com/download) runs language models on your own computer. Download the
app for your system and open it. You'll see its icon in the menu bar while it runs.

Check it's running:

```bash
ollama --version
curl http://localhost:11434/api/version    # should print a version, not "connection refused"
```

If the `curl` fails, open the Ollama app (or run `ollama serve` in a separate terminal).

## Step 3: Download the model

```bash
ollama pull qwen3:4b-instruct
```

It's about 2.5 GB. When the download finishes you'll see `success`. If it stops halfway with
`unexpected EOF`, your connection dropped: run the same command again and it resumes where it
left off.

Check it's there:

```bash
ollama list    # qwen3:4b-instruct should appear
```

Why this model: it's light enough for a laptop, supports tool calling, and answers without a
slow reasoning step. [Guide 4](04-customizing.md#change-the-model) compares it with other options.

## Step 4: Get the code

```bash
git clone <repository-url> ollama-coffee-shop-agent
cd ollama-coffee-shop-agent
```

## Step 5: Run the agent

```bash
uv run coffee-agent
```

The first run installs the Python dependencies (a few seconds). Then you'll see:

```text
☕ Cafetería online — modelo qwen3:4b-instruct. Escribe 'salir' para terminar.

Barista: ¡Hola! ¿Qué café se te antoja hoy?
Tú:
```

Type a question in Spanish, for example `¿Qué cafés molidos tienen?`, and press Enter. The
reply appears word by word as the model writes it. The first reply can take a few extra seconds
while Ollama loads the model into memory.

To finish, type `salir` (or press Ctrl+D or Ctrl+C). The agent prints the order as JSON.

## Step 6: Check everything works (optional)

```bash
uv run pytest
```

All tests should pass. They don't need Ollama, so they also run without the model.

## Next

[Guide 2: Using the agent](02-using-the-agent.md) walks through a complete sale.
