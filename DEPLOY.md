# Deploy LitExtract

Two paths. **Path A is recommended** if you don't already have the
GitHub or Hugging Face CLIs installed.

---

## Path A — Web UI only (no CLI installs)

You'll do this once, takes ~10 minutes total.

### Step 1 — Push to GitHub

The local repo is already initialized and committed. You only need to
create the empty repo on GitHub and push.

1. **Create the empty repo:** open <https://github.com/new>
   - Owner: `prabhu2k7` (your account)
   - Repository name: `LitExtract`
   - Visibility: **Public**
   - DO NOT initialize with README, .gitignore, or LICENSE — we already
     have them locally
   - Click **Create repository**

2. **Copy the URL** GitHub shows on the next page (something like
   `https://github.com/prabhu2k7/LitExtract.git`).

3. **Push from your terminal** (in the repo root):
   ```bash
   git remote add origin https://github.com/prabhu2k7/LitExtract.git
   git branch -M main
   git push -u origin main
   ```
   GitHub will prompt you to log in via browser the first time.

After this step your code is at
<https://github.com/prabhu2k7/LitExtract>.

### Step 2 — Deploy to Hugging Face Spaces

1. **Sign up / sign in:** <https://huggingface.co/join> (free, no credit
   card).

2. **Create a new Space:** <https://huggingface.co/new-space>
   - Owner: your HF username
   - Space name: `LitExtract`
   - License: `agpl-3.0`
   - SDK: **Docker** → **Blank** (don't pick a template)
   - Hardware: **CPU basic (free)**
   - Visibility: **Public**
   - Click **Create Space**.

3. **Link it to your GitHub repo** (so HF auto-pulls when you push to
   GitHub):

   On the Space page → **Settings** → scroll to **"Sync with GitHub"**
   → click **"Configure repo"** → choose
   `prabhu2k7/LitExtract`, branch `main` → **Save**.

   HF will pull the repo and start building from the `Dockerfile`. The
   YAML frontmatter at the top of `README.md` tells HF this is a Docker
   Space on port 7860.

4. **Wait for the build** — first build takes 5–10 minutes (you'll see
   the live build log on the Space page). When it finishes you'll have
   a public URL:

   ```
   https://prabhu2k7-litextract.hf.space
   ```

5. **Done.** Share that URL with your pharma evaluator. They'll be
   prompted for an OpenAI key on first upload — your wallet stays
   intact.

### Step 3 (optional) — Lock CORS for production

Once you know the public URL, set it as an env var on the HF Space:

- Space page → **Settings** → **Variables and secrets** → **New variable**
- Name: `ALLOWED_ORIGINS`
- Value: `https://prabhu2k7-litextract.hf.space`

This restricts CORS to your Space URL only (instead of the dev defaults).
HF Spaces will rebuild and pick it up.

---

## Path B — CLI (faster for repeat deploys)

If you'd rather drive everything from the terminal:

```bash
# One-time installs
winget install GitHub.cli                                        # GitHub CLI
pip install huggingface_hub                                      # HF Python client

# One-time auth
gh auth login                                                    # OAuth
huggingface-cli login                                            # paste token from https://huggingface.co/settings/tokens

# Create + push GitHub repo
gh repo create prabhu2k7/LitExtract --public --source=. --push

# Create the HF Space (one time)
huggingface-cli repo create LitExtract --type space --space_sdk docker

# Push to the HF Space
git remote add hf https://huggingface.co/spaces/<your-hf-username>/LitExtract
git push hf main
```

After the first deploy, just use:

```bash
git push origin main      # to GitHub
git push hf main          # to Hugging Face (triggers rebuild)
```

Or set up the GitHub→HF auto-sync from Path A Step 2 and just `git push
origin main`.

---

## Verifying the deploy

Once the HF Space build finishes, hit these endpoints to verify:

| Endpoint | Expected |
|---|---|
| `https://<space-url>/` | React app loads |
| `https://<space-url>/api/health` | `{"ok":true,"model":"gpt-4o-mini","provider":"openai","byok_required":true}` |
| `https://<space-url>/api/test-key` (POST, no header) | `{"ok":false,"reason":"missing"}` |

The `byok_required: true` confirms the Space is in BYOK mode (no
server-side OpenAI key set) — your wallet stays out of the loop.

---

## Updating the deployed Space

Any time you want to ship a change:

```bash
# make your edits
git add -A
git commit -m "describe the change"
git push origin main          # GitHub
# HF Spaces auto-pulls if you set up Path A Step 2 sync — otherwise:
git push hf main              # manual push
```

HF rebuilds automatically. The build log shows in the **Logs** tab on the
Space page.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Build fails on HF with "ModuleNotFoundError" | A new dep wasn't added to `requirements.txt`. Add it, commit, push. |
| Frontend shows 404 on a deep link (e.g. `/biomarkers`) | The SPA fallback should catch this — verify `frontend/dist/index.html` exists in the image. Run `docker build -t litextract . && docker run litextract ls -la frontend/dist/` to check. |
| HF Space stuck on "building" forever | Push a trivial change (e.g. add a newline to README) to trigger a rebuild. Or restart the Space from the **Settings** tab. |
| 401 errors on every upload | The user's API key is invalid or expired — check the **Settings** page in the UI and re-paste. |
| CORS errors in browser console | `ALLOWED_ORIGINS` env on the Space doesn't include the URL the browser is using. Update it. |
| Space goes to sleep | Free tier on HF sleeps after 48h inactivity. First visitor wakes it in ~10 seconds. Set up a free uptime ping (e.g. UptimeRobot) if you need it always-warm. |

---

## What this gives your pharma demo

After Path A:

- **Public URL:** `https://prabhu2k7-litextract.hf.space` — share this
- **Source code:** `https://github.com/prabhu2k7/LitExtract` — open source under AGPL-3.0
- **Cost to you:** $0/month (HF free tier; users bring their own OpenAI key)
- **Cost to evaluators:** ~$0.01–0.03 per paper they upload (OpenAI, on their key)
- **Time to "yes I'd like to pilot this"** — depends on whether they
  bring a real paper and a real key.
