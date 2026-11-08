# NNNN. The writes check holds four more routes: a namespace package, sys's modules, a class's attribute set from outside, and gh or git run from Python

Status: accepted. The Factory Builder's story of 2026-11-08, issue 596, "check_writes: further ways a write could be reached past the check, written to hide it", raised by the reads of issue 587, "Only the write steps call a write: a check that keeps GitHub writes to an allowlist of callers". It amends decision 0153's rows "Not held here: code written to hide a write" and "Not held here: `gh` run from Python".

## Decision

| What | Decided | Because |
|---|---|---|
| A namespace package | `tools/check_writes.py` reads a folder of modules with no package module of its own as the package Python imports it as. A dotted `import adapters.effects`, with no `adapters/__init__.py`, is a module of the repo, and what it names is read | Before, such an import was read as no module of the repo's, and what it reached was not read at all |
| sys's modules | A module that reads `sys.modules`, or imports `modules` from `sys`, is refused as one that loads a module by its name, unless NAME_LOADERS names it | A module taken from `sys.modules` by its name is one the syntax cannot follow, as `importlib` is |
| A class's attribute | An attribute set by `setattr` is refused. So is an attribute set on a class, to anything but text, from a function or from another module than the class's. A class's own body, and its module's top level, still fill it as before | A caller that names the class reaches what its own module gives it, and nothing set on it from elsewhere. A text constant set from a function reaches nothing, as `tools/trial_p50_stub.py` sets one |
| gh or git run from Python | A string that is `gh` or `git` alone, or opens a command line with either, is refused outside the Python RUNNERS names: ten files that run git to read or read a command they are given. A new one is the Maintainer's to allow, as a new caller is (decision 0153) | Run from Python, either may write to GitHub by no request of `adapters/github.py`'s, and holds no write verb as a whole string |
| Still not held | Code written to hide a write in ways the syntax cannot follow, such as a command's name built from parts, stays the review's to see, as decision 0153 says | The check is a net for code written plainly |

## Why

The reads of decision 0153's change found four routes past the check, each taken only by code written to hide a write. On the Factory Builder's ruling they were filed rather than held in that change. Each is a pattern the syntax can name, so the check names it: none is used on main but by the ten RUNNERS, which read.

## Boundaries

| Boundary | Check |
|---|---|
| With no `adapters/__init__.py`, a dotted import of an adapter reaches what it writes | `tests/test_tools.py::test_a_namespace_package_is_read_as_one`, `tools/check_writes.py`, mutant: "a namespace package is no module of the repo's", mutant: "a namespace package's module is not read" |
| `sys.modules`, read or imported, is refused; so are `setattr` and an attribute set on a class from a function or another module; and gh or git as a command outside RUNNERS | `tests/test_tools.py::test_what_cannot_be_read_fails`, `tools/check_writes.py`, mutant: "sys's modules are read", mutant: "sys's modules imported by name are read", mutant: "setattr may set an attribute", mutant: "a class's attribute may be set from another module", mutant: "a class's attribute may be set from a function", mutant: "gh or git may be run from Python", mutant: "a command line is read only as its program alone" |
| On main, a text constant set on a class from a function, and the RUNNERS' own gh and git, pass | `tests/test_tools.py::test_on_main_only_the_callers_listed_reach_a_write_and_each_what_it_lists`, `tools/check_writes.py`, mutant: "a text constant set on a class from a function is refused", mutant: "a runner's own gh or git is refused" |
