---
name: arize-admin
description: Manages Arize users, organizations, spaces, roles, role bindings, resource restrictions, and API keys via the ax CLI. Use for enterprise admin workflows: inviting and offboarding users, onboarding new teams, creating custom roles for SAML/SSO mappings, assigning roles to users, restricting project-level access, and managing service keys for multi-tenant architectures. Covers ax users, ax organizations, ax spaces, ax roles, ax role-bindings, ax resource-restrictions, and ax api-keys.
metadata:
  author: arize
  version: "1.0"
compatibility: Requires the ax CLI (≥ 0.14.0) and a configured Arize profile with org-admin privileges.
---

# Arize Admin Skill

Programmatic management of Arize users, organizations, spaces, roles, permissions, and API keys — the building blocks for enterprise access control.

> **Privilege requirement:** Most operations in this skill require **org-admin** or **account-admin** privileges. If commands return `403 Forbidden`, the authenticated profile does not have sufficient permissions.

## When to Use

- Invite users to the account, assign them to orgs and spaces
- Offboard a user and revoke all their access in one command
- Onboard a new team: create a space, create a custom role, assign users, generate a service key
- Create custom roles for SAML/SSO attribute mappings (need stable role IDs)
- List roles and their IDs to configure an IdP
- Assign or change a user's role in a space or on a project
- Restrict a project so only explicitly bound users can access it
- Create scoped service keys for CI/CD pipelines or multi-tenant architectures
- Rotate or revoke API keys

## Concepts

- **Organization** — a named grouping within an account (e.g. one per business unit). Spaces live inside organizations. Users are added to the account first, then to orgs, then to spaces.
- **Space** — a workspace that isolates traces, datasets, and projects. A user must be an org member before they can be added to a space within that org.
- **Role** — a named set of permissions. Predefined roles are system-managed. Custom roles are created by admins. The roles for org/space membership (`admin`, `member`, `read-only`, `annotator`) are separate from custom RBAC roles used with `ax role-bindings`.
- **Role binding** — fine-grained assignment of a custom role to a user on a specific resource (a space or a project).
- **Resource restriction** — marks a project so that only users with an explicit role binding on that project can access it. Space-level roles are excluded.
- **API key** — either a *user* key (authenticates as the creator, full user permissions) or a *service* key (scoped to a specific space, for automated pipelines).

## Prerequisites

Proceed directly — run the `ax` command you need. Do NOT check versions or profiles upfront.

If an `ax` command fails:
- `command not found` or version error → see [references/ax-setup.md](references/ax-setup.md)
- `401 Unauthorized` / missing API key → run `ax profiles show`; follow [references/ax-profiles.md](references/ax-profiles.md)
- `403 Forbidden` → the active profile lacks admin privileges; ask the user to authenticate with an admin key
- **Security:** Never read `.env` files or search the filesystem for credentials. Use `ax profiles` for Arize credentials. Never echo, log, or display raw API key values.

---

## Users

Manage account-level users. A user must exist in the account before they can be added to an org or space.

**Account-level roles:** `admin`, `member`, `annotator`

### List

```bash
ax users list                                  # all users
ax users list --email "jane"                   # substring filter on email
ax users list --status active                  # active users only
ax users list --status invited                 # pending invitations
ax users list -l 100 -o json                   # paginate, get global IDs
```

Use `ax users list -o json` to look up a user's global ID (base64) for use with `ax role-bindings`, `ax organizations add-user`, and `ax spaces add-user`.

### Get

```bash
ax users get USER_ID                           # by global base64 ID
```

### Create (invite)

Creates the user account and optionally sends an invitation.

```bash
# Send an email invitation
ax users create \
  --full-name "Jane Doe" \
  --email jane@example.com \
  --role member \
  --invite-mode email_link

# Create without sending an invite (e.g. for SSO/JIT provisioning)
ax users create \
  --full-name "Jane Doe" \
  --email jane@example.com \
  --role member \
  --invite-mode none

# Send a temporary password instead of a link
ax users create \
  --full-name "Jane Doe" \
  --email jane@example.com \
  --role admin \
  --invite-mode temporary_password
```

**Invite modes:**

| Mode                 | Description                                      |
|----------------------|--------------------------------------------------|
| `none`               | Create the user without sending any invitation   |
| `email_link`         | Send an invitation email with a sign-in link     |
| `temporary_password` | Send an email with a one-time temporary password |

### Update

```bash
ax users update USER_ID --full-name "Jane Smith"
ax users update USER_ID --is-developer          # grant developer flag
ax users update USER_ID --no-is-developer       # revoke developer flag
```

