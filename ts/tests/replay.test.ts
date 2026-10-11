// The TypeScript Kernel must make the same decision as the Python one, case for case.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { decide } from "../kernel/decide.ts";
import { validate, SchemaError } from "../tools/jsonschema_lite.ts";

const root = new URL("../../", import.meta.url);
const read = (rel: string) => JSON.parse(readFileSync(new URL(rel, root), "utf8"));

const canon = (v: unknown): string =>
  Array.isArray(v) ? `[${v.map(canon).join(",")}]`
    : v !== null && typeof v === "object"
      ? `{${Object.keys(v).sort().map((k) => `${JSON.stringify(k)}:${canon((v as any)[k])}`).join(",")}}`
      : JSON.stringify(v);

test("every recorded decision is reproduced exactly", () => {
  const lines = readFileSync(new URL("corpus/decisions.jsonl", root), "utf8").trim().split("\n");
  const decisionSchema = read("schemas/decision.schema.json");
  let n = 0;
  for (const line of lines) {
    const c = JSON.parse(line);
    const got = decide(c.facts, c.runs, c.context, c.config, c.now);
    assert.equal(canon(got), c.expected);
    assert.deepEqual(validate(got, decisionSchema), []);
    n++;
  }
  assert.ok(n > 1000, `only ${n} cases`);
  console.log(`  ${n} decisions replayed`);
});

test("golden examples validate and counter-examples are rejected", () => {
  const schemas: Record<string, any> = {};
  for (const f of readdirSync(new URL("schemas/", root))) schemas[f.replace(".schema.json", "")] = read(`schemas/${f}`);
  for (const f of readdirSync(new URL("examples/", root)).filter((f) => f.endsWith(".json"))) {
    assert.deepEqual(validate(read(`examples/${f}`), schemas[f.split(".")[0]]), [], f);
  }
  for (const f of readdirSync(new URL("examples/invalid/", root))) {
    assert.notEqual(validate(read(`examples/invalid/${f}`), schemas[f.split(".")[0]]).length, 0, f);
  }
  const live: [string, string][] = [["lifecycle/pull_request.json", "lifecycle"], ["config/authority.json", "authority"],
    ["config/defaults.json", "config"], ["config/rubric-pr-review.json", "rubric"]];
  for (const [rel, kind] of live) assert.deepEqual(validate(read(rel), schemas[kind]), [], rel);
});

test("the validator refuses a schema it cannot enforce", () => {
  assert.throws(() => validate({}, { type: "object", patternProperties: {} }), SchemaError);
  assert.equal(validate(true, { type: "integer" }).length, 1);
});
