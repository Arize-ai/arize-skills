---
name: arize-admin
description: "Manages Arize users, organizations, spaces, projects, roles, role bindings, resource restrictions, and API keys via the ax CLI. Use for enterprise admin workflows: inviting and offboarding users, onboarding new teams, creating custom roles for SAML/SSO mappings, assigning roles to users, restricting project-level access, and managing service keys for multi-tenant architectures. Covers ax users, ax organizations, ax spaces, ax projects, ax roles, ax role-bindings, and ax api-keys."
metadata:
  author: arize
  version: "1.0"
compatibility: Requires the ax CLI (≥ 0.19.0) and a configured Arize profile with org-admin privileges.
---

# Arize Admin Skill

Programmatic management of Arize users, organizations, spaces, roles, permissions, and API keys — the building blocks for enterprise access control.

> **Privilege requirement:** Most operations require **org-admin** or **account-admin** privileges. If commands return `403 Forbidden`, the authenticated profile lacks sufficient permissions.

> **Destructive-action rule:** Commands that delete, revoke, remove, or irreversibly modify resources (`delete`, `revoke`, `remove-user`, `unrestrict`) require **explicit user confirmation before execution**. When a user asks you to perform one of these operations:
> 1. Summarize exactly what will happen (e.g., "This will delete user jane@example.com and cascade-revoke their API keys and remove all their org/space memberships and role bindings.")
> 2. Ask the user to confirm (use `AskUserQuestion`).
> 3. Only after the user confirms, run the command with `--force` to skip the CLI's interactive prompt.
>
> Never run a `--force` destructive command without confirming with the user first.

## When to Use

- Invite users to the account, assign them to orgs and spaces
- Offboard a user and revoke all their access in one command
- Onboard a new team: create a space, create a custom role, assign users, generate a service key
- Create custom roles for SAML/SSO attribute mappings (need stable role IDs)
- Restrict a project so only explicitly bound users can access it
- Create scoped service keys for CI/CD pipelines or multi-tenant architectures
- Rotate or revoke API keys
- Create or delete projects within a space

## Upfront Questions

For multi-step workflows, **collect all required information before running any `ax` commands**. Use `AskUserQuestion` to avoid back-and-forth mid-workflow. Fetch live data first (e.g. org list) so you can present real options rather than asking the user to recall IDs.

### Onboarding a new team
1. Run `ax organizations list -o json` to get available org names.
2. Use `AskUserQuestion` (single call, up to 4 questions) to gather:
   - **Which org?** — present the org names from the list as options
   - **Space name** — what to call the new team's space
   - **Team members** — names and emails to invite (user can type via "Other"; ask if none yet)
   - **Service key?** — whether to generate a service key for CI/CD pipelines

### Offboarding a user
Ask before running any commands:
- **Which user?** — email address (then look up with `ax users list --email`)

### Restricting a project
Ask before running any commands:
- **Which space and project?** — to look up the project global ID
- **Which users get explicit access?** — emails of users to bind to the restricted project

### Inviting users (standalone)
Ask before running any commands:
- **Name and email** — for each user to invite
- **Role** — `admin`, `member`, or `read-only` (present as options)
- **Invite mode** — `email_link` (default), `temporary_password`, or `none`

### Revoking or rotating an API key
Ask before running any commands:
- **Which key?** — run `ax api-keys list -o json` and present options by name and status; or ask for `KEY_ID`
- **Revoke or rotate?** — `revoke` invalidates immediately; `refresh` issues a new key with the same scope (zero-downtime rotation)

If the user says "delete" an API key, use `ax api-keys revoke` — there is no `delete` subcommand for API keys.

## Concepts

- **Organization** — a named grouping within an account (e.g. one per business unit). Spaces live inside organizations. Users are added to the account first, then to orgs, then to spaces.
- **Space** — a workspace that isolates traces, datasets, and projects. A user must be an org member before they can be added to a space within that org.
- **Role** — a named set of permissions. Predefined roles are system-managed. Custom roles are created by admins. The roles for org/space membership (`admin`, `member`, `read-only`, `annotator`) are separate from custom RBAC roles used with `ax role-bindings`.
- **Role binding** — fine-grained assignment of a custom role to a user on a specific resource (a space or a project).
- **Resource restriction** — marks a project so that only users with an explicit role binding on that project can access it. Roles bound at any higher hierarchy level (space, org, account) are excluded.
- **API key** — either a *user* key (authenticates as the creator, full user permissions) or a *service* key (scoped to a specific space, for automated pipelines).

