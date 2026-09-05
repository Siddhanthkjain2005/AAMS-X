# AAMS-X — one entry point per task. `make` alone lists them.
#
# Everything runs from the repository root and uses the local virtualenv at .venv
# so a stale system python cannot silently be picked up.

VENV    := .venv
PY      := $(VENV)/bin/python
PIP     := $(VENV)/bin/pip
SEEDS   ?= 6
PORT    ?= 8000

.DEFAULT_GOAL := help
.PHONY: help setup data index test test-fast lint fmt typecheck verify-docs api web web-install \
        web-build benchmark ablation head-to-head tune sensitivity report clean clean-index \
        docker docker-up docker-down all

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

# ---- backend ----------------------------------------------------------------

$(PY):
	python3 -m venv $(VENV)

setup: $(PY) ## Create .venv and install the package with dev extras
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"
	@test -f .env || cp .env.example .env
	@echo "\nready. next: make data && make index"

data: ## Download the real e-CALLISTO cache (~139 MB, needs network, once)
	$(PY) scripts/fetch_real_data.py

index: ## Characterise every cached window and write the scenario index
	$(PY) scripts/build_index.py

test: ## Full test suite
	$(VENV)/bin/pytest

test-fast: ## Skip the property-based and slow tests
	$(VENV)/bin/pytest -m "not slow" -x -q --ignore=tests/test_properties.py

lint: ## ruff check + format check
	$(VENV)/bin/ruff check .
	$(VENV)/bin/ruff format --check .

fmt: ## Apply ruff fixes and formatting
	$(VENV)/bin/ruff check --fix .
	$(VENV)/bin/ruff format .

typecheck: ## mypy over the package
	$(VENV)/bin/mypy aamsx

verify-docs: ## Diff every published number in docs/ against reports/out/*.json
	$(PY) scripts/verify_docs.py

api: ## Serve the API with reload on :$(PORT)
	$(VENV)/bin/uvicorn aamsx.api.app:create_app --factory --reload --port $(PORT)

# ---- experiments ------------------------------------------------------------
# These execute real episodes. Nothing in reports/ is written by hand.

benchmark: ## Run the arena protocol over every preset (SEEDS=$(SEEDS))
	$(PY) scripts/run_benchmark.py --seeds $(SEEDS)

ablation: ## Run the ablation ladder (SEEDS=$(SEEDS))
	$(PY) scripts/run_benchmark.py --ablation --seeds $(SEEDS)

tune: ## Re-tune MAG-NTS weights on the training split only
	$(PY) scripts/tune_mag_nts.py --trials 48 --seeds 3

sensitivity: ## Sweep the reward weights and report how the ranking moves
	$(PY) scripts/sensitivity.py

report: ## Render an HTML report from the most recent stored experiments
	$(PY) -m aamsx.cli report --latest 6

head-to-head: ## Re-run the arena with thompson as the control (writes benchmark_thompson.json)
	$(PY) scripts/run_benchmark.py --seeds $(SEEDS) --baseline thompson

# ---- frontend ---------------------------------------------------------------

web-install: ## npm ci in web/
	cd web && npm ci

web: ## Vite dev server on :5173
	cd web && npm run dev

web-build: ## Production bundle into web/dist
	cd web && npm run build

# ---- containers -------------------------------------------------------------

docker: ## Build both images
	docker compose build

docker-up: ## Start api + web (ui on :5173)
	docker compose up -d

docker-down: ## Stop the stack
	docker compose down

# ---- housekeeping -----------------------------------------------------------

clean: ## Remove caches and build artefacts (keeps data/ and reports/)
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache .mypy_cache build dist *.egg-info
	rm -rf web/dist web/node_modules/.vite

clean-index: ## Delete the window index only (cheap to rebuild, keeps recordings)
	rm -f data/index/windows.parquet

all: setup data index test ## Full first-run: install, fetch, index, test
