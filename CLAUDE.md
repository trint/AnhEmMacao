# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the app locally
python main.py
# App serves at http://localhost:8080 (or $PORT env var)

# Run all tests
pytest tests/

# Run tests with verbose output
pytest tests/test_core.py -v

# Run a single test class
pytest tests/test_core.py::TestChunkScore -v

# Install production dependencies
pip install -r requirements.txt

# Install dev dependencies (includes pytest, pytest-mock)
pip install -r requirements-dev.txt

# Run with Docker
docker build -t anhemmacao .
docker run -p 8080:8080 --env-file .env anhemmacao
```

## Environment

Copy `.env.example` to `.env`. Key variables:

| Variable | Purpose |
|----------|---------|
| `GREENNODE_CLIENT_ID` / `GREENNODE_CLIENT_SECRET` | GreenNode AgentBase auth |
| `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` | Optional LLM for test case enhancement |
| `LLM_WIRE_API` | `responses` or `chat` — which OpenAI-compatible endpoint to use |
| `LLM_VISION_ENABLED` | Set `true` to enable image OCR via LLM |
| `PORT` | HTTP port, defaults to 8080 |

## Architecture

**AnhEmMacao** is a QA automation tool that converts feature descriptions and business documents into structured test cases. It runs as a standalone Starlette web app.

### Single-file monolith

All backend logic lives in `main.py` (~1,982 lines). The HTML/CSS/JS frontend (~1,635 lines) is embedded as a string literal inside `main.py` and served from the `/` route. There are no separate frontend build steps.

### Core data flow

1. **Knowledge ingestion** — Users upload or paste documents (PDF, DOCX, XLSX, plain text, images, diagrams). Text is extracted, split into overlapping chunks, and stored in `.agentbase/knowledge.json` with a keyword index and status (`READY`, `NEEDS_REVIEW`, `FAILED`). Images require `LLM_VISION_ENABLED=true` to extract text; otherwise they land in `NEEDS_REVIEW`.

2. **Test case generation** (`/chat` POST) — Given a feature description, actor, platform, and acceptance criteria, the system:
   - Retrieves the top-10 most relevant chunks from READY knowledge items using keyword overlap scoring (`retrieve_context`)
   - Generates structured test cases rule-based (always works, no LLM required)
   - Optionally calls an OpenAI-compatible LLM (`_enhance_with_llm`) to refine cases if `LLM_API_KEY` is set

3. **Output** — JSON test cases with title, type, priority, preconditions, test data, steps, expected result, references, and quality checklist. The UI displays cards; `/export/csv` exports UTF-8 BOM CSV for Google Sheets.

### Key functions

| Function | Location | Purpose |
|----------|----------|---------|
| `_keywords(text)` | `main.py` | Extract significant keywords; filters stopwords (EN + VI) |
| `_chunk_text(text)` | `main.py` | Split text into overlapping chunks with keyword index |
| `_chunk_score(query, query_kw, item, chunk)` | `main.py` | Score a chunk by keyword overlap ratio + title/type bonuses |
| `retrieve_context(query, limit)` | `main.py` | Top-N chunk retrieval from READY knowledge items |
| `build_test_cases(payload)` | `main.py` | Main orchestrator: retrieval → rule-based generation → optional LLM enhancement |
| `add_knowledge(...)` | `main.py` | Store new knowledge item with chunking |
| `_enhance_with_llm(...)` | `main.py` | Call LLM API to improve generated test cases |
| `load_test_case_types()` | `main.py` | Load custom types from `.agentbase/testcase_types.json` or return defaults |

### Knowledge persistence

Knowledge is stored in `.agentbase/knowledge.json`. All reads and writes use `filelock.FileLock` (cross-platform) via the `_knowledge_lock()` context manager. Never read or write this file without holding the lock.

### Custom test case types

Place a `testcase_types.json` in `.agentbase/` to override the 6 built-in types (Positive, Negative, Boundary, Permission, Resilience, Workflow). See `docs/testcase_types_example.json` for the schema.

### Retrieval tuning constants

```python
MAX_CONTEXT_CHARS = 6000   # max total chars sent to LLM
TOP_CONTEXT_CHUNKS = 10    # max chunks retrieved
CHUNK_SIZE = 1200          # chars per chunk
CHUNK_OVERLAP = 180        # overlap between adjacent chunks
```

### GreenNode AgentBase integration

The app registers with `greennode_agentbase` using `@app.entrypoint` (maps to `/invocations`) and `@app.ping` (maps to `/health`). These are required for production deployment on GreenNode MaaS. The `codex.toml` configures the MiniMax LLM provider for the Codex CLI.

## Tests

Tests cover the pure RAG functions and are in `tests/test_core.py`. They import `_keywords`, `_chunk_text`, `_chunk_score`, and `retrieve_context` directly from `main`. Functions that touch the filesystem (`_read_knowledge`, `_write_knowledge`) are mocked with `pytest-mock`.