## Prerequisites

Proceed directly — run the `ax` command you need. Do NOT check versions or profiles upfront.

If an `ax` command fails:
- `command not found` or version error → see [references/ax-setup.md](references/ax-setup.md)
- `401 Unauthorized` / missing API key → run `ax profiles show`; follow [references/ax-profiles.md](references/ax-profiles.md)
- `403 Forbidden` → the active profile lacks admin privileges; ask the user to authenticate with an admin key
- **Security:** Never read `.env` files or search the filesystem for credentials. Use `ax profiles` for Arize credentials. Never echo, log, or display raw API key values.

> **OAuth login option (v0.18.0+):** Users can authenticate via browser-based OAuth PKCE instead of API keys by running `ax auth login` (then `ax auth logout` to revoke). Inform users of this option if they ask about authentication alternatives — do **not** run `ax auth login` yourself, as it opens a browser interactively.

---

## Users

A user must exist in the account before they can be added to an org or space. **Account-level roles:** `admin`, `member`, `annotator`

```bash
ax users list                                  # all users
ax users list --email "jane"                   # substring filter
ax users list --status active                  # active only
ax users list -l 100 -o json                   # paginate, get global IDs

ax users get USER_ID

ax users create \
  --full-name "Jane Doe" \
  --email jane@example.com \
  --role member \
  --invite-mode email_link        # or: none | temporary_password

ax users update USER_ID --full-name "Jane Smith"
ax users update USER_ID --is-developer          # grant developer flag

ax users delete USER_ID --force   # ⚠ confirm first — cascades: org/space memberships, API key revocation, role bindings

ax users resend-invitation USER_ID
ax users reset-password USER_ID
```

---

## Organizations

**Organization roles:** `admin`, `member`, `read-only`, `annotator`

```bash
ax organizations list
ax organizations list --name "platform"
ax organizations list -l 100 -o json

ax organizations get "Platform Team"

ax organizations create --name "Platform Team" --description "Core ML platform"

ax organizations update "Platform Team" --name "ML Platform" --description "Updated"

# Add user (must exist in account first)
ax organizations add-user "Platform Team" --user-id USER_ID --role member

# Remove user (also removes from all child spaces) — ⚠ confirm first
ax organizations remove-user "Platform Team" --user-id USER_ID --force
```

---

## Spaces

**Space roles:** `admin`, `member`, `read-only`, `annotator`

```bash
ax spaces list
ax spaces list --organization-id ORG_ID

ax spaces get "my-workspace"

# --organization-id required; get ORG_ID from ax organizations list -o json
ax spaces create --name "team-alpha" --organization-id ORG_ID

ax spaces update "team-alpha" --name "team-alpha-v2"

ax spaces delete "team-alpha" --force   # ⚠ confirm first — irreversible; deletes all resources

# User must be an org member before being added to a space
ax spaces add-user "team-alpha" --user-id USER_ID --role member
ax spaces remove-user "team-alpha" --user-id USER_ID --force   # ⚠ confirm first
```

---

## Roles

Custom RBAC roles used with `ax role-bindings`. Separate from the simpler `admin`/`member`/`read-only`/`annotator` roles in org/space membership.

```bash
ax roles list                          # all roles
ax roles list --is-custom -o json      # custom only — get stable IDs for SAML mappings
ax roles list --is-predefined

ax roles get "Data Scientist"          # inspect permissions

# --permissions is comma-separated; fully replaces on update
ax roles create \
  --name "Data Scientist" \
  --permissions "PROJECT_READ,DATASET_CREATE,EXPERIMENT_CREATE" \
  --description "Read traces, create datasets and experiments"

ax roles update "Data Scientist" --permissions "PROJECT_READ,DATASET_CREATE,EXPERIMENT_CREATE,EVALUATOR_CREATE"

ax roles delete "Data Scientist" --force   # ⚠ confirm first — predefined roles cannot be deleted
```

