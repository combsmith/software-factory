# NNNN. A module of the Kernel's is called only at its functions, and the Kernel raises nothing and names no special name

Status: accepted. The Factory Builder's story of 2026-11-07, issue 593, "check_purity: further ways a Kernel function could call a value it is handed". It closes the plainly written ways the reads of decision 0152 found for the Kernel to call a value it is handed, narrows what 0152 let the Kernel call through a module or hand to be called, and names what the check leaves to the review Role.

## Decision

| What | Decided | Because |
|---|---|---|
| A module's attribute | A call of a module of the Kernel's is of a function it defines or imports, followed as decision 0152 follows one. A module's value, and a name it does not bind, are refused, called through the module or handed to be called | `terms.LIMIT()` passed, and so did `terms.apply(fetch, xs)`, which called what the module's `__getattr__` returned |
| An imported name handed to be called | What is handed as `key=`, or as `map`'s or `filter`'s first argument, by a name it imports, is a function of the Kernel's. An imported constant, or a name from `__future__`, is refused | `sorted(xs, key=LIMIT)` passed when `LIMIT` was imported |
| A builtin handed to be called | `map`, `filter` and `type`, in `UNHANDED_BUILTINS`, are never handed to be called. `type` is called with one argument written out, never a spread | `map(map, [fetch], [xs])` calls `fetch` unread, and `type` with three arguments, `type(*parts)` among them, makes a class and calls its bases' code |
| What a top-level function's definition binds | A name its defaults, annotations or decorators bind is read as the module's, as for a function inside another | `def bind(x=frozenset((safe := map,))):` bound `safe` where the check did not read it |
| `raise` | Refused in the Kernel | It calls what it raises when that is a class, and the Kernel raises nothing on `main`: what it cannot read is a deferral or a Hold |
| A special name | A name written `__x__` is refused in the Kernel wherever its syntax tree holds one but in a constant: an attribute, a name, a definition, a parameter, a keyword, an import, a pattern or a handler. `from __future__ import` stays | `__dict__` rewrites a module's names, whether read as an attribute or imported. A module's or a package's `__getattr__` hands back what no module binds, in place of the module the check reads. The Kernel names none on `main` |
| A package and the modules in it | A module beside a package of the same name is refused, and so is a package that binds a name that also names a module in it, unless it binds that module | Python imports the package, and its `from` import takes the package's binding. In either case the check would read another module than Python runs |
| A default for `_decision` | One that is not a constant is already refused, as state kept between calls, and a constant cannot be called | Argon's read of 0152 asked; a test now holds it |
| Code outside `kernel/` that fills `_decision` | Not held by this check | The check reads the Kernel. Code outside it, a port or the harness, may read the world in its own right and is held by its own directory's rules. On `main`, nothing outside `kernel/` calls a function that takes `_decision` |
| Deliberate evasion: code written to hide a call from the check through Python's own workings, beyond what this record and 0152 refuse | Not held by the check | The check guards the Kernel against plainly written mistakes, from its syntax tree. The review Role reads every change to the Kernel, and `kernel/brakes.py`, `kernel/gate.py` and `kernel/coverage.py` are protected paths |
| A method on the list called on a value not of a built-in type, and a handed value's special methods | Still not held, as decision 0152 says | The facts are JSON, which holds no such value |
| A name a comprehension binds, read as its scope's | Kept | It is stricter than Python, which scopes it to the comprehension, and it is how 0152 reads a function's body. A name that shadows another is renamed |

## Why

The issue listed the ways the reads of decision 0152 found, none used on `main`. A module's attribute was taken on trust whatever it named. An imported name was handed to be called unread. A builtin that calls what it is given could itself be handed. A top-level function's defaults bound names the check did not read. A package could be read as a module Python never imports. Each is a plain slip a new Kernel module could make, and the check now refuses it. The reads of this change found that `type(*parts)`, an imported `__dict__`, a package's `__getattr__` and a pattern's `__class__` passed. Refusing every special name the syntax tree holds closes the last three, and the Kernel uses none. What remains needs the code to be written against the check, and that is the review Role's to read.

## Boundaries

| Boundary | Check |
|---|---|
| A top-level function's default, annotation or return binds in the module. `map`, `filter` and `type` are not handed to be called, and `type` takes one argument written out. `raise` and a special name are refused. A default for `_decision` that is not a constant is refused | `tests/test_tools.py::test_the_kernel_calls_nothing_it_is_given` |
| A module's value, a name it lacks, or what its `__getattr__` returns is neither called through it nor handed to be called. An imported name handed to be called is a Kernel function. `__dict__` is refused, read or imported | `tests/test_tools.py::test_a_module_is_called_into_only_at_its_functions` |
| A module beside a package of its name, a package's binding of a name that names a module in it, and a package's `__getattr__` are refused. A package that binds its own module passes | `tests/test_tools.py::test_a_package_is_read_as_python_imports_it` |
| A caller's `_decision` that it binds is not its own, and a lambda at a module's top takes no `_decision` | `tests/test_tools.py::test_what_fills_a_decision_maker_is_a_kernel_function` |
| Each of these rules has a mutant that a test kills | `tools/mutants.py` |
