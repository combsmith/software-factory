PY ?= python3

.PHONY: verify fast checks
verify:
	$(PY) -m tools.verify

fast:
	$(PY) -m tools.verify --fast

checks:
	$(PY) -m tools.verify --checks
