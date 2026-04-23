.PHONY: all venv run test test-only clean

all: venv

venv: .venv/bin/python
.venv/bin/python:
	python3 -m venv .venv
	.venv/bin/pip install -e .

run: venv
	.venv/bin/python julius.py

test: venv
	.venv/bin/python -m tests.qa

test-only: venv
	.venv/bin/python -m tests.qa $(PAT)

perf: venv
	.venv/bin/python -m tests.perf

clean:
	rm -rf .venv *.egg-info julius_tui/__pycache__ tests/__pycache__
