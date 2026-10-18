# Glossary

The terms are those of the product requirements: section 4, "Glossary", of
`docs/prd/agentic-software-factory.md`. A term is written with a capital and means one thing. Do
not coin a second word for any of them, and do not copy that list here.

This page holds only the words this repo uses that the requirements do not define.

| Term | Meaning |
|---|---|
| Facts | What GitHub holds about one Work item, read in one pass, with a flag for each list that was read in full. `schemas/facts.schema.json` |
| Run record | GitHub's record that a Run happened and how it ended. `schemas/run-record.schema.json` |
| Act | A change the Kernel decides with no model: an approval, an enqueue, a dequeue, or a label the Controller adds. The approval is made by a Run with no Engine. One that does not land is bounded by its attempts, and by the Run ceiling whatever its fault. Every act that lands is counted from GitHub's timeline, read in full, as `acts_since_writer`, against `max_acts_per_item`. An act that stops work is counted and never refused |
| Decision | What the Kernel concluded for one Work item in one pass: State, reason, outcome. `schemas/decision.schema.json` |
| Class | Who a Work item comes from: `agent`, `maintainer`, `dependency` (opened by a dependency bot; a dependency update while that bot pushed its head itself) or `outside` (a fork, or someone who is not a collaborator). Worked out once, when the facts are read |
| Gating | A Finding gates when it sends the Work item back to its author. That is not a Hold, which stops the item until a person acts |
| Rubric | The criteria a reviewing Role must report on, as data. `schemas/rubric.schema.json` |
| Coverage | What a reviewing Result says of each criterion of its rubric that applies: `met`, a Finding that cites it, or `not_applicable` with a reason code. A Result that leaves one uncovered is refused, and its Run fails by a fault of the item. `schemas/coverage.schema.json`, `kernel/coverage.py` |
| Acceptance contract | The criteria a change is judged against, written before the work by a Role other than the one that does it. `schemas/acceptance.schema.json` |
| Boundary case | One input at the edge of a Kernel rule, with the Decision it must give. A test in `tests/test_decide.py` |
| Mutant | A Kernel rule broken on purpose, which some test must notice. An entry in `tools/mutants.py` |
| Trial | One question from section 6 of the design, put once to the real GitHub in the canary repo, combsmith/software-factory-canary. Run by the skill `.claude/skills/run-a-platform-trial/SKILL.md` |
| Fixture | What one trial sent and what GitHub answered, with every credential removed, and its verdict. A file in `trials/`, whose form is `schemas/trial.schema.json` |
| Unverified | Said of a rule the simulator's fake GitHub applies that no fixture grounds yet. `sim/grounding.py` lists every rule; `make verify` prints each that is unverified |
