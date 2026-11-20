PY ?= python3

# The Makefile is read as committed: an explicit rule with no recipe stops make remaking it by an implicit rule from
# a file beside it, Makefile.sh among them, before verify is looked up (decision 0240).
Makefile: ;

.PHONY: verify fast checks
verify:
	$(PY) -m tools.verify

fast:
	$(PY) -m tools.verify --fast

checks:
	$(PY) -m tools.verify --checks
