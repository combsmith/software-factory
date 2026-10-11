# kernel/

Every decision the Factory makes lives here, as pure functions.

- **No I/O.** No file, socket, process, environment variable or clock. Time is an argument.
  Enforced by `tools/check_purity.py`: only `__future__`, `typing` and `kernel` may be imported.
- **Facts in, decision out.** Plain dictionaries and lists, already validated against `schemas/`.
- **No text from outside.** No function here takes a comment body or a title.
- **Codes, not sentences.** A reason is a code from `terms.py`; people read a rendering of it.
- **Fail to a deferral or a Hold.** An unreadable fact never yields `admit` or `act`.
- **State is derived.** `derive.py` is the only definition of a pull request's State.

Adding a rule: add the boundary case to `tests/test_decide.py` first, then the code, then run
`make verify`.
