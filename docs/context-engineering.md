# Context engineering

Why the files an author reads here are shaped as they are. Each practice below was taken from
published guidance, and each is held by a check. Guidance that would need a rule no check can
hold is listed at the end, and is not a rule here.

Sources were read on 2026-10-11. "Measured" means the source reports data; the rest is a vendor's
or a practitioner's advice.

## Adopted

| Practice here | Why | Held by |
|---|---|---|
| The root `AGENTS.md` is at most 60 lines, and each directory's at most 40. That leaves room for commands, rules and pointers, and none for describing the code file by file | Anthropic's guidance is under 200 lines for a file loaded every session, and says a longer one is followed less well [1]. One practitioner's own root file is under 60 [2]. Measured: recall falls as input grows, on 18 models [3], and adherence falls as instructions are added [4]. Measured: across 438 tasks, context files gave no general gain in success and raised cost by over 20%, and overviews did not help agents find files sooner, though agents did follow what the files said [5]. So only what cannot be found by reading the code earns a line [6] | `tests/test_tools.py::test_a_root_file_too_long_to_read_in_full_is_caught` |
| The root file points to each document by the task that needs it | Measured, in one vendor's evals: a compact index that is always loaded reached 100%, while material loaded on demand was never opened in 56% of cases [7]. On-demand is not reliable without a pointer | `tests/test_tools.py::test_a_path_or_a_test_that_does_not_exist_is_caught` |
| Each directory has its own `AGENTS.md`, with the rules of that place only | The nearest file to the code being edited takes precedence in the open format and in the tools that read it [8] [9] [1]. No study has measured nested files against one root file | `tests/test_tools.py::test_a_directory_with_no_rules_of_its_own_is_caught` |
| Every rule names the check that holds it | An instruction is a request; a hook, a linter or a required check is enforcement [10] [11]. A rule an agent follows anyway should become a check or be deleted [6] | `tests/test_tools.py::test_a_rule_in_any_agents_file_must_name_its_check` |
| A standard shows an example before it states the rule, and the example is real | Curated examples carry more than a list of edge cases [12] [13]. Pasted snippets go stale, so point at the real file [2]: here a named path must exist, and the workflow example is compared with the file word for word | `tests/test_tools.py::test_a_standard_with_prose_and_no_example_is_caught`, `tests/test_tools.py::test_an_example_in_the_standard_that_has_drifted_is_caught` |
| The exact commands that verify are at the top, and each module they name exists | Agents run the commands a file lists and fix what fails [8] [13] | `tools/check_context.py` |
| One set of rules for every tool: `CLAUDE.md` holds one line that imports `AGENTS.md` | Two sets of instructions that disagree are resolved arbitrarily [1] | `tests/test_tools.py::test_a_date_in_what_is_always_read_is_caught` |
| What is read on every task holds no date and nothing that changes with the day | A stable prefix keeps the model's cache; one changed token invalidates what follows it [14] | `tests/test_tools.py::test_a_date_in_what_is_always_read_is_caught` |
| A procedure done rarely and exactly is a skill, `.claude/skills/<name>/SKILL.md`, opening with the name and description it is found by; the root file points to each | A skill costs nothing until a task calls for it, but on-demand loading alone was measured as unreliable [7], so a pointer is always loaded | `tests/test_tools.py::test_a_skill_the_root_file_does_not_point_to_is_caught` |
| Decisions are one small file each, numbered with no gap; a change is a new record, not a rewrite | Measured: rewriting a memory in full erodes its detail, and small additions do better [15] | `tests/test_tools.py::test_a_decision_with_no_boundary_is_caught` |
| A change to these files is judged by a task, not by reading: a fresh agent, given the repo and one sentence, adds a rule to the Kernel and passes both commands | Context meant to improve results should be evaluated before it is relied on [5]; start from tasks with a known answer and run them more than once [16] | `tests/test_evals.py::test_a_fresh_agent_given_the_repo_adds_a_rule_and_passes_the_check`, not held yet |

## Considered and not made a rule

No check can hold these, so they are advice for whoever runs a session, and nothing in this repo
depends on them.

- **Write these files by hand.** Generated context files measured slightly worse than none [5].
- **Count instructions, not only lines.** The line limit stands in for it [4].
- **Give exploration and review to a fresh context that returns a short summary** [12] [17], and
  do not split one change across parallel agents [18].
- **Start a new session for a new task,** and hand over through a file in the repo [19].

## Sources

1. Anthropic, Claude Code documentation, "How Claude remembers your project". https://code.claude.com/docs/en/memory
2. HumanLayer, "Writing a good CLAUDE.md", 2025. https://www.humanlayer.dev/blog/writing-a-good-claude-md
3. Hong, Troynikov and Huber, "Context Rot", Chroma, 2025. https://www.trychroma.com/research/context-rot
4. Jaroslawicz and others, "How Many Instructions Can LLMs Follow at Once?", 2025. https://arxiv.org/abs/2507.11538
5. Gloaguen and others, "Evaluating AGENTS.md", 2026. https://arxiv.org/abs/2602.11988
6. Anthropic, Claude Code documentation, "Best practices". https://code.claude.com/docs/en/best-practices
7. Vercel, "AGENTS.md outperforms skills in our agent evals", 2026. https://vercel.com/blog/agents-md-outperforms-skills-in-our-agent-evals
8. The AGENTS.md format. https://agents.md/
9. OpenAI, Codex documentation, "AGENTS.md". https://learn.chatgpt.com/docs/agent-configuration/agents-md
10. Anthropic, Claude Code documentation, "Hooks guide". https://code.claude.com/docs/en/hooks-guide
11. Böckeler, "Harness engineering", martinfowler.com, 2026. https://martinfowler.com/articles/exploring-gen-ai/harness-engineering.html
12. Anthropic, "Effective context engineering for AI agents", 2025. https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
13. GitHub, "How to write a great agents.md: lessons from over 2,500 repositories", 2025. https://github.blog/ai-and-ml/github-copilot/how-to-write-a-great-agents-md-lessons-from-over-2500-repositories/
14. Manus, "Context Engineering for AI Agents: Lessons from Building Manus", 2025. https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus
15. Zhang and others, "Agentic Context Engineering", 2025. https://arxiv.org/abs/2510.04618
16. Anthropic, "Demystifying evals for AI agents", 2026. https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
17. Anthropic, Claude Code documentation, "Subagents". https://code.claude.com/docs/en/sub-agents
18. Cognition, "Don't Build Multi-Agents", 2025. https://cognition.com/blog/dont-build-multi-agents
19. Anthropic, "Effective harnesses for long-running agents", 2025. https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents

The sources disagree in places. Vendors recommend context files; the one large measurement found
no gain in success from a typical one, and a second found runs faster and cheaper without checking
that they were correct. Both are consistent with a file that is small and holds only commands and
rules, which is the reading taken here. No size limit in any source is derived from a published
measurement.