### Delete

Deletes the user and **cascades to all organization memberships, space memberships, API keys, and role bindings**. This is the primary offboarding command.

```bash
ax users delete USER_ID --force
```

Get `USER_ID` from `ax users list -o json`.

### Re-invite / Reset password

```bash
ax users resend-invitation USER_ID    # resend invite to a pending user
ax users reset-password USER_ID       # send a password-reset email
```

---

## Organizations

**Organization roles:** `admin`, `member`, `read-only`, `annotator`

### List

```bash
ax organizations list
ax organizations list --name "platform"        # substring filter
ax organizations list -l 100 -o json
```

### Get

```bash
ax organizations get "Platform Team"           # by name
ax organizations get ORG_ID                    # by base64 ID
```

### Create

```bash
ax organizations create --name "Platform Team" --description "Core ML platform"
```

Names must be unique within the account.

### Update

```bash
ax organizations update "Platform Team" --name "ML Platform" --description "Updated desc"
ax organizations update ORG_ID --description ""   # clear description
```

### Add / remove users

Add a user to an org (or update their role if already a member). The user must exist in the account — create them first with `ax users create` if needed.

```bash
ax organizations add-user "Platform Team" --user-id USER_ID --role member
ax organizations add-user "Platform Team" --user-id USER_ID --role admin
```

Remove a user from an org. **Also removes them from all child spaces within that org.**

```bash
ax organizations remove-user "Platform Team" --user-id USER_ID --force
```

---

## Spaces

**Space roles:** `admin`, `member`, `read-only`, `annotator`

### List

```bash
ax spaces list
ax spaces list --organization-id ORG_ID        # filter to one org
ax spaces list -l 100 -o json
```

### Get

```bash
ax spaces get "my-workspace"
ax spaces get U3BhY2U6...                       # base64 ID
```

### Create

`--organization-id` is required. Get the org ID from `ax organizations list -o json`.

```bash
ax spaces create --name "team-alpha" --organization-id ORG_ID
ax spaces create --name "team-alpha" --organization-id ORG_ID --description "Alpha team workspace"
```

### Update

```bash
ax spaces update "team-alpha" --name "team-alpha-v2"
ax spaces update SPACE_ID --description "Updated description"
```

### Delete

Deletes the space **and all resources within it** (traces, datasets, projects, etc.). Irreversible.

```bash
ax spaces delete "team-alpha" --force       # --force skips confirmation
```

### Add / remove users

The user must already be a member of the space's **parent organization** before they can be added to a space.

```bash
ax spaces add-user "team-alpha" --user-id USER_ID --role member
ax spaces add-user "team-alpha" --user-id USER_ID --role admin
```

Remove a user from a space (does not remove them from the parent org).

```bash
ax spaces remove-user "team-alpha" --user-id USER_ID --force
```

---

## Roles

Custom RBAC roles used with `ax role-bindings` for fine-grained project/space access control. Separate from the simpler `admin`/`member`/`read-only`/`annotator` roles used in org and space membership.

### List

```bash
ax roles list                          # all roles (predefined + custom)
ax roles list --is-predefined          # system roles only
ax roles list --is-custom              # custom roles only
ax roles list -l 100 -o json           # paginate — get IDs for SAML mappings
```

Use `--is-custom -o json` to retrieve stable role IDs for SAML attribute mapping in your IdP config.

### Get

```bash
ax roles get "Data Scientist"
ax roles get ROLE_ID                   # by base64 ID
```

Returns the role's permissions list — inspect a predefined role to discover available permission names.

### Create

`--permissions` is comma-separated. At least one permission is required. Names must be unique within the account.

```bash
ax roles create \
  --name "Data Scientist" \
  --permissions "PROJECT_READ,DATASET_CREATE,EXPERIMENT_CREATE" \
  --description "Read traces, create datasets and experiments — no admin"

ax roles create \
  --name "Trace Writer" \
  --permissions "PROJECT_READ,TRACE_CREATE" \
  --description "Service accounts that send traces only"
```

**Finding available permissions:** Run `ax roles get <predefined-role> -o json` on a system role (e.g. `Member`, `Admin`) to see its full permission set — those names are valid for custom roles.

### Update

When `--permissions` is provided, it **fully replaces** the existing permission set (not additive).

```bash
ax roles update "Data Scientist" --permissions "PROJECT_READ,DATASET_CREATE,EXPERIMENT_CREATE,EVALUATOR_CREATE"
ax roles update "Data Scientist" --name "ML Engineer" --description "Updated scope"
```

Predefined (system) roles cannot be updated.

