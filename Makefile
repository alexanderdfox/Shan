.PHONY: venv bootstrap serve test check

PY := .venv/bin/python

venv bootstrap:
	./scripts/bootstrap-venv.sh

serve: venv
	$(PY) -m shan serve

test: venv
	$(PY) -m pytest tests/ -q

check: venv
	$(PY) -m shan check examples/hello.shan
