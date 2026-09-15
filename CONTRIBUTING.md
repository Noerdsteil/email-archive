# Contributing

Small project, small rules.

- **The parser stays standard library only.** `parse.py` must run on any Python 3.11+ without installing anything. Silver is the contract every later layer relies on.
- **Silver is stable, gold is disposable.** Change the embedding, the schema or the ranking freely; change the silver record shape only with a note in the README.
- **Knobs live in `settings.py`**, each with an environment override. No new constants in other files.
- **Smallest diff that works.** One file over three, stdlib over a dependency, a native browser feature over a library. Deliberate shortcuts carry a `ponytail:` comment naming the ceiling.
- **One check per behaviour.** `python test_parse.py` for the parser, `python test_search.py` for the search path on the demo mailbox, `python test_mcp.py` against a running server. Keep them plain asserts, no framework.
- **Never commit mail.** `bronze/`, `silver/`, `gold.db`, `exports/` and `.env` are ignored; the demo mailbox in `demo/make_demo.py` is invented and is what screenshots and tests use.

Run `make demo` for a throwaway archive on port 8001, `make test` before a pull request.
