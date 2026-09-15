# Everyday commands. `make` lists them.
.DEFAULT_GOAL := help
DEMO = docker compose run --rm -e DATA_DIR=demo -e OWN_ADDRESSES=@example.com

help:            ## this list
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F ':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'
up:              ## build image (first time: downloads the model) and start -> http://localhost:8000
	docker compose up -d
import:          ## bronze -> silver -> gold, then restart. Only new mail is embedded.
	./import.sh
demo:            ## try it on a synthetic mailbox under demo/ -> http://localhost:8001 . Never touches your archive.
	$(DEMO) app sh -c "python demo/make_demo.py && python parse.py && python gold.py build"
	$(DEMO) -p 8001:8000 app uvicorn app:app --host 0.0.0.0 --port 8000
test:            ## parser + search self-checks (local venv, needs the model in ./models)
	.venv/bin/python test_parse.py && .venv/bin/python test_search.py
export:          ## zip the folder for another machine
	./export.sh
logs:            ## follow the server log
	docker compose logs -f app
down:            ## stop
	docker compose down
.PHONY: help up import demo test export logs down
