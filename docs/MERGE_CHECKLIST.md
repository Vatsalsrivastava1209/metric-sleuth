# Merge Checklist

Use this checklist before merging any non-trivial change into `main`.

## 1. Scope And Risk

- The PR description explains what changed and why.
- User-facing risk is called out explicitly.
- Background job, queue, billing, auth, RLS, and connector risks are called out if touched.
- Migration impact is documented if schema, storage policies, or Supabase RPCs changed.

## 2. Validation

- Backend tests passed: `python -m pytest -q`
- Frontend lint passed: `npm run lint` in `frontend/`
- Frontend production build passed: `npm run build` in `frontend/`
- Any touched scripts, migrations, or workflows were sanity-checked locally.

## 3. Data And Security

- No secrets, tokens, or plaintext credential material were committed.
- Sensitive config changes still fail closed if required env vars are missing.
- RLS assumptions remain valid for any new table, RPC, or storage policy changes.
- Public links, exports, and client-safe views were reviewed for data exposure risk.

## 4. Migrations And Rollout

- New migration files are ordered correctly under `supabase/migrations/`.
- The PR clearly states whether staging must apply migrations before deploy.
- Required environment variable changes are documented.
- Rollout order is clear for `frontend`, `api`, `worker`, and `beat` if relevant.
- Rollback plan is written when the change affects persistence, billing, or background jobs.

## 5. Operational Checks

- Observability or logs remain useful for the changed path.
- Long-running jobs, retries, and failure states were considered if async work changed.
- Any new external integration behavior is documented as `pilot-only` or `production-ready`.
- Deployment status checks are green, or any non-authoritative failures are explained before merge.

## 6. Staging Gate

Run or confirm staging smoke coverage when the change affects live workflows:

- login/auth
- dataset upload or workspace save
- analysis run creation and completion
- report persistence
- export
- share-link creation, expiry, or revocation
- billing or connector setup if touched

## 7. Final Merge Decision

Merge only if all of the following are true:

- CI is green.
- The rollout path is understood.
- No known blocker is being deferred silently.
- The branch is cleaner than `main`, not just different from it.

