# Rules

Rules for building this project. Follow them on every phase.

## Phase discipline

1. Inspect what already exists.
2. Do the smallest change that finishes the current phase.
3. Test it.
4. Update the docs that the change affects.
5. Stop.

Do not start the next phase until asked.

## Before a significant component

Explain what it does, why it is needed, how it fits, and what it costs in latency. Then implement it.

## Code

Prefer small functions, clear names, and straight control flow. Do not add a layer, pattern, or library unless the current code cannot do the job.

Before adding a package: say why it is required, check whether the stack already covers it, and consider install size and runtime cost.

## Local latency

Do not call the model because a model is available. Ask whether a direct function can answer.

Keep prompts, history, memory, and tool descriptions as small as the task allows. A 3B-class local model gets slower and less reliable as context grows.

Measure before optimizing. Fix the largest measured cost first.

## Tools

The application runs tools. The model never executes code.

Separate read-only actions from destructive ones. Confirm before anything irreversible.

## Secrets

API keys, tokens, and passwords go in `.env` only. Commit `.env.example` with empty placeholders. Never commit `.env`.

## Do not add unless asked

Vector databases, RAG, a larger model, a UI, cloud speech APIs, background agents, or extra services.

## A phase is done when

The behavior works, a basic test passes, failures are handled, docs match the code, latency is recorded where it matters, and no extra dependency was added.
