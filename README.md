# book-bounty-data

Find scoped paid tasks with clear acceptance and authorization.

Status: **local source pilot**, version 0.1.0. Five manually invoked official
sources now use the shared local lake runtime; there is no published remote,
scheduler, hosted API, or consumer integration. The CLI provides a
machine-readable JSON contract, validates explicit exports, and searches
synthetic examples. It never falls back from live data to fixtures.

## Users and boundary

For people and small teams discovering task bounties.
Payment for accepted deliverables; ranked contests and ordinary employment stay separate.

Subcategories: open-source, security, documentation, translation, community-task.

Domain-specific terms: `acceptance_criteria`, `authorization_scope`, `payout_condition`, `dispute_process`.
Each record represents one program/offer intake window. A repeat intake receives
a distinct source record ID. Cross-domain packages use `related_records` rather
than copying the same award into several products.

## Run locally

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
book-bounty-data contract
book-bounty-data demo --open-only
book-bounty-data demo --query "open-source"
book-bounty-data validate src/book_bounty_data/demo.json
python -m unittest discover -s tests -v
```

With dependencies already available, use `PYTHONPATH=src python3 -m book_bounty_data`.
`demo` uses the fixed synthetic clock 2026-09-07T00:00:00Z unless `--as-of` is
provided. `--open-only` excludes closed, unknown-deadline, expired, stale (72h
default), and future-checked records. This is an availability filter; it does
not assert personal eligibility, selection probability, or a guaranteed payout.

Contract: `src/book_bounty_data/schema.json` (`bounty.v1`).
Unknown amounts, currencies, eligibility and deadlines remain unknown. Cash,
credit, discount, in-kind benefits and access are different value kinds. Never
sum them as cash income. Queries and validation are read-only and do not persist
provided files. The `live` label requires captured lineage, but validation alone
does not verify that referenced lake objects exist or prove source truth.

## Data ownership and source policy

Owner: bookchaowalit. Public program metadata only; no applications, personal
screening answers, financial credentials, cookies, or private transcripts.
See `sources.json` and `src/book_bounty_data/source-github-bug-bounty-rules.json`.
The GitHub Bug Bounty rules page is reviewed for public read access and captured
only for bounded program metadata. The official [scope page](https://bounty.github.com/scope.html)
and [rewards page](https://bounty.github.com/rewards) remain linked policy inputs;
re-check them before any authorized testing. No security testing, spending,
account creation, submissions or messaging is performed by this adapter.

Implemented flow: approved source pull → immutable landing bytes
and checksum → Bronze Parquet and manifest through the shared lake runtime →
versioned read-only contract → consumer pull. Each product owns its source
adapters and lake prefix. Producers never write into another app's database,
CRM, tasks, application tracker, or notification system.

## Official source pilots

The five enabled sources are listed in `sources.json` and
`src/book_bounty_data/source*.json`. They include [GitHub Bug Bounty Rules of Engagement](https://bounty.github.com/rules), [Up For Grabs](https://up-for-grabs.net/), [Google Season of Docs](https://developers.google.com/season-of-docs), [Mozilla Pontoon](https://pontoon.mozilla.org/), and [Apache contribution guidance](https://www.apache.org/foundation/getinvolved.html).
The adapter records a rolling security program with variable, discretionary
value. It preserves the program's acceptance, authorization, safe-harbor,
reporting and payout conditions without inferring a guaranteed amount or
personal eligibility. Exact scope and current reward guidance are maintained by
the linked official pages.

Run with the existing data-lake Python environment:

```bash
export SOLO_DATA_LAKE_ROOT=/path/to/solo-data-lake
PYTHONPATH=src "$SOLO_DATA_LAKE_ROOT/.venv/bin/python" -m book_bounty_data.capture acquire --lake "$PWD/data/lake" --state-dir "$PWD/data/control"
PYTHONPATH=src "$SOLO_DATA_LAKE_ROOT/.venv/bin/python" -m book_bounty_data.capture records --lake "$PWD/data/lake" --state-dir "$PWD/data/control"
```

The lane depends on the explicit local `discovery.capture_runtime` v1. Capture
is manual, rate-limited to one check per six hours, and rejects sensitive source
markers before archival. A failed latest fetch has no fixture fallback; parser
failures leave a quarantined capture reference.

## Next implementation gates

1. Keep the five source adapters fresh and add parser fixtures when a provider changes its public contract.
2. Add live source tests, retention/access controls and runtime monitoring.
3. Connect a read-only consumer. Personal eligibility, ranking, deadlines and
   application workflow belong to consumers with separate private storage.

No runtime port is reserved. The former `opportunity.v1` is archival; `job.v1` remains a separate job-data contract.
Breaking contract changes require a new version and a consumer migration.
There is no production deployment to roll back; discard demo output or restore
the previous contract version locally. Source permission, live availability,
lake replay and real eligibility are **unverified**, not passing gates.

## Development

```bash
uv sync --frozen --all-extras && uv run mypy  # locked env (uv.lock) as CI installs it
uv run pytest -q --cov
```
