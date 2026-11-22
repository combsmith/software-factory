# Decision records

Made by `python3 -m tools.records` from the records in `docs/decisions/` alone: change a record, never this page.
A record is live until a later one replaces it. Its area is the top directories its Boundaries name, but `tests/`.

| Record | Title | Status | Area |
|---|---|---|---|
| 0001 | One repo, and a Kernel that does no I/O | live | adapters, tools |
| 0002 | State is derived and never stored | live | .github, examples, tools |
| 0003 | One Controller admits every Run, from current facts | live | adapters, controller, examples, kernel, schemas, tools |
| 0004 | One run contract; a job is a credential boundary | live | adapters, config, controller, examples, harness, release, tools |
| 0005 | Each Role writes through its own App; the machine user only approves | live | adapters, examples, harness, sim, tools |
| 0006 | One Release, one path | live | examples, release, tools |
| 0007 | An approval is bound to content | live | examples, harness |
| 0008 | Verification binds | live | examples, tools |
| 0009 | One fact, one place | live | roles, tools |
| 0010 | Built greenfield, cut over one repo and one Intent family at a time | live | examples, release, tools |
| 0011 | The poller and the view are measured | live | adapters, controller, tools |
| 0012 | Every Lens reports Findings in one schema; the Kernel decides Convergence | replaced by 0015 | adapters, examples, schemas, tools |
| 0013 | The context authors build from is part of the product | live | tools |
| 0014 | Where this repo departs from the org's standards | live | examples |
| 0015 | A Lens is read from its own App, and only what gates holds a merge | replaced by 0018 | adapters, examples, harness, schemas, tools |
| 0016 | What the session hooks decide without reading | replaced by 0017 |  |
| 0017 | The session hooks read every commit a push sends | live |  |
| 0018 | A Lens is read from its own App and its own workflow file, and only what gates holds a merge | replaced by 0022 | adapters, examples, harness, schemas, sim, tools |
| 0019 | Under bypassPermissions, the protected hook tells and asks nothing | live |  |
| 0020 | A change to the Factory's own rules or a Lens's inputs is reviewed by a model Lens | live | adapters, examples, harness |
| 0021 | Only the Maintainer starts a session with no one asked | live |  |
| 0022 | A Lens is read from its own App and workflow, its job judges every job it waits on, and only what gates holds a merge | replaced by 0026 | adapters, examples, harness, schemas, sim, tools |
| 0023 | A Lens's verdict and the secret scan's rules run from the base | live |  |
| 0024 | The identity hook reads where a push goes from git's configuration, and refuses a git the command may redefine | live | tools |
| 0025 | Acceptance is read from its reporter, against the contract a person approved | live | adapters, examples, harness, sim, tools |
| 0026 | A Lens is read from its own App and workflow, its job judges every job it waits on, and only what gates holds a merge | live | adapters, examples, harness, schemas, sim, tools |
| 0027 | A mutant is killed by a test that fails on it twice and passes without it | live | tools |
| 0028 | An issue's State is derived in a module of its own | replaced by 0139 | adapters, examples, kernel, sim, trials |
| 0029 | A reviewing Run that leaves a criterion uncovered has not reported | replaced by 0049 | examples, schemas, tools |
| 0030 | The identity hook refuses a write into git's directory, and a git an alias or a feeder hides | live | tools |
| 0031 | What is admitted on an issue, and when apply refuses | live | examples |
| 0032 | The identity hook reads a write where and when the shell makes it | live | tools |
| 0033 | The Factory's model credential is, for now, the Maintainer's own subscription; a trial of a vendor's CLI records no repo | live | examples, tools |
| 0034 | An issue goes stale as a pull request does | live | examples |
| 0035 | An App's grants are read from GitHub and the data is held to them; each key lives in the environment of the one job that holds it | live | examples, tools |
| 0036 | A Run listed before its name is unidentified, and defers every admission | live | .github, tools |
| 0037 | An issue's ceilings are asked about the Run it wants | live |  |
| 0038 | A Result asks and names no one, and `apply` writes the Finding it posted | live | adapters, applied, controller, examples, harness, tools |
| 0039 | One envelope, on what crosses a boundary whole | live | .github, examples |
| 0040 | The identity hook reads where the shell may stand, and a program it does not read may write | live | tools |
| 0041 | Identity is held by the required check that reads each commit, and the session hook guards mistakes | live | tools |
| 0042 | The context is tested by a task run outside CI, and the runs are held as a fixture | replaced by 0129 | tools |
| 0043 | A scheduled tick is a backstop of hours; the relay carries W-2, and a pass records what started it | live | .github, controller, examples, tools |
| 0044 | The ports are the one place that reaches the network, through one transport held to GitHub's API | live |  |
| 0045 | The transport follows one redirect: an artifact's download, to GitHub's artifact storage alone | replaced by 0138 | adapters, trials |
| 0046 | A change to a model Lens's own inputs needs a person | replaced by 0052 | adapters, tools |
| 0047 | An issue asks for an acceptance contract only by an Intent that asks, or a person's `factory:contract` label | live | adapters |
| 0048 | A person's write access is read from the collaborator permission, never from an association | live | tools |
| 0049 | A reviewing Run that leaves a criterion uncovered has not reported, and one that ran and left no outcome is an attempt | live | examples, kernel, schemas, sim, tools |
| 0050 | The model is given a Task and no tool, and apply writes only what it reads back | replaced by 0138 | examples, tools |
| 0051 | The Controller's writes go through one credential each, held to what it may send, and every one is recorded | live | examples |
| 0052 | A change to a model Lens's own inputs needs a different person's approval | live | adapters, tools |
| 0053 | The eval job reads the held-out home with the Maintainer's token, and reports hashes, verdicts and codes alone | live | tools |
| 0054 | `apply` writes a Role's Effects with a token narrowed to them, and claims only what it reads back | live | tools |
| 0055 | The approving act holds the machine user's token alone, approves the commit it re-read, and says whose fault each failure was | live | .github, examples, tools |
| 0056 | A dispatch waits on the Pause read again outside the Kernel, and one tracking issue reports the Factory's faults | live |  |
| 0057 | A shim calls the Release and holds nothing else, and the poller wakes on a workflow's end and reads nothing of it | live | .github, examples, tools |
| 0058 | A Run holds its item's lane from run to apply, and starts only from the pass's own token while nothing is Paused | live | examples |
| 0059 | A Role's manifest is held to the authority table and its App's ceiling | live | examples, roles, tools |
| 0060 | The pass's entry reads through the ports with a token of reads alone, and the last two pass records under a bound of their own | live |  |
| 0061 | Every write a Factory identity makes is matched to a recorded Effect, and one that is not raises one alert | live | tools |
| 0062 | A review whose rubric cannot be read is never asked, and a manifest is held to its shape before its fields | live | tools |
| 0063 | Reconciliation reads what left the open list, reads a dispatch by its run's making, and leaves short what it cannot tell | live | .github, controller, tools |
| 0064 | A Run's steps each read with their own credential and revoke it, and every Run leaves its outcome | live | adapters |
| 0065 | A review is given the whole diff or is not asked, and the Kernel holds the bound | live | tools |
| 0066 | The pass, the Run's three jobs and the approving act are held word for word, and each runs one Release | live |  |
| 0067 | A thread's resolver is told by its account, never by resolvedBy's type | live | tools |
| 0068 | A pull request the Factory opens is bound to its issue by its branch, never its body | live | adapters, tools |
| 0069 | What a Lens recorded holds its threads, and gives each its category | live | tools |
| 0070 | A Role's push that touches the base's list is refused | replaced by 0188 | adapters, harness, tools |
| 0071 | A Release is cut from main through the eval gate and never moved, and next is rolled back with no gate | replaced by 0120 | release, tools |
| 0072 | A rename's two names are read from the compare the port reads, and one shape carries them | live | tools |
| 0073 | The release step reads its facts and the eval gate through the release App's token, writes each tag and reads it back | live | tools |
| 0074 | A rule names only a trial whose row asks it, and the fake models stale dismissal | live | tools |
| 0075 | A later review by the same Lens supersedes its earlier records for a thread that is gone | live | tools |
| 0076 | One workflow moves next, held to its shape, through the release App's token for this repo alone | live | tools |
| 0077 | The grants of 2026-10-27 are read again by P-39 and mapped, and P-52 shows where the org's Pause can be read | live | tools |
| 0078 | A held-out case is reviewed by the Task and the Engine a live Run is, and its report tells nothing it expected | replaced by 0109 | examples, tools |
| 0079 | The machine user's approval counts only for a pull request open when it was given, and never from before a reopening | live | tools |
| 0080 | A Release's verify is verify.yml's, next is read again before it moves, and one repo in two cases is one | live | tools |
| 0081 | A fixture records a write on a node of the canary, and P-2 names what the queue takes | live | tools |
| 0082 | An App resolves another's thread only with contents: write, and CodeRabbit approves once its thread is resolved | live | tools |
| 0083 | A mutant run's baseline runs the tests its own mutants name, method by method among its workers, and a slow one is not a red one | live | tools |
| 0084 | Thirty thread resolutions in a row meet no secondary limit | live | tools |
| 0085 | The merge queue merges, ejects, refuses a push and a draft; and GitHub approves a closed pull request | live | tools |
| 0086 | A Lens judges, and the queue App resolves its thread as the Kernel's act on its accepted ruling | live | tools |
| 0087 | The commits job holds the name each commit carries, and a forged name is a risk the Maintainer accepts | live |  |
| 0088 | A Finding that cites a criterion has the rubric's severity, or the Result is uncovered | live | tools |
| 0089 | The queue App's acts take contents: write alone, and the merge queue checks a thread only at the enqueue | live | tools |
| 0090 | A label on a pull request takes pull_requests: write, a label on an issue issues: write, the queue App holds the queue's acts, and each App's reach is read after its installation last changed | live | examples, tools |
| 0091 | A job stopped at its timeout concludes cancelled, a step's own timeout fails, and CodeRabbit with auto-approval off does not approve | live | tools |
| 0092 | An external Lens's approval never counts, and no Role resolves another reviewer's thread | live | tools |
| 0093 | A mutant shard's baseline is its share of what every mutant names, and the whole suite runs in dealt parts | live | tools |
| 0094 | The eval job holds a set's split where its cases are, and no count of a kind is public | replaced by 0099 | examples, tools |
| 0095 | A Finding that cites a criterion is of the rubric's category, or the Result is uncovered | live | tools |
| 0096 | A Lens review whose record is past retention on an open pull request is asked for again | live | tools |
| 0097 | A pull request the Factory opens is bound to its issue by the Run that opened it, read from that Run's own record | live | harness, tools |
| 0098 | Each job the Factory writes stops its own work under a step limit, so that a job too long fails and is never cancelled | live | examples, tools |
| 0099 | The eval job holds a set's split where its cases are, since the repo cannot hold the counts true | replaced by 0109 | examples, tools |
| 0100 | An eval case's expected Finding is as its rubric gives it, read at run time, where the case is | replaced by 0120 | tools |
| 0101 | A stored credential's age is read from a table of its dates, and only an expiry brings it due | live | examples, tools |
| 0102 | A pull request is opened from this repo by an account the configuration lists | live | examples, harness, tools |
| 0103 | A check a job creates reads as the first suite's workflow, an upload can turn CodeQL neutral, and the queue's base and a stale dismissal hold | live | tools |
| 0104 | A required Lens's check is read only where its details are its own job's | live | tools |
| 0105 | The facts the held-out set predates are filled in the eval job, and a case that cannot be asked says why by a code | live | examples, tools |
| 0106 | A fault of the Engine is never the reviewer's, the scrub needs bubblewrap, and a check runs the Engine end to end | live | tools |
| 0107 | P-31, the relay's host, is asked before the relay is built, and not before the first approval | live | controller, tools |
| 0108 | The machine user holds write on every repo through an org role on the code owners' team, and is a code owner of every path | live | examples, tools |
| 0109 | The scorer's codes are in the public report and the judge's log | replaced by 0120 | examples, tools |
| 0110 | The review cites the criterion, knows what `met` means, and reads the issue a change serves | live | adapters, examples, tools |
| 0111 | A first attempt an `if:` skipped is no attempt, and a later attempt it skipped is one | live | tools |
| 0112 | A pass gathers what reconciliation reads, and carries what it has read | live | .github, tools |
| 0113 | A fixture may record the Factory's own repo, for the trial named for it alone | live | examples, tools |
| 0114 | The release App is in the data, and alone holds `workflows` | live | tools |
| 0115 | A shim inherits secrets, and a Run's last job wakes the poller | live | examples, tools |
| 0116 | A Run GitHub started no job of counts toward the automatic pause, under its own name | live | tools |
| 0117 | What grades the review stays on model review, and the Maintainer accepts the risk | live | tools |
| 0118 | The status on the item is one neutral check run, edited in place when the Decision changes | live | examples, tools |
| 0119 | Each factory environment's deployment branches are read by hand, and anything but `main` alone is drift | live | tools |
| 0120 | The gate holds a bar of the set and of each kind, and a fault of the Engine or the run still closes it | replaced by 0150 | examples, release, tools |
| 0121 | A CLI that exits 0 with no answer closes the eval, and stays an attempt on its item | live | tools |
| 0122 | A run the model could not finish is an attempt on its item, as the CLI names it | replaced by 0136 | tools |
| 0123 | A called workflow checks out its own commit, not the tag that called it | live | tools |
| 0124 | No branch may stand where a Channel's tag should | live | tools |
| 0125 | An expired Run's open thread asks its Lens's review, and is closed once a later review supersedes it | live | tools |
| 0126 | A created check replaces only an earlier created one of its name, and three of P-42's check rules are grounded | live | tools |
| 0127 | The queue App holds contents: write alone, and each resolution it lands counts as an act | live | tools |
| 0128 | Each queue act is a dispatched Run of the queue workflow, once it is named | live | tools |
| 0129 | The context's task is held by its sentence's sha256, and a run records whether it added a test, a mutant and the code, never what | replaced by 0133 | tools |
| 0130 | The queue step reads the pull request again with the queue App's token, and sends one write | live | harness, tools |
| 0131 | An unanswered eval case says why, by its class, its place and its code | live | examples, tools |
| 0132 | An outsider's merge never makes an issue done | live | tools |
| 0133 | A context run passes only having looked nowhere outside its export, and is judged in a tree of its own | live | tools |
| 0134 | The queue act's job holds the queue App's key, the job's reads and the Pause, word for word | live | tools |
| 0135 | A description edited after the first approval since a person looked holds the item | replaced by 0140 | tools |
| 0136 | The CLI holds a Run to its tier's cost ceiling, and a Run it stops is the item's | live | examples, tools |
| 0137 | The review is given each head line's number, and the bound counts the diff numbered | live | tools |
| 0138 | The review reads the pull request's head, with the read tools alone, held to it by --restricted | replaced by 0147 | examples, tools, trials |
| 0139 | A platform close keeps the State a person set on an issue held or not served | replaced by 0141 | adapters, examples, sim, tools, trials |
| 0140 | The facts port reads a pull request's description edits, and an edit's absence is never read as none | live | tools |
| 0141 | A linked draft's flag is read from its timeline, and no linked draft's label holds an issue at its merge | replaced by 0174 | adapters, examples, kernel, sim, tools, trials |
| 0142 | The live review's head is held to its commit's tree, and an eval case's head is not | live | tools |
| 0143 | An eval case's fault may be rightly placed at more than one place, and each is named blind | live | examples, tools |
| 0144 | A Finding that would hold a clean change fails its case, whatever criterion it cites | live | tools |
| 0145 | A Finding names a place in the change, and is adopted only from an advisory reviewer's thread on the item | live | tools |
| 0146 | A Result's reason is one of the Engine's codes, and a Finding's lines are on a hunk of its file at the head | live | examples, tools |
| 0147 | The Engine runs the pinned model by its full id, at the tier's effort, and keeps an answer only from that model | replaced by 0151 | examples, tools |
| 0148 | `apply` checks every field of a Result that needs no diff before it reads the diff, and a Finding's lines last | live | examples, tools |
| 0149 | A result's check is read as any check, so one a job created is foreign to its reporter | live | tools |
| 0150 | The review Intent's bar is each kind's own, set under the measured recall to guard against regression | live | tools |
| 0151 | The artifact storage is any productionresults account numbered in one to three digits | live | adapters, tools, trials |
| 0152 | The Kernel calls nothing it is given but `_decision`, and what fills `_decision` is a Kernel function | live | tools |
| 0153 | Only the callers a check lists reach a GitHub write, each the writers it lists | live | tools |
| 0154 | A boundary's check names a test, never a file, and a new or changed row names the mutant its test kills | live | tools |
| 0155 | A module of the Kernel's is called only at its functions, and the Kernel raises nothing and names no special name | live | tools |
| 0156 | The review is told, and the eval applies, that a Finding off every hunk refuses the whole Result | live | roles, schemas, tools |
| 0157 | An act's shim is the Run's but for its name and the file it calls | live | .github, examples, tools |
| 0158 | A machine user's approval is measured from the act that read the description, and one nothing anchors holds an edit | replaced by 0168 | kernel, sim |
| 0159 | The poller's shim stands on main, and a paused pass dispatches nothing | live | .github, adapters, tools |
| 0160 | A case that expects a Finding takes one Finding at its place, and one gating Finding away from it | live | harness, schemas, tools |
| 0161 | A Run is given no part of its case's answer, and a head holds no `.git` | live | harness |
| 0162 | The eval report names the model, the prompt and the rubric, and what each case used | live | harness, schemas, tools |
| 0163 | Each case's head is unpacked apart from the set's cases | live | harness |
| 0164 | The eval job reads a named set, and a gate set's report is counts alone, its ledger sealed to the Maintainer's certificates | live | harness, schemas, tools |
| 0165 | The eval scratch is read part by part, and the plan makes the heads folder new | live | harness |
| 0166 | A changed line of Python no test notices is reported for a month before it can fail | live | .github, tools |
| 0167 | The writes check holds four more routes: a namespace package, sys's modules, a class's attribute set from outside, and gh or git run from Python | live | tools |
| 0168 | A machine user's approval is measured from the act that read the description, in the Kernel and the simulator's world alike, and one nothing anchors holds an edit | live | kernel, sim |
| 0169 | A gate set's gate pools every dispatch on the commit, under the set's own bars, and a development set stays the best of several | live | adapters, harness, tools |
| 0170 | A gate set's dispatch asks its preflight first, and a broken one stops it before any of the set's cases is asked | live | harness, schemas, tools |
| 0171 | The writes check reads a name back through what it is given, and holds an object's class, another module's names set from outside, sys and loads reached other ways, code run from text and a command a shell runs; a runner's helper stays the review's | live | tools |
| 0172 | A pull request that moved while a pass read it is deferred once with no alert | live | adapters, controller, schemas |
| 0173 | The eval job's trial records the Factory's own repo beside P-30, and a live read stands for a refusal | live | examples, tools |
| 0174 | Two pull requests linked by hand before an issue's merge leave it held, and its type changes are read whole | replaced by 0237 | kernel |
| 0175 | On a development set the surplus bound is told and fails no case | live | harness |
| 0176 | The release step keeps its own exchanges, held to lists, as a public artifact of its run | live | release, tools |
| 0177 | The writes check reads a name where it is stored, every class and owner it may be, and exec as its own only where a binding always runs | live | tools |
| 0178 | A gate set's split needs no case that expects a blocking Finding | live | harness |
| 0179 | A read GitHub did not answer is named by its stage and the snapshot's part, never by one code for every read | live | adapters, harness |
| 0180 | A gate set holds a floor per criterion, read from each case's expected criterion | live | harness |
| 0181 | A check's App another App's token is not shown reads as null, and is never a Lens's | live | adapters, kernel |
| 0182 | On a pull request the mutant shards decline, and on a merge group each runs in full | live | tools |
| 0183 | A linked pull request's closes and reopenings are read whole, and a rival is read as it stood at the merge | live | kernel, schemas |
| 0184 | Each step's token holds every read its code can reach | live | adapters, controller, harness |
| 0185 | A private replay may switch on four review approaches, each off in the committed configuration | live | harness |
| 0186 | A closing keyword's link is timed by the first pass that saw it, and two links of any kind at an issue's merge keep it held | live | adapters, controller, kernel, tools |
| 0187 | Any fault of a read is named by its stage and the snapshot's part, not a refused read alone | live | adapters, harness |
| 0188 | A Role's push is refused where it touches a protected path or a model Lens's input, read from its bundle before any token is minted | live | adapters, config, examples, harness, schemas, tools |
| 0189 | No author Role is named until its manifest exists | live | config, tools |
| 0190 | A pass that did not succeed and lists no record is read, after a second look | live | adapters, tools |
| 0191 | `main` counts the machine user's approval, from the switch of 2026-11-11 | live | config |
| 0192 | A Pause the port could not read is named by which read it was and why | live | adapters, harness |
| 0193 | When a Run began is read from its jobs, trusted only once a job is in progress or ran, and kept by the pass records | live | adapters, controller, examples, schemas, tools |
| 0194 | The Maintainer's continue or stop is recorded in a file, and a decision counts only in his name | live | examples, release, schemas, tools |
| 0195 | Bubblewrap is fetched over HTTPS from a mirror outside ubuntu.com, by a list of the block's own | live | tools |
| 0196 | The pass asks when a Run began only of the open pull requests' Runs | live | adapters, controller, kernel, tools |
| 0197 | Bubblewrap is fetched from two mirrors of different operators, so one unreachable mirror fails no Run | live | tools |
| 0198 | When the Factory cannot or may not approve, the Maintainer approves by hand as the machine user | live | .claude |
| 0199 | An act's read again of its own item asks when all of that item's Runs began, past the cap | live | adapters, harness, tools |
| 0200 | A path only a person decides is listed apart from a Lens's inputs, and a change to it needs a person's approval | live | config, tools |
| 0201 | A Run's outcome says whether its Engine step started | live | .github, adapters, controller, harness, tools |
| 0202 | A Role's Run that spent no model is counted apart from the Run ceiling | live | config, kernel, lifecycle, tools |
| 0203 | A run stopped before it judged is passed over beside another run of the Lens on the same head | live | adapters, kernel |
| 0204 | A browser's approval is dated at its own time only where a record of the item began before it, by its jobs | live | kernel, sim, tools |
| 0205 | Each lookup of the CLI's install is bounded by glibc, not the update by a timeout, which would lose the index it read | live | tools |
| 0206 | The required check's pull-request run gives way to a newer push's, and a merge group's run is never cancelled | live | tools |
| 0207 | A change that touches only paths a person decides waits under its own code | live | config, controller, examples, kernel, sim |
| 0208 | A gate set's manifest keeps the floored criteria and natural marks main has held for its cases | live | tools |
| 0209 | The transport refuses a path with a dot segment, and Sonar's traversal rule is set aside for its file | live | adapters, tools |
| 0210 | A Run that did not succeed and lists no record is read after a second look, and each port waits by the entry's sleep | live | adapters, controller, tools |
| 0211 | A pull request that left the open set is read for the window, so a write nobody matched keeps its alert | live | adapters, controller, schemas |
| 0212 | A push past a Lens's review asks it again while its thread gates, and a thread its later review dropped is the Kernel's to resolve | live | adapters, kernel, schemas, sim, tools |
| 0213 | A case the vendor or the network failed is asked again a bounded number of times, and told apart from running out | live | harness, schemas, tools |
| 0214 | A read in the second after a base move may give the merge state of before it, and the snapshot's last read holds it | live | adapters, kernel, tools, trials |
| 0215 | No Role is named to open pull requests until open_pull_request has its writer | live | examples, tools |
| 0216 | The author Role's fix is admitted only on a pull request the Factory opened | live | adapters, examples, kernel, schemas, sim, tools |
| 0217 | While the draft the Factory opened fails its checks, the issue admits another implementing Run | live | adapters, config, controller, kernel |
| 0218 | An issue's timeline is read by REST, whole by its missing next link, and an App's act with a person's token is the App's | replaced by 0237 | adapters, controller, examples, schemas, tools, trials |
| 0219 | A Run that writes code hands over a patch by its digest, `apply` alone pushes, and the item's own checks on the draft are its build | live | harness, tools |
| 0220 | A gate set's sealed ledger says where two of its groups overlap in a few cases, and nothing public does | live | harness, schemas, tools |
| 0221 | A Lens's review that ends while a conflict waits at the Run ceiling holds the item, and the explorer reads a conflict at once | live | lifecycle, tools |
| 0222 | A rule on a Role's own write is a guard, a pure function in guards/, held as the Kernel is | live | config, tools |
| 0223 | A person's resolution of a thread a Role opened is a write reconciliation matches to the Kernel's act that named the thread | live | adapters, controller, examples, schemas, tools |
| 0224 | A second model family reads a change as an advisory Lens inside the review's Run, and `pr-review` adopts only what it checked | live | adapters, examples, schemas, tools |
| 0225 | A workflow on pull_request beside a secret takes its settings from protected files of the head, or checks out the base | live | config, harness, tools |
| 0226 | Where the branch does not exist, the opening Run is admitted for the commit it lands on, and the default branch moving does not stop it | live | kernel, sim |
| 0227 | A Run that cannot show a review a Finding it lists is never asked, and ends as the item's own | live | harness |
| 0228 | An eval case shows a review its Lens's open Findings, and each ruling is scored | live | harness, schemas, tools |
| 0229 | An issue that moved while a pass read it is deferred once with no alert, as a pull request is | live | controller |
| 0230 | The served issues' writes are read for reconciliation, and one not read is short, never owed | live | adapters, controller |
| 0231 | No issue rule reads when a Run's jobs began, so the pass asks the jobs of no issue's Run | live | controller, kernel |
| 0232 | A pull request the Factory opened stands with its issue: held while a person holds the issue or has closed it | live | adapters, controller, examples, harness, kernel, schemas |
| 0233 | The Controller's tracking issue is told at its own read, by the App that opened it and the body its write step writes | live | adapters, controller |
| 0234 | An issue's reads are bounded by pages and by a budget of requests a pass, and an issue past its bound calls a person | live | adapters, config, controller, examples, kernel, sim |
| 0235 | An issue a pass served that has left is read with its close, and one read short is owed | live | adapters, controller |
| 0236 | A pull request linked by hand to another base leaves an issue's linked list not whole | live | adapters |
| 0237 | A commit closer is read only as a listed pull request's merge, and the closers' rows say what the port reads and the trials it still owes | live | adapters, kernel, sim |
| 0238 | The opening Run's draft is the model's title and body, bounded in effect/1; `apply` writes it after the push and appends the one closing line | live | examples, harness, schemas, tools |
| 0239 | Push is granted only where no secret-bearing job runs what a patch may change, no Run holds a tool that runs code, and a later opening Run opens from the branch | live | adapters, harness |
| 0240 | The checks that hold a trust boundary are protected paths | live | config |
| 0243 | An advisory Lens's spend, configuration and model pin are worded by the configuration's keys | live | adapters, controller, harness |
| 0244 | A pull request's title names its area, a plain change and its issue | live | tools |
| 0245 | A new record's title is short and names its file | live | tools |
| 0246 | A pull request's body keeps the template's shape | live | tools |
| 0248 | Every reason the Kernel gives is listed in one of two sets | live | kernel |
| 0249 | A trial's question and pass are read from its own page | live | tools |
| 0250 | An issue's references and links are cut past their one page | live | adapters, kernel |
| 0251 | A pass reads issues to a budget of requests, oldest left out first | live | adapters, config, controller, examples |
| 0252 | A short issue list reads no issue and stops no pass | live | controller |
| 1121 | A decision record takes the number of the pull request that adds it | live | tools |
| 1123 | The feed gives each reason one plain sentence a person reads | live | adapters, examples, schemas, tools |
| 1138 | Four open pull requests are read at once, and a rate limit is no answer | live | adapters, controller |
| 1145 | A pass reads the repo before and after the issues that left | live | adapters, controller |
| 1166 | A new record is a short why-log held to a word budget | live | tools |

## Chains

Each live record that replaced others, and every record it replaced, through the chain.

| Live record | Replaced |
|---|---|
| 0017 | 0016 |
| 0026 | 0012, 0015, 0018, 0022 |
| 0049 | 0029 |
| 0052 | 0046 |
| 0133 | 0042, 0129 |
| 0136 | 0122 |
| 0140 | 0135 |
| 0150 | 0071, 0078, 0094, 0099, 0100, 0109, 0120 |
| 0151 | 0045, 0050, 0138, 0147 |
| 0168 | 0158 |
| 0188 | 0070 |
| 0237 | 0028, 0139, 0141, 0174, 0218 |
