.PHONY: ci eval schemas test

ci:
	bash scripts/ci_local.sh

eval:
	.venv/bin/python scripts/run_eval.py evidence/eval/latest

test:
	.venv/bin/pytest -q

schemas:
	.venv/bin/python scripts/gen_schemas.py