### Delete

```bash
ax roles delete "Data Scientist" --force
```

Predefined roles cannot be deleted.

---

## Role Bindings

Fine-grained assignment of a custom role to a user on a specific resource (space or project). Use this when the simpler org/space membership roles (`admin`, `member`, etc.) aren't granular enough.

> **No list command:** `ax role-bindings` does not have a `list` subcommand. To enumerate all bindings on a resource, use the Arize UI (Settings > Users & Permissions). You can only `get` a binding if you already know its ID.

> **Getting user IDs:** Run `ax users list -o json` to get a user's global base64 ID for use with `--user-id`.

### Create

```bash
# Assign a role at the space level
ax role-bindings create \
  --user-id USER_GLOBAL_ID \
  --role-id ROLE_GLOBAL_ID \
  --resource-type SPACE \
  --resource-id SPACE_GLOBAL_ID

# Assign a role at the project level (for fine-grained access)
ax role-bindings create \
  --user-id USER_GLOBAL_ID \
  --role-id ROLE_GLOBAL_ID \
  --resource-type PROJECT \
  --resource-id PROJECT_GLOBAL_ID
```

Idempotent — if a binding already exists for the user on that resource, the command exits without error.

### Get

```bash
ax role-bindings get BINDING_ID
```

### Update (change the assigned role)

```bash
ax role-bindings update BINDING_ID --role-id NEW_ROLE_ID
```

### Delete (revoke access)

```bash
ax role-bindings delete BINDING_ID --force
```

---

## Resource Restrictions

Restricts a **project** so that only users with an explicit role binding on that project can access it. Roles bound at the space, org, or account level are excluded from that project.

Currently only `PROJECT` resources are supported.

### Restrict a project

```bash
ax resource-restrictions restrict --resource-id PROJECT_GLOBAL_ID
```

Idempotent — safe to run even if already restricted.

### Unrestrict a project

Removes the restriction so space-level roles apply again.

```bash
ax resource-restrictions unrestrict --resource-id PROJECT_GLOBAL_ID --force
```

### Finding project IDs

```bash
ax projects list -l 100 -o json --space "my-workspace"
```

Use the `id` field (base64) as `--resource-id`.

---

## API Keys

> **Scope:** `ax api-keys list` returns only keys owned by the **authenticated user**. There is no CLI command to list or revoke another user's keys. For org-wide key auditing, use the Arize UI (Settings > API Keys).

### List

```bash
ax api-keys list                              # your own keys
ax api-keys list --key-type service           # service keys only
ax api-keys list --key-type user              # user keys only
ax api-keys list --status active              # active only
ax api-keys list --status deleted             # deleted/revoked keys
ax api-keys list -l 50 -o json
```

### Create

Two key types:

**User key** — authenticates as the creating user, inherits their full permissions. No space scope.

```bash
ax api-keys create --name "CI pipeline" --key-type user --expires-at "2027-01-01T00:00:00"
```

**Service key** — scoped to a specific space. Safe for automated pipelines and multi-tenant setups.

```bash
ax api-keys create \
  --name "team-alpha-traces" \
  --key-type service \
  --space "team-alpha" \
  --description "Trace writer for team-alpha CI/CD"

# With expiration (recommended for rotation schedules)
ax api-keys create \
  --name "team-alpha-traces" \
  --key-type service \
  --space "team-alpha" \
  --expires-at "2027-01-01T00:00:00"
```

> **The raw key is displayed once.** Save it immediately in your secrets manager (e.g. GitHub Actions secret, Vault). It cannot be retrieved again.

### Delete (revoke)

```bash
ax api-keys delete KEY_ID --force
```

### Refresh (zero-downtime rotation)

Atomically revokes the old key and issues a new one with the same name, type, and scope.

```bash
ax api-keys refresh KEY_ID
ax api-keys refresh KEY_ID --expires-at "2028-01-01T00:00:00"   # new expiration
```

Get `KEY_ID` from `ax api-keys list -o json`.

---

## Enterprise Workflows

### Workflow 1: Onboard a New Team

