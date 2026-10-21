# 0043. A scheduled tick is a backstop of hours; the relay carries W-2, and a pass records what started it

Status: accepted. Taken as a working ruling on 2026-10-21 for "Design: a scheduled tick is a backstop of hours, not minutes (P-8 ticks failed)" (issue 246), which the Maintainer may overturn in review. The Maintainer accepted, the same day, that W-2 is not met while the relay is down. It adds to `docs/decisions/0011-the-poller-and-the-view-are-measured.md`, whose thresholds it reads, and to decision 0036, whose next pass it starts.

## Decision

| What | Decided | Because |
|---|---|---|
| The schedule | A backstop of hours, not minutes. In this repo, over one day, 19 of 335 due ticks arrived, the gap between runs was 287 minutes at the 95th percentile, and the first run came four hours after the workflow landed (`trials/P-8.ticks.json`). More schedule lines are the same scheduler more times: three lines five minutes apart gave those figures | Design section 7.3 assumed about 60% of ticks dropped; the measurement is 94% |
| W-2 while the relay is down | Not met, and accepted. A change that produces no event is decided at the schedule's latency, about five hours at the 95th percentile, and correctness never depends on it (W-1). What bounds it is that the outage is itself reported within fifteen minutes, so those hours are hours a person knows about. Option 3, the looping job, is not pursued | No carrier the design has meets W-2 without the relay. The looping job would hold a runner slot for the length of every outage, on terms GitHub has not answered, for an outage the relay's host makes rare. W-2 was always the relay's (decision 0011) |
| A broken chain | Restarts on a tick, on the relay's nudge, and, from the first day and with the relay down too, on the Factory's own repo's `workflow_run` completion events, which its own workflow turns into a nudge. While any Run is in flight a broken chain restarts at that Run's end; only one broken with no Run in flight waits for the schedule | Every Run's workflow ends in an event in the Factory's repo. With ticks hours apart, "due sooner than the next tick" is nearly always, so a chain runs while anything is due and ends when nothing is, as decision 0036 and W-7 want |
| The not-run alert | Set from the relay's cadence. No pass the relay started for fifteen minutes, W-2's figure, raises one alert for one cause (L-48), held until a pass the relay started is recorded again. No pass at all for five hours is the same alert, held, with a second cause named: the schedule's own failure, which is the whole poller's. Until the relay runs, in slice 3, only the second can be read | Set from the schedule's 287 minutes, an outage would go unseen for hours; set from its nominal five, the alert would fire all day |
| What a pass records of its start | `started_by` in `pass/1`, required, a code: `schedule`, `relay`, `own_repo`, `successor` or `dispatch`, the Maintainer's hand. The poller reads it from the event that started its run and, for a dispatch, from the identity that dispatched it, never from anything the dispatch carries | The alert and decision 0011's thresholds are computed from the records. Without the start, a pass the schedule started after five hours looks like one the relay started |
| The critical path | The relay's two trials come in slice 1, before a Release on `next` can meet W-2: P-20, the public event, first of its batch, and P-31, the relay's host, a story of its own. The relay itself stays in slice 3, and slice 0's exit does not change | W-2 rests on the relay alone. The first approval does not need W-2: the Factory's own repo's events start its passes |

## Why

Trial P-8's ticks part failed on 2026-10-20, and section 7.3 leaned on the schedule in three places: as the fallback when the relay is down, as what restarts a broken chain, and, by implication, as what the not-run alert is set from. Nothing built depends on the schedule yet, since the poller, the relay and the nudges are all slice 1 or later, so this is the time to say what each now rests on. The pass record is where the Controller's health is read from, so what started each pass is recorded there as a code, as everything in a pass record is.

## Boundaries

| Boundary | Check |
|---|---|
| A pass records what started it as one of five codes, never a sentence | `tools/check_examples.py`, `examples/invalid/pass.a-start-in-words.json` |
| A scheduled tick can be lost, as the tick probe recorded, and the schedule alone does not carry W-2 | `tests/test_tools.py::test_the_tick_probes_intervals_are_held_to_its_runs` |
| A broken chain restarts on the Factory's own repo's `workflow_run` events, the relay's nudge or a tick | waiting on `controller/` |
| The not-run alert fires once after fifteen minutes with no pass the relay started, holds until one is recorded, and names a second cause after five hours with no pass at all | waiting on `controller/` |
