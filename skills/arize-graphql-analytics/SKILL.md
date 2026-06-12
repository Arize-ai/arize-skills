---
name: arize-graphql-analytics
description: Query and analyze data from the Arize platform using GraphQL, or help build/validate GraphQL queries and mutations. Use when users want to explore spaces, models, monitors, datasets, any Arize platform data, OR when they need help writing, formatting, or debugging GraphQL queries/mutations for the Arize API.
metadata:
  author: arize
  version: "1.1"
compatibility: Requires curl and jq. User must have an ARIZE_API_KEY environment variable set.
---

# Arize GraphQL Analytics

Query and analyze data from the Arize ML observability platform using GraphQL via curl, or help users write and debug GraphQL queries and mutations.

---

## Decide the mode first

Two things a user might want. Figure out which one before doing anything else, because they end differently:

- **Execute mode** — the user wants data or wants a change applied: *"show me my spaces"*, *"how many monitors are alerting?"*, *"create a space called X"*. You run the operation and return results.
- **Draft mode** — the user wants a query written, formatted, or debugged but **not run**: *"write me a query that lists models in a space"*, *"why is this mutation failing?"*. You build and hand back the query without executing it.

If the request is genuinely ambiguous, ask which they want. When you can't ask and it's still unclear, prefer drafting — executing a mutation has side effects you can't take back.

Both modes share the same start: check the key, then fetch the schema. They only diverge at the final step.

```
Step 1 (both): Check API Key
Step 2 (both): Fetch Schema
Step 3 (both): Build Query/Mutation
Step 4: Execute mode → run it + handle errors    Draft mode → hand back the query
Step 5 (execute only): Summarize results
```

---

## Step 1: Check API Key

```bash
echo "${ARIZE_API_KEY:-NOT_SET}"
```

### If NOT_SET

Ask the user for their API key:

> "To query the Arize GraphQL API, I need your API key. You can find it in Arize: Settings → API Keys."

Then set it:

```bash
export ARIZE_API_KEY="user-provided-key"
```

Verify connectivity before going further:

```bash
curl -s -X POST "${ARIZE_GRAPHQL_ENDPOINT:-https://app.arize.com/graphql}" \
  -H "Content-Type: application/json" \
  -H "x-api-key: $ARIZE_API_KEY" \
  -d '{"query": "{ __typename }"}'
```

Expected: `{"data":{"__typename":"Query"}}`. If you get a `401`, a non-JSON body, or no response at all, stop and resolve that before continuing — see **"When a request fails"** under Step 4 (Execute mode).

---

## Step 2: Fetch the Schema (always first)

The schema is the source of truth. Field names, argument types, and enum values change between API versions, so build queries from a fresh introspection rather than from memory or from earlier examples.

Run the introspection query in `references/EXAMPLES.md` under **"Full Schema Introspection"** — it's a single curl command that returns every type, field, argument, enum value, and relationship in the API. (It lives in the references file rather than inline here so this workflow stays readable; copy it as-is, don't retype it from memory.)

### What "up to 10 levels deep" means

The introspection captures the full set of types and fields. The one bounded part is **type-reference unwrapping**: a field's type can be wrapped in `NON_NULL` and `LIST` markers (e.g. `[Model!]!`), and the query resolves up to 10 of those nested wrappers. Real schemas never stack wrappers more than ~3–4 deep, so in practice you get the complete picture — this is not a meaningful truncation of the schema.

If a specific type reference ever bottoms out at `ofType: null` before reaching a named type, that one reference was nested deeper than the query captured. Don't guess at it and don't tell the user the schema is incomplete — just re-introspect that single type with the targeted `__type(name: "...")` query in EXAMPLES.md.

### Key Type Kinds

| Kind | Description | Example |
|------|-------------|---------|
| `SCALAR` | Primitive types | `String`, `Int`, `ID`, `Boolean`, `Float` |
| `OBJECT` | Complex types with fields | `Space`, `Model`, `Monitor` |
| `INPUT_OBJECT` | Input types for mutations | `CreateMonitorInput` |
| `ENUM` | Enumeration types | `ModelType`, `MonitorStatus` |
| `LIST` | Array wrapper | `[Model]` |
| `NON_NULL` | Required wrapper | `String!` |
| `INTERFACE` | Shared field contract | `Node` |
| `UNION` | One of multiple types | `SearchResult` |

### Unwrapping Types

When `kind` is `NON_NULL` or `LIST`, the actual type is in `ofType`. Keep unwrapping until you reach a named type:

```
NON_NULL → LIST → NON_NULL → OBJECT(Model)
means: [Model!]!
```

---

## Step 3: Build Query or Mutation

Using the introspected schema, construct the operation.

### For Queries

1. Find the query field in the schema's `queryType`.
2. Check its return type and arguments (unwrap as needed).
3. Shape lists according to what the schema actually exposes — see below.
4. Use inline fragments for interface/union types.

### Lists: connections vs. plain lists

Don't assume every list uses the Relay `edges`/`node` shape — check the field's return type in the schema:

