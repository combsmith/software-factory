# Glossary

The terms are those of the product requirements: section 4, "Glossary", of
`docs/prd/agentic-software-factory.md`. A term is written with a capital and means one thing. Do
not coin a second word for any of them, and do not copy that list here.

This page holds only the words this repo uses that the requirements do not define.

| Term | Meaning |
|---|---|
| Facts | What GitHub holds about one Work item, read in one pass, with a flag for each list that was read in full. `schemas/facts.schema.json` |
| Run record | GitHub's record that a Run happened and how it ended. `schemas/run-record.schema.json` |
| Decision | What the Kernel concluded for one Work item in one pass: State, reason, outcome. `schemas/decision.schema.json` |
| Class | Who a Work item comes from: `agent`, `maintainer`, `dependency` (an automated dependency update) or `outside` (a fork, or someone who is not a collaborator). Worked out once, when the facts are read |
| Gating | A Finding gates when it sends the Work item back to its author. That is not a Hold, which stops the item until a person acts |
| Rubric | The criteria a reviewing Role must report on, as data. `schemas/rubric.schema.json` |
| Acceptance contract | The criteria a change is judged against, written before the work by a Role other than the one that does it. `schemas/acceptance.schema.json` |
| Boundary case | One input at the edge of a Kernel rule, with the Decision it must give. A test in `tests/test_decide.py` |
| Mutant | A Kernel rule broken on purpose, which some test must notice. An entry in `tools/mutants.py` |
