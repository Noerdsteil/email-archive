# email-archive

Local, searchable archive of ~12k emails. Concept and decisions: `JonasWiki/EMAIL RAG Archive/`.

```
bronze/   Apple Mail mbox exports (Name.mbox/mbox). Sent folders suffixed `_Sent`, e.g. `Family_Sent.mbox`.  gitignored
silver/   emails.jsonl, one cleaned record per mail.                                 gitignored
models/   pinned embedding model (fastembed, offline).                                gitignored
gold      SQLite file: FTS5 + sqlite-vec + metadata columns.                          later
```

## Silver

```sh
OWN_ADDRESSES="me@a.de,me@b.com" python3 parse.py     # bronze -> silver, prints metrics
python3 test_parse.py                                 # self-check
```

Python 3.13 from Homebrew (`/opt/homebrew/bin/python3.13`): the system Python's sqlite lacks extension loading, which gold needs for sqlite-vec.

## Embedding model

`jinaai/jina-embeddings-v2-base-de` via fastembed: German+English, 8192 tokens, 768 dim, ~310 MB. One vector per email, no chunking.

```sh
/opt/homebrew/bin/python3.13 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -c 'from fastembed import TextEmbedding; TextEmbedding("jinaai/jina-embeddings-v2-base-de", cache_dir="models")'   # downloads into models/
```

`onnxruntime` is pinned to 1.22.1: 1.29 returns NaN and 1.23+ fails to load this model on arm64. Throughput ~6 emails/s on CPU.

## Gold

```sh
.venv/bin/python gold.py build [--limit 200] [--rebuild]   # silver -> gold.db, upserts only new ids, embeds
.venv/bin/python gold.py search "Rechnung" --human --from 1und1 --since 2021-01-01 -n 10
```

`gold.db` = one SQLite file: `emails` (metadata columns), `fts` (FTS5, external content), `vec` (sqlite-vec, 768 float).
Search = BM25 top-k + vector top-k, merged with reciprocal rank fusion, filters applied as SQL. ~10 ms per query after model load.
The model name is stored in `meta`; a mismatch with `gold.py` refuses to start.

## Web UI + API

```sh
.venv/bin/uvicorn app:app --reload --port 8000     # http://localhost:8000
```

`app.py` = FastAPI over `gold.search()`: `GET /api/search?q=&from=&since=&until=&human=&n=` (empty q → newest first) and `GET /api/email?id=` (full mail + thread).
`static/index.html` = one file, Vue 3 + Tailwind v4 from CDN, no build step. Tokens (oklch palette, Inter / Space Grotesk / JetBrains Mono) copied from joschwe-site; dark mode follows the OS.
Search fires 120 ms after the last keystroke, stale responses are dropped, ↑↓ moves the selection.

## Docker

```sh
docker compose up -d                                  # http://localhost:8000
docker compose run --rm app python parse.py           # bronze -> silver
docker compose run --rm app python gold.py build      # silver -> gold.db (add --rebuild after parser changes)
docker compose restart                                # after a --rebuild, so the server reopens gold.db
```

Image = python:3.13-slim + requirements (~430 MB). The project folder is bind-mounted to `/app`, so code, `models/`,
`gold.db`, `bronze/` and `silver/` all come from the folder: copying the folder is the deployment.
Vue and Tailwind are vendored in `static/vendor/`; only the Google Fonts still load from the network and fall back to system fonts offline.
Verified 2026-09-05 on linux/arm64: onnxruntime 1.22.1 loads the model and returns real vectors.