**Finding available permissions:** Run `ax roles get <predefined-role> -o json` on a system role (e.g. `Member`, `Admin`) to see valid permission names.

---

## Role Bindings

Fine-grained assignment of a custom role to a user on a specific resource (space or project).

```bash
# Assign at space level
ax role-bindings create \
  --user-id USER_GLOBAL_ID \
  --role-id ROLE_GLOBAL_ID \
  --resource-type SPACE \
  --resource-id SPACE_GLOBAL_ID

# Assign at project level
ax role-bindings create \
  --user-id USER_GLOBAL_ID \
  --role-id ROLE_GLOBAL_ID \
  --resource-type PROJECT \
  --resource-id PROJECT_GLOBAL_ID

ax role-bindings get BINDING_ID
ax role-bindings update BINDING_ID --role-id NEW_ROLE_ID
ax role-bindings delete BINDING_ID --force   # ⚠ confirm first
```

Idempotent — if a binding already exists for the user on that resource, exits without error.

---

## Resource Restrictions

Restricts a **project** so only users with an explicit role binding on that project can access it. Space/org-level roles are excluded.

```bash
ax resource-restrictions restrict --resource-id PROJECT_GLOBAL_ID     # idempotent
ax resource-restrictions unrestrict --resource-id PROJECT_GLOBAL_ID --force   # ⚠ confirm first

# Finding project IDs
ax projects list -l 100 -o json --space "my-workspace"
```

---

## API Keys

> **Scope:** `ax api-keys list` returns only keys owned by the **authenticated user**. For org-wide auditing, use the Arize UI (Settings > API Keys).

```bash
ax api-keys list
ax api-keys list --key-type service --status active -o json

# User key — authenticates as creator, inherits their full permissions
ax api-keys create --name "CI pipeline" --expires-at "2027-01-01T00:00:00"

# Service key — space-scoped bot user (recommended for CI/CD pipelines)
ax api-keys create-service-key \
  --name "team-alpha-traces" \
  --space "team-alpha" \
  --space-role member \
  --expires-at "2027-01-01T00:00:00"

ax api-keys revoke KEY_ID --force   # ⚠ confirm first — invalidates the key immediately

# Zero-downtime rotation — revokes old key, issues new one with same scope
ax api-keys refresh KEY_ID
ax api-keys refresh KEY_ID --expires-at "2028-01-01T00:00:00"
```

> **The raw key is displayed once.** Save it immediately in your secrets manager. It cannot be retrieved again.

**`create-service-key` flags:**

| Flag | Required | Description |
|------|----------|-------------|
| `--name` | yes | Key name |
| `--space` | yes | Space this service key is scoped to |
| `--space-role` | no | Role in the space: `admin`, `member`, `read-only` |
| `--org-role` | no | Role in the parent organization |
| `--account-role` | no | Role at account level |
| `--expires-at` | no | ISO 8601 expiry date |
| `--description` | no | Optional description |

---

## Projects

Projects live inside spaces and contain traces, datasets, and experiments.

```bash
ax projects list --space SPACE
ax projects list --space SPACE --name "playground"   # substring filter
ax projects list --space SPACE -l 100 -o json        # get base64 IDs

ax projects get NAME_OR_ID --space SPACE

ax projects create --name "my-project" --space SPACE

ax projects delete NAME_OR_ID --space SPACE --force   # ⚠ confirm first — deletes all traces and datasets
```

> **Note:** Project IDs (base64 strings) are used by `ax spans export`, `ax traces export`, and `ax resource-restrictions`. If commands reject a project name, look up the `id` field from `ax projects list -o json` and use that instead.

---

## Enterprise Workflows & Troubleshooting

Step-by-step workflows (onboard a team, SAML/SSO mappings, project restriction, offboarding, multi-tenant keys) and a troubleshooting table are in [references/REFERENCE.md](references/REFERENCE.md).

---

## Related Skills

- **arize-instrumentation**: Set up tracing in an LLM app once a space is ready.
- **arize-trace**: Export and inspect traces within a managed space.
- **arize-dataset**: Create and manage datasets within a space.
