# email-archive

Local, searchable archive of ~12k emails. Concept and decisions: `JonasWiki/EMAIL RAG Archive/`.

```
bronze/   Apple Mail mbox exports (Name.mbox/mbox). Sent folders prefixed `_Sent `.  gitignored
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
