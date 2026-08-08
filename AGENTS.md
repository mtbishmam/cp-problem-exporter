# cp-problem-exporter project instructions

## ChatGPT Account, Site, and Codex Context

### ChatGPT accounts

- Both ChatGPT accounts may be used to build, edit, debug, and test these
  projects:
  - `mtbishmam@gmail.com`
  - `bari86838683@gmail.com`
- ChatGPT Site deployment currently works through `mtbishmam@gmail.com`.
- When working from `bari86838683@gmail.com`, build and stress-test locally
  using localhost, development servers, local APIs, local databases, mocks,
  browser testing, automated tests, and production-style build checks whenever
  possible.
- Treat final deployment as a handoff step to `mtbishmam@gmail.com`. Do not
  claim that a Site was deployed until deployment has been performed or
  independently verified through that account.
- Both accounts use the same local project and source files. Account
  differences do not imply separate codebases.

### Secondary-account workflow

- If the active ChatGPT account is `bari86838683@gmail.com`, treat the
  secondary account as a build, test, and preparation environment only.
- Do not attempt to deploy a ChatGPT Site or claim that a Site deployment
  succeeded from the secondary account.
- For any task involving application data, create or refresh a local snapshot
  of the current persistence layer before testing:
  - D1: use a local D1 database seeded from the available schema and data
    snapshot.
  - R2: use a local R2 simulation populated from the available object
    snapshot.
  - If the project uses another database or storage system, create the
    equivalent isolated local snapshot.
- Keep local bindings pointed at local resources. Do not enable remote
  bindings or connect destructive tests to production D1, R2, or equivalent
  storage.
- Run the local build, migrations, unit tests, API tests, browser checks, and
  relevant insert/update/delete stress tests against the local snapshot.
- If an exact production snapshot is unavailable, say so explicitly and use
  schema-valid fixtures or seed data. Do not claim that production data was
  verified.
- Treat all database and storage changes made from the secondary account as
  local-only. They do not change the deployed Site.
- Before handing work back, report clearly: **Site not yet deployed. Deploy
  the verified build from `mtbishmam@gmail.com`.**
- The primary account is responsible for deploying the approved saved version
  and for any intended production database or storage mutation. After the
  primary account deploys, verify the canonical hostname and report the
  production result separately from local test results.

### Canonical deployed Sites

| Project | Hostname | Description |
|---|---|---|
| ReSync | https://resync.mtbishmam.chatgpt.site | Intentional video and reading consumption system using RePlay, ReRead, Inbox, cooldown, Queue, Finished, AI summaries, value scoring, grounded chat, notes, and learning memory. |
| ReFocus | https://refocus.mtbishmam.chatgpt.site | Personal planning and focus-control system for daily plans, prioritized tasks, work cycles, screen-break overlays, agendas, routines, check-ins, streaks, metrics, offline use, and synchronization. |
| ReSolve | https://resolve.mtbishmam.chatgpt.site | Competitive-programming learning and active-recall system for problem capture, structured reflections, mistakes, mental models, memory cues, difficulty, status, review history, and spaced repetition. |

### Site identity rules

- Before creating a new ChatGPT Site, confirm the exact display name, owner
  namespace, slug, and complete hostname.
- Do not ask again for rebuilds, updates, or redeployments to an already
  confirmed Site.
- Ask again only when creating a new Site or changing its slug, namespace, or
  hostname.
- Never infer, rename, shorten, or substitute a Site slug or hostname.
- Treat a mismatched account, owner namespace, hostname, or deployment target
  as a deployment issue to diagnose and resolve.

### Codex context

- Codex task, thread, and conversation IDs may change frequently and are
  session-specific.
- Do not use Codex IDs as permanent project, Site, or deployment identifiers.
- Use the repository path, Git remote, branch, commit, canonical Site
  hostname, and active ChatGPT account as stable references.
- If an old Codex ID cannot be found, re-establish context from those stable
  references instead of assuming that the project or Site has changed.
