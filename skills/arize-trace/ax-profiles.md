# ax Profile Setup

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

If a profile exists but one or more settings are wrong, patch only what's broken:

```bash
# Fix the API key
ax profiles update --api-key NEW_API_KEY

# Fix the region
ax profiles update --region us-east-1b

# Fix both at once
ax profiles update --api-key NEW_API_KEY --region us-east-1b
```

`update` only changes the fields you specify — all other settings are preserved. If no profile name is given, the active profile is updated.

## 3. Create a new profile

If no profile exists, or if the existing profile needs to point to a completely different setup (different org, different region):

```bash
# Create the default profile (no prompt if no profiles exist yet)
ax profiles create --api-key API_KEY

# Create with a region
ax profiles create --api-key API_KEY --region us-east-1b

# Create a named profile (for a different setup alongside the default)
ax profiles create work --api-key API_KEY --region us-east-1b
```

To use a named profile with any `ax` command, add `-p NAME`:
```bash
ax spans export PROJECT_ID -p work
```

## 4. Where to get the API key

Go to **https://app.arize.com/admin > API Keys**. API keys are scoped per space — make sure you're using the key for the correct space.

## 5. Verify

After any create or update:

```bash
ax profiles show
```

Confirm the API key and region are correct, then retry the original command.

## Space ID

There is no profile flag for space ID. Save it as an environment variable:

**macOS/Linux** — add to `~/.zshrc` or `~/.bashrc`:
```bash
export ARIZE_SPACE_ID="U3BhY2U6..."
```
Then `source ~/.zshrc` (or restart terminal).

**Windows (PowerShell):**
```powershell
[System.Environment]::SetEnvironmentVariable('ARIZE_SPACE_ID', 'U3BhY2U6...', 'User')
```
Restart terminal for it to take effect.
