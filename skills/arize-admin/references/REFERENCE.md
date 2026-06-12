# Arize Admin — Enterprise Workflows & Troubleshooting

## Workflow 1: Onboard a New Team

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

## Workflow 2: Configure SAML/SSO Role Mappings

SAML group-to-role mappings require stable role IDs. Retrieve them:

```bash
# List all custom roles with their IDs
ax roles list --is-custom -o json

# Get a specific role's ID and permissions
ax roles get "Data Scientist" -o json
```

Use the `id` field (base64 string like `Um9sZTo1...`) in your SAML `values.yaml` or IdP attribute mapping. These IDs are stable and do not change unless the role is deleted and recreated.

## Workflow 3: Restrict a Project to Specific Users

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

## Workflow 4: Audit Access

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

> **CLI audit limitations:** `ax` cannot enumerate role bindings (no `list` subcommand) or other users' API keys. For a full access audit, use the Arize UI (Settings > Users & Permissions and Settings > API Keys).

## Workflow 5: Offboard a User

`ax users delete` cascades to all org memberships, space memberships, API keys, and role bindings in one operation.

**Always confirm with the user before running the delete.** Summarize the cascade impact, then ask for explicit confirmation.

```bash
# 1. Find the user's global ID
ax users list --email "jane@example.com" -o json

# 2. Confirm with the user: "Delete jane@example.com? This will cascade-remove
#    all org/space memberships, API keys, and role bindings."

# 3. After user confirms, delete
ax users delete USER_ID --force
```

If you also need to deactivate the user in your IdP (to prevent SSO re-login), do that separately in Okta/Azure AD/etc. For real-time automated key invalidation on IdP deactivation, configure SCIM 2.0 provisioning.

## Workflow 6: Multi-Tenant Service Key Management

One service key per tenant space — scoped permissions, no org-admin required:

```bash
# Create a service key per tenant space
ax api-keys create --name "tenant-acme-key" --key-type service --space "tenant-acme"
ax api-keys create --name "tenant-beta-key" --key-type service --space "tenant-beta"

# Revoke a key (immediate invalidation)
ax api-keys list --key-type service -o json   # find KEY_ID by name
ax api-keys revoke KEY_ID --force

# Rotate a key (zero-downtime, same scope)
ax api-keys refresh KEY_ID
```

Service keys can only write traces to their scoped space — they cannot access other spaces or perform admin operations.

---

## Troubleshooting

| Error | Cause | Fix |
|---|---|---|
| `403 Forbidden` | Profile lacks admin privileges | Authenticate with an admin API key (`ax profiles update --api-key $ARIZE_API_KEY`) |
| `401 Unauthorized` | Missing or invalid API key | See [ax-profiles.md](ax-profiles.md) |
| Role binding already exists | Idempotent — not an error | Safe to ignore; the existing binding is unchanged |
| User not found in space add-user | User not yet an org member | Run `ax organizations add-user` first, then `ax spaces add-user` |
| Role create fails with duplicate name | Name already in use | Use `ax roles list --is-custom` to find the existing role |
| Service key create fails | `--space` missing or space doesn't exist | Verify with `ax spaces list`; `--space` is required for service keys |
| Key value not saved | Raw key was not captured at creation | Refresh the key: `ax api-keys refresh KEY_ID` |
| `Unknown command delete` on `ax api-keys` | `delete` was removed; use `revoke` instead | `ax api-keys revoke KEY_ID --force` |
