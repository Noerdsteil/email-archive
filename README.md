# email-archive

**Your mail, searchable forever, in one folder.**

Export your mailboxes once, drop them in a folder, run `docker compose up`. You get instant keyword + semantic
search over every mail you ever sent or received, a reading pane with threads and attachments, an image export,
and an MCP endpoint so an AI assistant can search the archive too. Everything runs on your machine in one
container. Nothing leaves it.

Built in a day as a personal answer to a boring question: what happens to twenty years of mail when the provider,
the client or the plan changes? The answer is a folder that any machine with Docker can bring back to life.

<!-- screenshot: docs/screenshot.png -->

## What it does

- **Hybrid search** — full-text (SQLite FTS5) and semantic (embeddings via sqlite-vec) fused by reciprocal rank
  fusion. "Backup fehlgeschlagen" finds the mail that says "Sicherung nicht erfolgreich". ~10 ms per query.
- **Instant** — results update 120 ms after the last keystroke, ↑↓ moves the selection, Esc resets.
- **Browse** — empty query shows the whole archive newest first with infinite scroll.
- **Filters** — sender, date range, people only (no newsletters, no robots), with attachments. All mirrored in the URL,
  so a bookmark is a saved search.
- **Reading pane** — full mail, thread navigation, attachments streamed on demand from the original mbox.
- **People vs. machines** — everyone you ever wrote to counts as a person; List-Id, noreply and friends count as
  machines; the rest is marked unknown. Learned from your own sent mail, no model, no rules to maintain.
- **Image export** — one button writes every photo from the filtered mails to a folder, dated like the mail.
- **MCP server** — two tools, `search_emails` and `get_email`, for Claude Code or a local LLM front-end.
- **Portable** — the folder is the whole state. `./export.sh` zips it, `docker compose up` on the other side.

## Getting started

You need Docker (Docker Desktop, OrbStack or Docker Engine). Nothing else.

```sh
git clone https://github.com/<you>/email-archive && cd email-archive
cp .env.example .env            # put your own addresses or @domains in here
docker compose up -d            # first run builds the image and downloads the embedding model (~310 MB)
```

Open <http://localhost:8000>. The archive is empty until you import mail:

1. **Export mailboxes as mbox** into `bronze/`. Apple Mail: select a mailbox, *Mailbox → Export Mailbox…*.
   Any `*.mbox` folder or file and any `*.eml` files under `bronze/` are picked up, folder by folder.
2. **Parse and index**
   ```sh
   docker compose run --rm app python parse.py          # bronze -> silver/emails.jsonl, prints metrics
   docker compose run --rm app python gold.py build     # silver -> gold.db, ~4 mails/s on a laptop CPU, Ctrl+C safe
   docker compose restart
   ```
3. **Add mail later**: drop more mbox files into `bronze/`, repeat step 2. Both commands only add what is new;
   duplicates across folders are dropped by Message-ID.

Changed a `.py` file? `docker compose restart`. HTML/JS in `static/` reloads live.

## How it works

Three layers, each rebuildable from the one below. Nothing is ever the only copy.

| Layer | What | Where |
|---|---|---|
| bronze | raw mbox exports, never modified | `bronze/` |
| silver | one cleaned JSON record per mail | `silver/emails.jsonl` |
| gold | search index: metadata columns + FTS5 + vectors | `gold.db` (one SQLite file) |

**`parse.py`** (standard library only) decodes MIME, prefers plain text over HTML, strips quoted replies and
signatures, dedupes on Message-ID, threads via References, derives sent/received from your addresses, remembers
where each mail lives in bronze, and classifies every sender as human, machine or unknown. Prints metrics at the
end so you can see what your archive looks like before you index it.

**`gold.py`** embeds every mail with `jinaai/jina-embeddings-v2-base-de` (German + English, 8192 tokens, one
vector per mail) through fastembed/ONNX on CPU, and stores columns, FTS5 and sqlite-vec in one file. The model is
baked into the Docker image, so the index can never drift from the model that built it. `search()` fuses BM25 and
vector ranks and applies filters as SQL.

**`app.py`** is a small FastAPI service: `GET /api/search`, `GET /api/email`, `GET /api/attachment`,
`POST /api/export-images`, and the MCP server at `/mcp`. **`static/index.html`** is a single file: Vue 3 and
Tailwind 4 from vendored builds, no build step, Everforest colours.

Side tables `sources` and `classes` are refreshed on every build without re-embedding, so a classifier change
costs seconds, not an hour.

## Use it from an AI client

The server speaks MCP (Streamable HTTP) at `http://localhost:8000/mcp`. `search_emails` returns short hits,
`get_email` returns one mail with quotes stripped plus its thread. Results are kept small on purpose so a model can
search a few times before reading a mail.

```sh
claude mcp add --transport http email-archive http://localhost:8000/mcp   # Claude Code
npx @modelcontextprotocol/inspector http://localhost:8000/mcp            # click through the tools by hand
```

Anything you connect reads your mail. A cloud model sees every mail it fetches; a local LLM front-end that speaks
MCP (Open WebUI, LM Studio, Ollama-based UIs) keeps it on your machine. The endpoint accepts localhost only.

## Export images

The **Images** button runs `POST /api/export-images` with the current filters and writes every image over 50 KB
to `exports/images/`, named `date_sender_hash_name`, file date set to the mail date, duplicates saved once.
`python export_images.py` does the same for all mail from people, without the UI.

## Move it to another machine

```sh
./export.sh        # -> email-archive-YYYYMMDD.zip with code, .env, gold.db, silver/, bronze/
```

Unzip on the target, `docker compose up -d`. `bronze/` is included because attachments are read from it on demand;
`.git`, `.venv` and `models/` are not (the model is inside the image).

## Local development without Docker

Needs a Python whose sqlite allows extension loading (Homebrew `python3.13` on macOS; the system Python does not).

```sh
python3.13 -m venv .venv && .venv/bin/pip install -r requirements.txt
OWN_ADDRESSES="@example.com" .venv/bin/python parse.py
.venv/bin/python gold.py build                       # downloads the model into ./models on first run
.venv/bin/uvicorn app:app --reload --port 8000
.venv/bin/python test_parse.py                       # parser self-check on a synthetic mailbox
.venv/bin/python test_mcp.py                         # MCP self-check against a running server
```

`onnxruntime` is pinned to 1.22.1: 1.29 returns NaN and 1.23+ fails to load this model on arm64.

## Design notes

- **Silver is the contract, gold is disposable.** Every decision about embeddings can be revisited by deleting one file.
- **The model lives with the index.** No embedding service to keep in sync, no second container.
- **Bronze is read at runtime only for attachments**, by byte range, nothing copied. The price: bronze has to stay in place.
- **SQLite over Postgres.** One file, no volume, smaller image. FTS5 and sqlite-vec cover everything a personal archive needs.
- **Standard library first.** The parser has no dependencies. The UI has no build step.

## Not built yet

Chat against a local LLM through the MCP tools, an LLM pass to classify the 25 % of senders the rules leave unknown,
attachment text extraction, a Gmail/Thunderbird export guide.

## License

MIT
