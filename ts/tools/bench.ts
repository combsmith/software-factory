import { readFileSync } from "node:fs";
import { decide } from "../kernel/decide.ts";
const cases = readFileSync(new URL("../../corpus/decisions.jsonl", import.meta.url), "utf8").trim().split("\n").map((l) => JSON.parse(l));
const t0 = performance.now();
for (let i = 0; i < 20; i++) for (const c of cases) decide(c.facts, c.runs, c.context, c.config, c.now);
console.log(`typescript: ${((performance.now() - t0) * 1000 / (20 * cases.length)).toFixed(1)} microseconds per decision`);
