PY ?= python3

.PHONY: verify fast
verify:
	$(PY) -m tools.verify

fast:
	$(PY) -m tools.verify --fast
