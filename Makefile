PY ?= python3

.PHONY: verify fast checks
verify:
	$(PY) -m tools.verify

fast:
	$(PY) -m tools.verify --fast

checks:
	$(PY) -m tools.verify --checks

# The Makefile is read as committed: an explicit rule with an empty recipe stops make remaking it by an implicit rule
# from a file beside it, Makefile.sh among them, before verify is looked up (decision 0240). It comes after verify,
# which stays the goal of a bare make.
Makefile: ;
