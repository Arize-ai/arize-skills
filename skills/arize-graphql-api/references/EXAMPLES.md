# Arize GraphQL Examples

Practical examples using the patterns from the schema.

---

## Setup

All examples assume:
```bash
export ARIZE_API_KEY="your-api-key"
export ARIZE_GRAPHQL_ENDPOINT="https://app.arize.com/graphql"
```

---

## Full Schema Introspection

**Always run this first** to understand available types:

```bash
curl -s -X POST "$ARIZE_GRAPHQL_ENDPOINT" \
  -H "Content-Type: application/json" \
  -H "x-api-key: $ARIZE_API_KEY" \
  -d @- <<'EOF'
{
  "query": "query IntrospectionQuery { __schema { queryType { name } mutationType { name } subscriptionType { name } types { ...FullType } directives { name description locations args { ...InputValue } } } } fragment FullType on __Type { kind name description fields(includeDeprecated: true) { name description args { ...InputValue } type { ...TypeRef } isDeprecated deprecationReason } inputFields { ...InputValue } interfaces { ...TypeRef } enumValues(includeDeprecated: true) { name description isDeprecated deprecationReason } possibleTypes { ...TypeRef } } fragment InputValue on __InputValue { name description type { ...TypeRef } defaultValue } fragment TypeRef on __Type { kind name ofType { kind name ofType { kind name ofType { kind name ofType { kind name ofType { kind name ofType { kind name ofType { kind name ofType { kind name ofType { kind name } } } } } } } } } }"
}
EOF
```

---

## Exploring the Schema

### List All Query Fields

```bash
curl -s -X POST "$ARIZE_GRAPHQL_ENDPOINT" \
  -H "Content-Type: application/json" \
  -H "x-api-key: $ARIZE_API_KEY" \
  -d '{"query": "{ __type(name: \"Query\") { fields { name description args { name type { name kind ofType { name } } } type { name kind ofType { name } } } } }"}'
```

### List All Mutations

```bash
curl -s -X POST "$ARIZE_GRAPHQL_ENDPOINT" \
  -H "Content-Type: application/json" \
  -H "x-api-key: $ARIZE_API_KEY" \
  -d '{"query": "{ __type(name: \"Mutation\") { fields { name description args { name type { name kind ofType { name } } } } } }"}'
```

### Explore a Specific Type

```bash
TYPE_NAME="Space"
curl -s -X POST "$ARIZE_GRAPHQL_ENDPOINT" \
  -H "Content-Type: application/json" \
  -H "x-api-key: $ARIZE_API_KEY" \
  -d "{\"query\": \"{ __type(name: \\\"$TYPE_NAME\\\") { kind name description fields { name description type { name kind ofType { name kind ofType { name } } } args { name type { name kind ofType { name } } } } } }\"}"
```

### Explore an Input Type (for mutations)

```bash
INPUT_TYPE="AssignSpaceMembershipInput"
curl -s -X POST "$ARIZE_GRAPHQL_ENDPOINT" \
  -H "Content-Type: application/json" \
  -H "x-api-key: $ARIZE_API_KEY" \
  -d "{\"query\": \"{ __type(name: \\\"$INPUT_TYPE\\\") { kind name inputFields { name description type { name kind ofType { name kind } } } } }\"}"
```

### Get Enum Values

```bash
ENUM_NAME="ModelType"
curl -s -X POST "$ARIZE_GRAPHQL_ENDPOINT" \
  -H "Content-Type: application/json" \
  -H "x-api-key: $ARIZE_API_KEY" \
  -d "{\"query\": \"{ __type(name: \\\"$ENUM_NAME\\\") { enumValues { name description } } }\"}"
```

---

## Common Queries

### List All Spaces

```bash
curl -s -X POST "$ARIZE_GRAPHQL_ENDPOINT" \
  -H "Content-Type: application/json" \
  -H "x-api-key: $ARIZE_API_KEY" \
  -d '{"query": "{ spaces { edges { node { id name } } } }"}'
```

### Get Space with Models

```bash
curl -s -X POST "$ARIZE_GRAPHQL_ENDPOINT" \
  -H "Content-Type: application/json" \
  -H "x-api-key: $ARIZE_API_KEY" \
  -d '{"query": "{ spaces { edges { node { id name models { edges { node { id name modelType } } } } } } }"}'
```

### Get Entity by ID (Node lookup)

```bash
ENTITY_ID="your-base64-id"
curl -s -X POST "$ARIZE_GRAPHQL_ENDPOINT" \
  -H "Content-Type: application/json" \
  -H "x-api-key: $ARIZE_API_KEY" \
  -d "{\"query\": \"{ node(id: \\\"$ENTITY_ID\\\") { id ... on Space { name } ... on Model { name modelType } ... on Monitor { name status } } }\"}"
```

