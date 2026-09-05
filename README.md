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
