# email-archive

A searchable, private archive of your own email. Export your mailboxes once, drop them in a folder,
and get instant keyword + semantic search with a reading pane, threads and attachments in the browser.
Everything runs locally in one Docker container; nothing leaves your machine. Built to have a mail archive
that outlives mail clients and providers, and to learn how RAG-style search works on real data.

## Getting started

You need Docker (Docker Desktop, OrbStack, or plain Docker Engine). Nothing else.

1. **Get the folder** — clone this repo, or unzip an export made with `./export.sh`.
2. **Set your addresses** in `compose.yaml` (`OWN_ADDRESSES`). This decides which mails count as sent.
   Whole domains work: `@example.com`.
3. **Start it**
   ```sh
   docker compose up -d
   ```
   The first run builds the image and downloads the embedding model (~310 MB, a few minutes). Open http://localhost:8000.
   If the folder came from an export it already contains `gold.db`, and you are done.
4. **Import mail** (skip if `gold.db` came with the folder)
   - Export mailboxes as mbox. Apple Mail: select a mailbox, *Mailbox → Export Mailbox…*, save into `bronze/`.
     Any `*.mbox` folder or file and any `*.eml` files under `bronze/` are picked up.
   - ```sh
     docker compose run --rm app python parse.py          # bronze -> silver/emails.jsonl, prints metrics
     docker compose run --rm app python gold.py build     # silver -> gold.db, ~4 mails/s, resumable with Ctrl+C
     docker compose restart
     ```
5. **Add mail later**: drop more mbox files into `bronze/` and repeat step 4. Both commands only add what is new.

Changed a `.py` file? `docker compose restart`. HTML/JS in `static/` reloads live.

## Move it to another machine

```sh
./export.sh        # -> email-archive-YYYYMMDD.zip with code, gold.db, silver/, bronze/
```

Unzip on the target, `docker compose up -d`. `bronze/` is included because attachments are read from it on demand;
`.git`, `.venv` and `models/` are not (the model is inside the image).

## How it works

Three layers, each rebuildable from the one below. Nothing is ever the only copy.

| Layer | What | Where |
|---|---|---|
| bronze | raw mbox exports, never modified | `bronze/` |
| silver | one cleaned JSON record per mail | `silver/emails.jsonl` |
| gold | search index: metadata columns + FTS5 + vectors | `gold.db` (SQLite) |

- `parse.py` (stdlib only): decodes MIME, picks plain over HTML, strips quoted replies and signatures, dedupes on Message-ID,
  threads via References, derives sent/received from your addresses, records where each mail lives in bronze, and
  classifies every sender as **human / machine / unknown**: everyone you ever wrote to (To/Cc of your sent mail, written
  to `silver/contacts.json`) is human, header and address patterns (List-Id, noreply, info@, …) are machine, the rest is
  unknown; threads inherit human. "nur Menschen" in the UI means human only; unknown rows carry a `?`. Prints metrics at the end.
- `gold.py`: embeds every mail with `jinaai/jina-embeddings-v2-base-de` (German + English, 8192 tokens, one vector per mail)
  via fastembed/ONNX on CPU, stores FTS5 + sqlite-vec + columns in one file. `search()` fuses BM25 and vector ranks
  (reciprocal rank fusion) and applies filters as SQL. ~10 ms per query.
- `app.py`: FastAPI. `GET /api/search?q=&from=&since=&until=&human=&attachments=&n=`, `GET /api/email?id=`,
  `GET /api/attachment?id=&name=` (re-read from bronze by byte range, nothing extracted to disk).
- `static/index.html`: Vue 3 + Tailwind v4, vendored, no build step. Search fires 120 ms after the last keystroke,
  ↑↓ move the selection, Esc resets, `?q=` and `?id=` are linkable. Dark mode follows the OS.
  With an empty query the list is the whole archive, newest first, loaded in pages of 30 as you scroll (keyset cursor `before=date|id`, no offsets).

The model name is stored in `gold.db`; a mismatch with the code refuses to start. Rebuild with `gold.py build --rebuild`.
`sources` and `classes` are side tables refreshed on every build without re-embedding, so classifier changes cost seconds, not an hour.

## Local development without Docker

Needs a Python whose sqlite allows extension loading (Homebrew `python3.13` on macOS; the system Python does not).

```sh
/opt/homebrew/bin/python3.13 -m venv .venv && .venv/bin/pip install -r requirements.txt
OWN_ADDRESSES="@example.com" .venv/bin/python parse.py
.venv/bin/python gold.py build                       # downloads the model into ./models on first run
.venv/bin/uvicorn app:app --reload --port 8000
.venv/bin/python test_parse.py                       # parser self-check
```

`onnxruntime` is pinned to 1.22.1: 1.29 returns NaN and 1.23+ fails to load this model on arm64.

## Not built yet

MCP server over the same two endpoints, chat against a local LLM, an LLM pass to classify the machine mail that header
rules miss, attachment text extraction. Concept and decisions: `JonasWiki/EMAIL RAG Archive/`.