### Paginated Query

```bash
# First page
curl -s -X POST "$ARIZE_GRAPHQL_ENDPOINT" \
  -H "Content-Type: application/json" \
  -H "x-api-key: $ARIZE_API_KEY" \
  -d '{"query": "{ spaces(first: 10) { edges { node { id name } cursor } pageInfo { hasNextPage endCursor } } }"}'

# Next page (use endCursor from previous response)
CURSOR="previous-end-cursor"
curl -s -X POST "$ARIZE_GRAPHQL_ENDPOINT" \
  -H "Content-Type: application/json" \
  -H "x-api-key: $ARIZE_API_KEY" \
  -d "{\"query\": \"{ spaces(first: 10, after: \\\"$CURSOR\\\") { edges { node { id name } } pageInfo { hasNextPage endCursor } } }\"}"
```

---

## Common Mutations

### Create Space

```bash
curl -s -X POST "$ARIZE_GRAPHQL_ENDPOINT" \
  -H "Content-Type: application/json" \
  -H "x-api-key: $ARIZE_API_KEY" \
  -d @- <<'EOF'
{
  "query": "mutation CreateSpace($input: CreateSpaceInput!) { createSpace(input: $input) { space { id name } } }",
  "variables": {
    "input": {
      "name": "My New Space",
      "organizationId": "your-org-id"
    }
  }
}
EOF
```

### Delete Model

```bash
curl -s -X POST "$ARIZE_GRAPHQL_ENDPOINT" \
  -H "Content-Type: application/json" \
  -H "x-api-key: $ARIZE_API_KEY" \
  -d @- <<'EOF'
{
  "query": "mutation DeleteModel($input: DeleteModelInput!) { deleteModel(input: $input) }",
  "variables": {
    "input": {
      "modelId": "model-id-here"
    }
  }
}
EOF
```

### Generic Mutation Template

```bash
curl -s -X POST "$ARIZE_GRAPHQL_ENDPOINT" \
  -H "Content-Type: application/json" \
  -H "x-api-key: $ARIZE_API_KEY" \
  -d @- <<'EOF'
{
  "query": "mutation MutationName($input: InputTypeName!) { mutationName(input: $input) { returnField { id } } }",
  "variables": {
    "input": {
      "requiredField": "value",
      "optionalField": "value"
    }
  }
}
EOF
```

---

## Discovery Workflow

When you need to find a specific mutation:

### 1. Search mutations by name pattern

```bash
# Get all mutations, then filter for keywords like "user", "member", "space"
curl -s -X POST "$ARIZE_GRAPHQL_ENDPOINT" \
  -H "Content-Type: application/json" \
  -H "x-api-key: $ARIZE_API_KEY" \
  -d '{"query": "{ __type(name: \"Mutation\") { fields { name description } } }"}'
```

### 2. Get mutation details

```bash
MUTATION_NAME="assignSpaceMembership"
curl -s -X POST "$ARIZE_GRAPHQL_ENDPOINT" \
  -H "Content-Type: application/json" \
  -H "x-api-key: $ARIZE_API_KEY" \
  -d "{\"query\": \"{ __type(name: \\\"Mutation\\\") { fields(includeDeprecated: true) { name args { name type { name kind ofType { name } } } type { name kind ofType { name } } } } }\"}"
```

### 3. Get input type fields

Once you know the input type name (e.g., `AssignSpaceMembershipInput`):

```bash
curl -s -X POST "$ARIZE_GRAPHQL_ENDPOINT" \
  -H "Content-Type: application/json" \
  -H "x-api-key: $ARIZE_API_KEY" \
  -d '{"query": "{ __type(name: \"AssignSpaceMembershipInput\") { inputFields { name description type { name kind ofType { name kind } } } } }"}'
```

### 4. Construct and execute

Build the mutation using the discovered fields and execute.

---

## Error Handling

### Check for errors in response

```bash
RESPONSE=$(curl -s -X POST "$ARIZE_GRAPHQL_ENDPOINT" \
  -H "Content-Type: application/json" \
  -H "x-api-key: $ARIZE_API_KEY" \
  -d '{"query": "{ spaces { edges { node { id } } } }"}')

# Check for errors
echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print('ERRORS:', d.get('errors')) if d.get('errors') else print('SUCCESS:', d.get('data'))"
```

---

## Tips

1. **Always introspect first** - Schema may change between versions
2. **Use heredoc for complex queries** - Avoids escaping issues
3. **Check inputFields for INPUT_OBJECT** - Not `fields`
4. **Enums are unquoted** - `status: ACTIVE` not `status: "ACTIVE"`
5. **IDs are base64** - Decode to see type: `echo "ID" | base64 -d`