- **Connection type** (its name ends in `Connection` and it has `edges` and `pageInfo` fields): use the `edges { node { ... } } pageInfo { ... }` shape.
- **Plain list** (e.g. the type unwraps to `[Model]`): query the fields directly, without wrapping them in `edges`/`node`.

Wrapping a plain list in `edges`/`node` (or querying a connection as if it were a plain list) fails validation, so let the schema decide.

### For Mutations

1. Find the mutation in `mutationType`. **If `mutationType` is `null` or absent**, this API exposes no mutations — tell the user rather than inventing one.
2. Get the input argument's type name and look up that `INPUT_OBJECT` in `types`.
3. Build the mutation with all required `inputFields` (the ones wrapped in `NON_NULL` with no default).
4. **If the user hasn't supplied a value for a required input field**, ask them for it. Never invent IDs, names, or other values — a guessed `organizationId` or `modelId` will either error or, worse, mutate the wrong resource.

See `references/PATTERNS.md` for detailed patterns.

---

## Step 4 (Execute mode): Run it

### Simple Query

```bash
curl -s -X POST "${ARIZE_GRAPHQL_ENDPOINT:-https://app.arize.com/graphql}" \
  -H "Content-Type: application/json" \
  -H "x-api-key: $ARIZE_API_KEY" \
  -d '{"query": "{ spaces { edges { node { id name } } } }"}'
```

### With Variables (for Mutations)

```bash
curl -s -X POST "${ARIZE_GRAPHQL_ENDPOINT:-https://app.arize.com/graphql}" \
  -H "Content-Type: application/json" \
  -H "x-api-key: $ARIZE_API_KEY" \
  -d @- <<'EOF'
{
  "query": "mutation CreateSpace($input: CreateSpaceInput!) { createSpace(input: $input) { space { id name } } }",
  "variables": {
    "input": {
      "name": "My Space",
      "organizationId": "org-id-here"
    }
  }
}
EOF
```

### When a request fails

GraphQL returns HTTP 200 even for many errors, so always inspect the response — don't assume success.

- **Transport failure** — curl exits non-zero, the request times out, the HTTP status isn't 200, or the body isn't valid JSON. Stop and report it plainly. The endpoint or the key is almost certainly wrong; don't keep building or running queries against an endpoint that isn't answering.
- **GraphQL errors** — the response has a top-level `"errors"` array (unknown field, invalid argument, schema mismatch), or a mutation payload contains its own `errors`. Show the user the exact error text, explain what's wrong, and propose a corrected query or mutation. Don't silently retry the same operation, and don't bury the error inside a cheerful summary.

A quick way to surface either case:

```bash
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${ARIZE_GRAPHQL_ENDPOINT:-https://app.arize.com/graphql}" \
  -H "Content-Type: application/json" -H "x-api-key: $ARIZE_API_KEY" \
  -d '{"query": "{ spaces { edges { node { id } } } }"}')
echo "$RESPONSE" | jq . 2>/dev/null || echo "Non-JSON or failed response: $RESPONSE"
```

---

## Step 4 (Draft mode): Hand back the query

When the user wants the query but not the execution, return exactly two things:

1. A **readable, indented GraphQL query** they can review.
2. One **ready-to-run curl command** that wraps it.

Include a `"variables"` block only when the operation actually takes variables (typically a mutation input). Don't produce several near-duplicate variants — one clear query plus one runnable command is what's useful.

---

## Step 5 (Execute mode): Summarize Results

Parse the JSON response and give the user clear insights — counts, names, notable values — rather than dumping raw JSON. If the response carried errors, you've already handled them in Step 4; don't present partial data as if it were complete.

---

## Quick Reference: Common Patterns

### Relay Connections (when the field returns a `*Connection` type)

```graphql
{
  spaces {
    edges {
      node { id name }
      cursor
    }
    pageInfo { hasNextPage endCursor }
  }
}
```

### Node Lookup (by ID)

```graphql
{
  node(id: "BASE64_ID") {
    ... on Space { name }
    ... on Model { name modelType }
  }
}
```

### Pagination

```graphql
{ spaces(first: 10, after: "cursor") { edges { node { id } } } }
```

### Mutations

```graphql
mutation Op($input: InputType!) {
  mutationName(input: $input) {
    entity { id }
    errors { field message }
  }
}
```

---

## Troubleshooting

| Symptom | What it means / what to do |
|---------|----------------------------|
| `401 Unauthorized` | Invalid or expired API key — re-check `ARIZE_API_KEY`. |
| No response, timeout, or non-200 status | Transport failure — verify the endpoint and key before continuing (see **"When a request fails"** under Step 4). |
| Body isn't valid JSON | Likely a gateway/HTML error page, not a GraphQL response — don't parse it as data. |
| `"errors"` array in a 200 response | Validation/runtime error — report the message and propose a fix, don't retry blindly. |
| `Field doesn't exist` | Re-introspect; the field name changed or doesn't exist on that type. |
| `Cannot query field on type` | Use an inline fragment for an interface/union. |
| Parse errors in curl | Check JSON escaping; use the heredoc form for complex queries. |

---

## References

- `references/PATTERNS.md` - Detailed GraphQL patterns
- `references/EXAMPLES.md` - Ready-to-use examples, including the full introspection query
