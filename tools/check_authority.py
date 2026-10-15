"""Mechanical checks on who decides what: who owns each category of Finding, and that nothing speaks for a Lens."""
from __future__ import annotations

import json
import pathlib

from kernel import terms

ROOT = pathlib.Path(__file__).resolve().parent.parent
MODEL_JUDGED = {"functional", "security", "architecture", "delivery", "reliability",
                "requirements", "uncategorised"}


def _folded(name: str) -> str:
    """A name as a reader that ignores case and the space around it would read it."""
    return name.strip().casefold()


def run(authority: dict = None, config: dict = None, facts: dict = None) -> list:
    a = json.loads((ROOT / "config" / "authority.json").read_text()) if authority is None else authority
    c = json.loads((ROOT / "config" / "defaults.json").read_text()) if config is None else config
    problems = []
    if a["author_role"] != c["author_role"]:
        problems.append("the author Role differs between the authority table and the configuration")
    if a["max_rounds"] != c["limits"]["max_rounds"]:
        problems.append("max_rounds differs between the authority table and the configuration")
    # A Lens or its check named twice could pin two Apps, and which one reads the Lens would be unclear. Names are
    # compared folded, as a reader of names may fold them.
    lenses = c["required_lenses"]
    for key, what in (("lens", "Lens"), ("check", "check")):
        seen = set()
        for lens in lenses["deterministic"]:
            name = _folded(lens[key])
            if name in seen:
                problems.append("the %s %r is named twice in required_lenses.deterministic; name each once"
                                % (what, lens[key]))
            seen.add(name)
    # The Controller posts the status on the item as a check run. Under a required Lens's name, or the name of its
    # check, it would speak for that Lens.
    names = [lens[key] for lens in lenses["deterministic"] for key in ("lens", "check")] + list(lenses["model"])
    if _folded(c["status_on_item"]) in {_folded(name) for name in names}:
        problems.append("the status on the item is named %r, a required Lens's or its check's; give it a name no Lens "
                        "or check has" % c["status_on_item"])
    cats = a["categories"]
    finding = json.loads((ROOT / "schemas" / "finding.schema.json").read_text())
    known = set(finding["properties"]["category"]["enum"])
    for name in sorted(known - set(cats)):
        problems.append("a Finding may carry the category %s, and nobody owns it" % name)
    for name in sorted(set(cats) - known):
        problems.append("%s has an owner, and no Finding can carry it" % name)
    # A thread in the facts carries its Finding's category, in the same terms, or null where a Lens writes it as prose.
    # The Kernel reads a required Lens's thread only in those terms, and its severity only in the Finding's.
    f = json.loads((ROOT / "schemas" / "facts.schema.json").read_text()) if facts is None else facts
    fields = f.get("properties", {}).get("threads", {}).get("items", {}).get("properties", {})
    if not isinstance(fields.get("category"), dict) or not isinstance(fields["category"].get("enum"), list):
        problems.append("a thread in the facts carries no category")
        on_threads = set()
    else:
        on_threads = set(fields["category"]["enum"]) - {None}
    for name in sorted(on_threads - known):
        problems.append("a thread may carry the category %s, and no Finding can" % name)
    for name in sorted(known - on_threads):
        problems.append("a Finding may carry the category %s, and no thread can" % name)
    if set(terms.CATEGORIES) != known:
        problems.append("the Kernel reads the categories %s, and a Finding carries %s"
                        % (sorted(terms.CATEGORIES), sorted(known)))
    if set(terms.SEVERITIES) != set(finding["properties"]["severity"]["enum"]):
        problems.append("the Kernel reads the severities %s, and a Finding carries %s"
                        % (sorted(terms.SEVERITIES), sorted(finding["properties"]["severity"]["enum"])))
    for name in sorted(MODEL_JUDGED - set(cats)):
        problems.append("category has no owner: %s" % name)
    for name, c in sorted(cats.items()):
        owner = c["owner"]
        if name in MODEL_JUDGED and owner in ("none", "human"):
            problems.append("%s is judged by a model and needs a Role as owner" % name)
        if owner == a["author_role"]:
            problems.append("%s: the author Role may not own a category" % name)
        if c.get("shadow") == owner:
            problems.append("%s: a Role cannot shadow itself" % name)
        if c.get("shadow") == a["author_role"]:
            problems.append("%s: the author Role may not shadow a category" % name)
    weak = set(cats.get("security", {}).get("may_accept", [])) & {"declined", "deferred"}
    if weak:
        problems.append("a security Finding may never be accepted as: %s" % sorted(weak))
    return problems
