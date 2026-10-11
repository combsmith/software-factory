// The subset of JSON Schema the Factory's schemas use. Fails closed on any other keyword.
const ANNOTATIONS = new Set(["$schema", "$id", "title", "description", "$defs", "$comment"]);
const KEYWORDS = new Set(["type", "properties", "required", "additionalProperties", "items", "enum", "const",
  "minimum", "maximum", "minLength", "minItems", "pattern", "$ref"]);
type Schema = Record<string, any>;

export class SchemaError extends Error {}

function isType(v: unknown, name: string): boolean {
  switch (name) {
    case "object": return typeof v === "object" && v !== null && !Array.isArray(v);
    case "array": return Array.isArray(v);
    case "string": return typeof v === "string";
    case "boolean": return typeof v === "boolean";
    case "null": return v === null;
    case "integer": return typeof v === "number" && Number.isInteger(v);
    case "number": return typeof v === "number";
    default: throw new SchemaError(`unknown type: ${name}`);
  }
}

export function validate(value: any, schema: Schema, root: Schema = schema, path = "$"): string[] {
  const unknown = Object.keys(schema).filter((k) => !KEYWORDS.has(k) && !ANNOTATIONS.has(k));
  if (unknown.length) throw new SchemaError(`unsupported keyword(s) at ${path}: ${unknown.sort()}`);
  if ("$ref" in schema) {
    const ref: string = schema.$ref;
    if (!ref.startsWith("#/$defs/")) throw new SchemaError(`only local $defs references are supported: ${ref}`);
    const target = root.$defs?.[ref.slice("#/$defs/".length)];
    if (target === undefined) throw new SchemaError(`unresolved reference: ${ref}`);
    return validate(value, target, root, path);
  }
  const errors: string[] = [];
  if ("type" in schema) {
    const names: string[] = Array.isArray(schema.type) ? schema.type : [schema.type];
    if (!names.some((n) => isType(value, n))) return [`${path}: expected ${names.join(" or ")}`];
  }
  if ("const" in schema && value !== schema.const) errors.push(`${path}: must be ${JSON.stringify(schema.const)}`);
  if ("enum" in schema && !schema.enum.includes(value)) errors.push(`${path}: ${JSON.stringify(value)} is not allowed`);
  if (typeof value === "string") {
    if (value.length < (schema.minLength ?? 0)) errors.push(`${path}: shorter than ${schema.minLength}`);
    if ("pattern" in schema && !new RegExp(schema.pattern).test(value)) errors.push(`${path}: does not match ${schema.pattern}`);
  }
  if (typeof value === "number") {
    if ("minimum" in schema && value < schema.minimum) errors.push(`${path}: below ${schema.minimum}`);
    if ("maximum" in schema && value > schema.maximum) errors.push(`${path}: above ${schema.maximum}`);
  }
  if (Array.isArray(value)) {
    if (value.length < (schema.minItems ?? 0)) errors.push(`${path}: fewer than ${schema.minItems} items`);
    if ("items" in schema) value.forEach((item, i) => errors.push(...validate(item, schema.items, root, `${path}[${i}]`)));
  } else if (typeof value === "object" && value !== null) {
    const props: Schema = schema.properties ?? {};
    for (const name of schema.required ?? []) if (!(name in value)) errors.push(`${path}: missing ${name}`);
    const extra = schema.additionalProperties ?? true;
    for (const [name, item] of Object.entries(value)) {
      if (name in props) errors.push(...validate(item, props[name], root, `${path}.${name}`));
      else if (extra === false) errors.push(`${path}: unexpected ${name}`);
      else if (typeof extra === "object") errors.push(...validate(item, extra, root, `${path}.${name}`));
    }
  }
  return errors;
}
