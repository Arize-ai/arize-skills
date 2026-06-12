# GraphQL Patterns for Arize API

Patterns derived from the Arize GraphQL schema and best practices from the text-to-graphql architecture.

---

## Schema Understanding

### Type Hierarchy

When working with the introspected schema, understand these relationships:

```
__Schema
├── queryType → Query (root queries)
├── mutationType → Mutation (root mutations)
└── types[] → All types in the schema
    ├── OBJECT types (Space, Model, Monitor, etc.)
    ├── INPUT_OBJECT types (CreateMonitorInput, etc.)
    ├── ENUM types (ModelType, MonitorStatus, etc.)
    ├── INTERFACE types (Node, etc.)
    └── SCALAR types (String, Int, ID, etc.)
```

### Unwrapping Type References

Types may be wrapped in `NON_NULL` or `LIST`. Always unwrap to find the actual type:

```python
# Pseudocode for unwrapping
def unwrap_type(type_ref):
    while type_ref.kind in ['NON_NULL', 'LIST']:
        type_ref = type_ref.ofType
    return type_ref  # Now has the actual type name
```

Example type chain:
```
{kind: "NON_NULL", ofType: {kind: "LIST", ofType: {kind: "NON_NULL", ofType: {kind: "OBJECT", name: "Space"}}}}
→ [Space!]!
```

---

## Relay Connection Pattern

Arize uses Relay-style connections for paginated lists. This `edges`/`node` shape applies **only** to fields whose return type is a `*Connection` (it has `edges` and `pageInfo`). A field that the schema exposes as a plain list (e.g. `[Model]`) is queried directly, without `edges`/`node` — always check the field's return type before choosing the shape.

### Structure

```graphql
type SpaceConnection {
  edges: [SpaceEdge!]!
  pageInfo: PageInfo!
}

type SpaceEdge {
  node: Space!
  cursor: String!
}

type PageInfo {
  hasNextPage: Boolean!
  hasPreviousPage: Boolean!
  startCursor: String
  endCursor: String
}
```

### Query Pattern

```graphql
{
  spaces(first: 10, after: "cursor") {
    edges {
      node {
        id
        name
        # ... other fields
      }
      cursor
    }
    pageInfo {
      hasNextPage
      endCursor
    }
  }
}
```

### Pagination Loop

```bash
# First page
CURSOR=""
QUERY='{ spaces(first: 100) { edges { node { id name } cursor } pageInfo { hasNextPage endCursor } } }'

# Next pages - use endCursor from previous response
CURSOR="previous_end_cursor"
QUERY="{ spaces(first: 100, after: \"$CURSOR\") { edges { node { id name } } pageInfo { hasNextPage endCursor } } }"
```

---

## Node Interface

All major entities implement the `Node` interface with a globally unique `id`.

### Direct Node Lookup

```graphql
{
  node(id: "U3BhY2U6MTIzNDU=") {
    id
    ... on Space {
      name
      models { edges { node { name } } }
    }
    ... on Model {
      name
      modelType
    }
  }
}
```

### ID Format

IDs are base64-encoded: `Space:12345` → `U3BhY2U6MTIzNDU=`

Decode to understand the type:
```bash
echo "U3BhY2U6MTIzNDU=" | base64 -d
# Output: Space:12345
```

---

## Building Context for Queries

When constructing queries, gather all relevant types:

### For a Query

1. Start with the query's return type
2. For each field, get its type (unwrapping as needed)
3. Recursively gather types for nested fields
4. Skip `Node` implementations to avoid circular dependencies

### For a Mutation

1. Get the mutation's input type
2. Get the mutation's return/payload type
3. Gather all types referenced by input fields
4. Gather all types referenced by payload fields

---

## Mutation Patterns

### Structure

```graphql
mutation OperationName($input: InputTypeName!) {
  mutationName(input: $input) {
    # Payload fields - check schema for available fields
    createdEntity { id name }
    errors { field message }
  }
}
```

### Finding Input Fields

From introspection, INPUT_OBJECT types have `inputFields` (not `fields`):

```json
{
  "kind": "INPUT_OBJECT",
  "name": "CreateSpaceInput",
  "inputFields": [
    {"name": "name", "type": {...}},
    {"name": "organizationId", "type": {...}}
  ]
}
```

### Required vs Optional

- `NON_NULL` wrapper = required field
- No wrapper = optional field

### Common Mutation Patterns

**Create:**
```graphql
mutation CreateSpace($input: CreateSpaceInput!) {
  createSpace(input: $input) {
    space { id name }
  }
}
```

**Update/Patch:**
```graphql
mutation PatchMonitor($input: PatchMonitorInput!) {
  patchMonitor(input: $input) {
    monitor { id name status }
  }
}
```

**Delete:**
```graphql
mutation DeleteModel($input: DeleteModelInput!) {
  deleteModel(input: $input) {
    success
  }
}
```

**Assign/Remove (relationships):**
```graphql
mutation AssignSpaceMembership($input: AssignSpaceMembershipInput!) {
  assignSpaceMembership(input: $input) {
    # Check schema for return type
  }
}
```

---

## Filtering

Many connections support filter arguments. Check the schema for available filters:

```graphql
# Find filter argument in schema
{
  "name": "monitors",
  "args": [
    {"name": "filter", "type": {"name": "MonitorFilter"}}
  ]
}

# Look up MonitorFilter input type for available fields
```

Usage:
```graphql
{
  monitors(filter: { status: ALERTING }) {
    edges { node { name status } }
  }
}
```

---

## Enum Values

Enums are specified without quotes in GraphQL:

```graphql
# Correct
{ models(filter: { modelType: GENERATIVE }) { ... } }

# Wrong - don't quote enum values
{ models(filter: { modelType: "GENERATIVE" }) { ... } }
```

Find enum values from introspection:
```json
{
  "kind": "ENUM",
  "name": "ModelType",
  "enumValues": [
    {"name": "SCORE"},
    {"name": "GENERATIVE"},
    {"name": "RANKING"}
  ]
}
```

---

## Inline Fragments

Use for interface or union types:

```graphql
{
  node(id: "...") {
    ... on Space { name description }
    ... on Model { name modelType }
    ... on Monitor { name status }
  }
}
```

Check `possibleTypes` in schema to see what types implement an interface.

---

## Error Handling

### GraphQL Errors

```json
{
  "data": null,
  "errors": [
    {
      "message": "Field 'foo' doesn't exist on type 'Space'",
      "locations": [{"line": 1, "column": 10}],
      "path": ["space", "foo"]
    }
  ]
}
```

### Mutation Errors (in payload)

```json
{
  "data": {
    "createSpace": {
      "space": null,
      "errors": [
        {"field": "name", "message": "Name already exists"}
      ]
    }
  }
}
```

Always check both top-level `errors` and payload `errors`.

---

## Optimizing Token Usage

When providing schema context:

1. **Remove descriptions** for non-root types (saves ~60% tokens)
2. **Only include relevant types** for the specific query/mutation
3. **Stop recursion at Node types** to avoid circular dependencies

---

## curl Escaping Reference

### Single quotes (simple):
```bash
curl ... -d '{"query": "{ spaces { edges { node { id } } } }"}'
```

### Heredoc (complex/multiline):
```bash
curl ... -d @- <<'EOF'
{
  "query": "query { ... }",
  "variables": { ... }
}
EOF
```

### Variable interpolation:
```bash
ID="abc123"
curl ... -d "{\"query\": \"{ node(id: \\\"$ID\\\") { id } }\"}"
```
