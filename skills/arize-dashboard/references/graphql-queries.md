# Dashboard GraphQL queries

Canonical queries for this skill. POST to the programmatic endpoint (see references/dashboard-graphql-schema.md § HTTP endpoint). Header **`x-api-key`**: use **`$ARIZE_API_KEY`** only when already exported in the shell.

Official widget inventory shape: `https://arize.com/docs/ax/graphql-reference/apis/dashboards-api` (section “Query for Widget IDs”).

---

## List dashboards on a model

```graphql
query ListModelDashboards($modelId: ID!, $search: String, $first: Int!) {
  node(id: $modelId) {
    ... on Model {
      id
      name
      modelDashboards(search: $search, first: $first) {
        totalCount
        edges {
          node {
            dashboardId
            dashboardName
            dashboardStatus
          }
        }
        pageInfo {
          hasNextPage
          endCursor
        }
      }
    }
  }
}
```

**Variables:** `{ "modelId": "<Model global id>", "search": null, "first": 100 }`

Paginate with `after: pageInfo.endCursor` when `hasNextPage` is true.

---

## Model schema (dimensions for widgets)

```graphql
query ModelSchema($modelId: ID!) {
  node(id: $modelId) {
    ... on Model {
      id
      name
      modelSchema {
        features {
          id
          name
          dataType
        }
        tags {
          id
          name
          dataType
        }
        predictions {
          id
          name
          dataType
        }
        actuals {
          id
          name
          dataType
        }
      }
      modelPrimaryBaseline {
        id
      }
    }
  }
}
```

Extend the selection set via introspection if your tenant exposes more fields.

---

## Load dashboard and widget ids

```graphql
query DashboardWidgets($dashboardId: ID!) {
  node(id: $dashboardId) {
    ... on Dashboard {
      id
      name
      status
      statisticWidgets {
        edges {
          node {
            id
            title
            creationStatus
          }
        }
      }
      barChartWidgets {
        edges {
          node {
            id
            title
            creationStatus
          }
        }
      }
      lineChartWidgets {
        edges {
          node {
            id
            title
            creationStatus
          }
        }
      }
      driftLineChartWidgets {
        edges {
          node {
            id
            title
            creationStatus
          }
        }
      }
      textWidgets {
        edges {
          node {
            id
            title
            creationStatus
          }
        }
      }
      monitorLineChartWidgets {
        edges {
          node {
            id
            title
            creationStatus
          }
        }
      }
    }
  }
}
```

Use each edge **`node.id`** as the widget global id for **update** / **delete** mutations.
