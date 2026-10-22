"""The feed's two files, `view/meta.json` and `view/items.json`, from one pass record and the records before it
(decision 0039). Nothing else is read, so a view rebuilt from the records equals the view written pass by pass
(decision 0002). Who acts next and what is asked come from `config/feed.json` alone."""
from __future__ import annotations

from controller.shared import checked, key, seconds
from kernel import terms as t


def next_actor(d: dict, feed: dict):
    """Who acts next, read from the Decision's outcome, then its attention class, through config/feed.json alone."""
    rules = feed["next_actor"]
    for row in rules["by_outcome"]:
        if d["outcome"] in row["outcome"]:
            return row["actor"]
    for row in rules["by_attention"]:
        if row["attention"] == d["attention"]:
            if row["actor"] != "by_state":
                return row["actor"]
            for by in rules["by_state"]["rows"]:
                if by["state"] == d["state"]:
                    return by["actor"]
            return rules["by_state"]["default"]
    return None


def asked(d: dict, feed: dict):
    """What a person is asked, from config/feed.json's row for the reason, only when the item needs one."""
    if d["attention"] != t.NEEDS_YOU:
        return None
    for row in feed["decision_required"]:
        if row["reason"] == d["reason"]:
            return {"question": row["question"], "choices": list(row["choices"]), "evidence": list(d["evidence"])}
    return None


def age(entry: dict, record: dict, before: list) -> float:
    """Hours the item has been in its State, by the pass records: since the first of the passes in a row, ending with
    this one, that read it in that State."""
    item, state = entry["decision"]["item"], entry["decision"]["state"]
    since = record["now"]
    for older in reversed(before):
        seen = [e for e in older["pull_requests"] + older["issues"] if e["decision"]["item"] == item]
        if not seen or seen[0]["decision"]["state"] != state:
            break
        since = older["now"]
    return round(seconds(record["now"], since) / 3600.0, 2)


def view(record: dict, before: list, titles: dict, feed: dict) -> dict:
    """The feed's two files: every open item the pass decided on, and when and from what the feed was written."""
    items = []
    for entry in record["pull_requests"] + record["issues"]:
        facts, d = entry["facts"], entry["decision"]
        if facts["state"] != "open":
            continue
        mine = [r for r in record["runs"] if r["item"] == d["item"]]
        intents = sorted({r["intent"] for r in mine})
        # An attempt is a completed Run that failed by a fault of the item, since a person with write access last acted,
        # as the brakes count it (I-23): one that ran and left no outcome among them (decision 0049). Another Run is
        # among the item's `runs`, never its attempts.
        since = facts.get("last_writer_action_at")
        tried = [r for r in mine if r["status"] == "completed" and r["conclusion"] != "success"
                 and (r["outcome"] == "item" or (r["outcome"] is None and r["conclusion"] in t.RAN_AND_DIED))
                 and (since is None or r["started_at"] > since)]
        items.append({
            "item": d["item"], "state": d["state"], "reason": d["reason"], "attention": d["attention"],
            "evidence": list(d["evidence"]), "next_actor": next_actor(d, feed), "decision_required": asked(d, feed),
            "content_id": facts.get("content_id"), "age_hours": age(entry, record, before),
            "attempts": [{"intent": i, "count": len([r for r in tried if r["intent"] == i])} for i in intents],
            "runs": len(mine), "cost_usd": None, "sources": sorted({r["run"] for r in mine}), "url": key(d["item"]),
            "untrusted": {"title": titles.get(key(d["item"]), "")}})
    reach = min([r["started_at"] for r in record["runs"]] or [record["now"]])
    meta = {"schema": "view-meta/1", "pass": record["pass"], "release": record["release"],
            "written_at": record["now"], "reaches_back_to": reach}
    listed = {"schema": "view-items/1", "pass": record["pass"], "release": record["release"], "items": items}
    return {"meta": checked(meta, "view-meta"), "items": checked(listed, "view-items")}


def rebuild(records: list, titles: dict, feed: dict) -> list:
    """The view as each pass record leaves it, rebuilt from the records alone, oldest first. A record holds no title,
    so the titles are the ones read with the rebuild: a title changed since a pass is the one thing a rebuild shows
    otherwise, and it is untrusted text that decides nothing."""
    ordered = sorted(records, key=lambda r: r["now"])
    return [view(r, [e for e in ordered if e["now"] < r["now"]], titles, feed) for r in ordered]
