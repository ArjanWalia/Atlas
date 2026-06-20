# Atlas backend (Convex)

The optional cloud backend for Atlas: a **global run history** and **active-directory
memory**, so you can say things like *"build on my last project"* or *"switch to
`~/projects/foo`"* and have it stick across sessions and channels.

Atlas works fine without this — if `CONVEX_URL` is unset, history is simply disabled.

## One-time setup

```bash
cd backend
npm install
npx convex dev        # logs you in, creates a deployment, generates convex/_generated/
```

`npx convex dev` prints your deployment URL, e.g. `https://your-project-123.convex.cloud`.
Put it in the repo-root `.env` so the Python side can reach it:

```
CONVEX_URL=https://your-project-123.convex.cloud
```

Leave `npx convex dev` running while you develop (it watches and pushes functions).
For a permanent deployment use `npx convex deploy` and use the production URL.

## What's here

| File | Purpose |
|------|---------|
| `convex/schema.ts` | `runs` (history) and `config` (active/known directories) tables |
| `convex/runs.ts` | `record` (mutation), `recent` / `lastBuild` (queries) |
| `convex/config.ts` | `get` (query), `setWorkdir` (mutation) |

The Python client calls these as `runs:record`, `runs:recent`, `config:get`,
`config:setWorkdir` (see `atlas/cloud.py`).

> `convex/_generated/` is created by `npx convex dev` and is not committed; the import
> errors in `runs.ts`/`config.ts` resolve once you've run it.
