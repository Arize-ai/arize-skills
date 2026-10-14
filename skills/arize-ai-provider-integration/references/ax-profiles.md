# ax Profile Setup

Consult this when authentication fails (401, missing profile, missing API key). Do NOT run these checks proactively.

Use this when there is no profile, or a profile has incorrect settings (wrong API key, wrong region, etc.).

## 1. Inspect the current state

```bash
ax profiles show
```

Look at the output to understand what's configured:
- `API Key: (not set)` or missing → key needs to be created/updated
- No profile output or "No profiles found" → no profile exists yet
- Connected but getting `401 Unauthorized` → key is wrong or expired
- Connected but wrong endpoint/region → region needs to be updated

## 2. Fix a misconfigured profile

If a profile exists but one or more settings are wrong, patch only what's broken.

Profile region controls API and Flight routing for `ax` commands. Prefer `--region` over hard-coding SaaS hosts; examples include `us-central-1a`, `us-east-1b`, `eu-west-1a`, and `ca-central-1a`. It does not configure where a separately running app exports traces.

For EU and Canada, `--region eu-west-1a` and `--region ca-central-1a` automatically set `flight_host` to `flight.eu-west-1a.arize.com` or `flight.ca-central-1a.arize.com` and `flight_port` to `443`. Do not set those fields separately for standard SaaS profiles. Set them directly only for custom/private routing, using interactive profile setup or a complete `--from-file` profile; keep `flight_host` hostname-only (no `:443`) and set `flight_port` separately.

**Never handle the API key yourself.** A wrong or expired key is fixed by the user in their own terminal (see section 4). Settings with no secret in them are safe to fix directly:

```bash
# Fix the region (no secret involved — safe to run directly)
ax profiles update --region us-east-1b
```

`update` only changes the fields you specify — all other settings are preserved. If no profile name is given, the active profile is updated.

## 3. Create a new profile

If no profile exists, or if the existing profile needs to point to a completely different setup (different org, different region):

Ask the user to run the interactive wizard in their own terminal (see section 4). Don't run it yourself: it prompts for the API key.

```bash
ax profiles create        # creates 'default' when no profiles exist
ax profiles create work   # a named profile
```

The wizard also asks for the region, and its **Advanced → Single endpoint** option covers on-prem deployments. Creating a profile makes it the active one.

To switch between profiles later, use `ax profiles use NAME` (see **Managing Multiple Profiles** below).

## 4. Getting the API key

**Never ask the user to paste their API key into the chat, and never read, log, echo, or pass an API key value.** Don't inspect `ARIZE_API_KEY` or other key variables (no `echo`, `env`, or reading `.env` files), don't ask the user to export one for `ax`, and don't run any command that takes `--api-key`. Never suggest a profile that references an environment variable (`${ARIZE_API_KEY}` in the profile or a `--from-file` TOML): `ax` resolves it on every run, which keeps the key in the environment.

Instead, ask the user to run `ax profiles create` in **their own terminal**, not through your shell tool or a `!` command (both put the output in your context). The wizard prompts for the key, so it never appears in a command or in this conversation. If `ARIZE_API_KEY` is set in their shell, the wizard offers to create the profile from it (default yes); tell them to answer **No**, or `unset ARIZE_API_KEY` first, so the key is stored in the profile.

They can find their key at https://app.arize.com/admin > API Keys. Recommend they create a **scoped service key** (not a personal user key) — service keys are not tied to an individual account and are safer for programmatic use. Keys are space-scoped — make sure they copy the key for the correct space.

To replace a wrong or expired key, have them create a new profile the same way (for example `ax profiles create work`); it becomes the active one.

Once the user confirms the wizard finished, verify as in section 5.

## 5. Verify

After any create or update:

```bash
ax profiles show

# Or validate connectivity and configuration explicitly:
ax profiles validate
```

Confirm the API key and region are correct, then retry the original command.

## Managing Multiple Profiles

List all available profiles, with the active one marked:

```bash
ax profiles list
```

Switch to a different profile:

```bash
ax profiles use work
```

Delete a profile. You cannot delete the currently active profile; switch to another first if needed.

```bash
ax profiles delete staging --force
```

## Space

The CLI has no default space. Pass `-s`/`--space` (name or base64 ID) whenever a resource is given by **name**, or it fails with `project '...' not found. Provide 'space'`.

Resolve it once per session; first match wins:

1. The space the user named.
1. `ARIZE_SPACE_ID` (the tracing space; not a secret): `echo "$ARIZE_SPACE_ID"`, else `grep -E '^ARIZE_SPACE_ID=' .env` — read only that line.
1. `ax spaces list -o json`: use the only space, otherwise ask the user to pick a name.

Tell the user which space you used and why.

```bash
ax spans export my-project --space "$ARIZE_SPACE_ID"
```

## Save Credentials for Future Use

At the **end of the session**, if the user manually provided any credentials during this conversation **and** those values were NOT already loaded from a saved profile or environment variable, offer to save them.

**Skip this entirely if:**
- The API key was already loaded from an existing profile
- The user only used base64 project/space IDs and never needed to persist a space

**How to offer:** Use **AskQuestion**: *"Would you like to save your Arize credentials so you don't have to enter them next time?"* with options `"Yes, save them"` / `"No thanks"`.

**If the user says yes:**

1. **API key** — Run `ax profiles show` to check the current state. If no profile holds the key, ask the user to run `ax profiles create` in their own terminal (see section 4). Never pass a key value yourself.
