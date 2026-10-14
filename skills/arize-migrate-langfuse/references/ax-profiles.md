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

To use a named profile with any `ax` command, add `-p NAME`:
```bash
ax spans export PROJECT -p work
```

## 4. Getting the API key

**Never ask the user to paste their API key into the chat, and never read, log, echo, or pass an API key value.** Don't inspect `ARIZE_API_KEY` or other key variables (no `echo`, `env`, or reading `.env` files), don't ask the user to export one for `ax`, and don't run any command that takes `--api-key`. `ax` doesn't read the variable anyway; it authenticates only through a profile.

Instead, ask the user to run `ax profiles create` in **their own terminal**, not through your shell tool or a `!` command (both put the output in your context). The wizard prompts for the key, so it never appears in a command or in this conversation.

They can find their key at https://app.arize.com/admin > API Keys. Recommend they create a **scoped service key** (not a personal user key) — service keys are not tied to an individual account and are safer for programmatic use. Keys are space-scoped — make sure they copy the key for the correct space.

To replace a wrong or expired key, have them create a new profile the same way (for example `ax profiles create work`); it becomes the active one.

Once the user confirms the wizard finished, verify as in section 5.

## 5. Verify

After any create or update:

```bash
ax profiles show
```

Confirm the API key and region are correct, then retry the original command.

## Space

There is no profile flag for space. Save it as an environment variable — accepts a space **name** (e.g., `my-workspace`) or a base64 space **ID** (e.g., `U3BhY2U6...`). Find yours with `ax spaces list -o json`.

**macOS/Linux** — add to `~/.zshrc` or `~/.bashrc`:
```bash
export ARIZE_SPACE="my-workspace"    # name or base64 ID
```
Then `source ~/.zshrc` (or restart terminal).

**Windows (PowerShell):**
```powershell
[System.Environment]::SetEnvironmentVariable('ARIZE_SPACE', 'my-workspace', 'User')
```
Restart terminal for it to take effect.

## Save Credentials for Future Use

At the **end of the session**, if the user manually provided any credentials during this conversation **and** those values were NOT already loaded from a saved profile or environment variable, offer to save them.

**Skip this entirely if:**
- The API key was already loaded from an existing profile
- The space was already set via `ARIZE_SPACE` env var
- The user only used base64 project IDs (no space was needed)

**How to offer:** Use **AskQuestion**: *"Would you like to save your Arize credentials so you don't have to enter them next time?"* with options `"Yes, save them"` / `"No thanks"`.

**If the user says yes:**

1. **API key** — Run `ax profiles show` to check the current state. If no profile holds the key, ask the user to run `ax profiles create` in their own terminal (see section 4). Never pass a key value yourself.

2. **Space** — See the Space section above to persist it as an environment variable.
