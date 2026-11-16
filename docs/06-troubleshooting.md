# 6. Troubleshooting

## Messages from the agent

| You see | Cause | Fix |
|---------|-------|-----|
| `[No encuentro Ollama. Ábrelo (o corre ollama serve) y repite tu mensaje.]` | Ollama isn't running. | Open the Ollama app, or run `ollama serve` in another terminal. Then repeat your message. |
| `[El modelo ... no está descargado. Corre ollama pull ....]` | The model isn't downloaded. | Run the `ollama pull` command it shows, then start the agent again. |
| `[Ollama respondió con un error: ...]` | Ollama returned an error, often out of memory. | Close other heavy apps, or try a smaller model. |
| `Perdón, me enredé con tu solicitud...` | The model called tools 8 times in a row without answering. | Say it again more simply, one request per message. |

## Behavior

**The first reply takes several seconds.** Ollama loads the model into memory on first use. Later
replies are faster. Ollama unloads the model after about 5 minutes without use, so the delay
comes back after a pause.

**The Barista asks "¿deseas agregarlo?" instead of adding the product.** A known habit of
`qwen3:4b-instruct`. Answer "sí" and it adds it.

**A product I asked for is missing.** It happens sometimes when you ask for two products in one
message after a long chat. Ask for the missing one again. The confirmation box shows the full
order before any charge, so you can always check.

**The reply includes English text like "Okay, the user asked..." or `</think>`.** That's the
model's internal reasoning. It happens with reasoning models such as `qwen3:4b` if something
asks Ollama to turn thinking off. The current code doesn't, so you shouldn't see it; if you do
with another model, switch back to `qwen3:4b-instruct` and run the evals.

**Replies are very slow (minutes).** You're probably running a reasoning model such as `qwen3:4b`.
Check the model name on the first line the agent prints, and use `qwen3:4b-instruct`.

**The agent forgets products or invents ones that don't exist in a long chat.** The conversation
may have outgrown the model's context. The agent asks for 16K tokens (`num_ctx` in `agent.py`);
start a new chat, or raise that number if your machine has memory to spare.

## Setup

**`ollama pull` stops with `unexpected EOF`.** Your connection dropped. Run the same command
again; it resumes where it left off.

**`uv: command not found`.** Install uv ([guide 1](01-getting-started.md#step-1-install-uv)) and open
a new terminal.

**`curl http://localhost:11434/api/version` says "connection refused".** Ollama isn't running. Open
the app or run `ollama serve`.
