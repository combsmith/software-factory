PY ?= python3

.PHONY: verify
verify:
	$(PY) -m tools.verify