```bash
# 1. Get the org ID
ax organizations list -o json

# 2. Create a space for the team
ax spaces create --name "team-alpha" --organization-id ORG_ID

# 3. Create or reuse a custom role
ax roles create \
  --name "Data Scientist" \
  --permissions "PROJECT_READ,DATASET_CREATE,EXPERIMENT_CREATE" \
  --description "Read traces, create datasets and run experiments"

# 4. Get stable role IDs (for SAML mappings or role bindings)
ax roles list --is-custom -o json

# 5. Invite team members (or look up existing users)
ax users create \
  --full-name "Jane Doe" \
  --email jane@example.com \
  --role member \
  --invite-mode email_link

# 6. Get the user's global ID
ax users list --email "jane@example.com" -o json

# 7. Add the user to the org
ax organizations add-user "Platform Team" --user-id USER_ID --role member

# 8. Add the user to the space
ax spaces add-user "team-alpha" --user-id USER_ID --role member

# 9. Create a service key for the team's CI/CD pipeline
ax api-keys create \
  --name "team-alpha-service-key" \
  --key-type service \
  --space "team-alpha"
```

### Workflow 2: Configure SAML/SSO Role Mappings

SAML group-to-role mappings require stable role IDs. Retrieve them:

```bash
# List all custom roles with their IDs
ax roles list --is-custom -o json

# Get a specific role's ID and permissions
ax roles get "Data Scientist" -o json
```

Use the `id` field (base64 string like `Um9sZTo1...`) in your SAML `values.yaml` or IdP attribute mapping. These IDs are stable and do not change unless the role is deleted and recreated.

### Workflow 3: Restrict a Project to Specific Users

For fine-grained access where only certain users should see a project within a shared space:

```bash
# 1. Find the project ID
ax projects list -l 100 -o json --space "team-alpha"

# 2. Restrict the project (excludes space-level roles)
ax resource-restrictions restrict --resource-id PROJECT_GLOBAL_ID

# 3. Find the user's global ID
ax users list --email "jane@example.com" -o json

# 4. Find the role ID to assign
ax roles list --is-custom -o json

# 5. Explicitly grant access to allowed users on that project
ax role-bindings create \
  --user-id USER_GLOBAL_ID \
  --role-id ROLE_GLOBAL_ID \
  --resource-type PROJECT \
  --resource-id PROJECT_GLOBAL_ID
```

### Workflow 4: Audit Access

```bash
# List all users and their status
ax users list -l 100 -o json

# List all custom roles with their permissions
ax roles list --is-custom -o json

# Inspect a specific role's permission set
ax roles get "Data Scientist" -o json

# List your own active API keys
ax api-keys list --status active -o json
```

> **CLI audit limitations:** `ax` cannot enumerate role bindings (no `list` subcommand) or other users' API keys. For a full access audit — who has which role on which space/project, and all org-wide API keys — use the Arize UI (Settings > Users & Permissions and Settings > API Keys).

### Workflow 5: Offboard a User

`ax users delete` cascades to all org memberships, space memberships, API keys, and role bindings in one operation:

```bash
# 1. Find the user's global ID
ax users list --email "jane@example.com" -o json

# 2. Delete the user (cascades everything)
ax users delete USER_ID --force
```

If you also need to deactivate the user in your IdP (to prevent SSO re-login), do that separately in Okta/Azure AD/etc. For real-time automated key invalidation on IdP deactivation, configure SCIM 2.0 provisioning.

### Workflow 6: Multi-Tenant Service Key Management

One service key per tenant space — scoped permissions, no org-admin required:

```bash
# Create a service key per tenant space
ax api-keys create --name "tenant-acme-key" --key-type service --space "tenant-acme"
ax api-keys create --name "tenant-beta-key" --key-type service --space "tenant-beta"

# Rotate a key (zero-downtime, same scope)
ax api-keys list --key-type service -o json   # find KEY_ID by name
ax api-keys refresh KEY_ID
```

Service keys can only write traces to their scoped space — they cannot access other spaces or perform admin operations.

---

## Troubleshooting

| Error | Cause | Fix |
|---|---|---|
| `403 Forbidden` | Profile lacks admin privileges | Authenticate with an admin API key (`ax profiles update --api-key $ARIZE_API_KEY`) |
| `401 Unauthorized` | Missing or invalid API key | See references/ax-profiles.md |
| Role binding already exists | Idempotent — not an error | Safe to ignore; the existing binding is unchanged |
| User not found in space add-user | User not yet an org member | Run `ax organizations add-user` first, then `ax spaces add-user` |
| Role create fails with duplicate name | Name already in use | Use `ax roles list --is-custom` to find the existing role |
| Service key create fails | `--space` missing or space doesn't exist | Verify with `ax spaces list`; `--space` is required for service keys |
| Key value not saved | Raw key was not captured at creation | Refresh the key: `ax api-keys refresh KEY_ID` |

## Related Skills

- **arize-instrumentation**: Set up tracing in an LLM app once a space is ready.
- **arize-trace**: Export and inspect traces within a managed space.
- **arize-dataset**: Create and manage datasets within a space.
