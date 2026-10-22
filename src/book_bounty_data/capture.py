"""Capture the official GitHub Bug Bounty rules page through the shared lake runtime."""

import argparse
import os
import re
import sys
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

from .cli import resource, validate
from .observability import init_sentry, report_exit


class Text(HTMLParser):
    """Extract visible text while ignoring executable page content."""

    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, value):
        if not self.hidden:
            self.parts.append(value)


def _normalize_generic(raw, source, checked_at):
    parser = Text()
    parser.feed(raw.decode("utf-8"))
    text = " ".join(" ".join(parser.parts).split())
    folded = text.casefold()
    markers = source.get("required_markers") or [source["title"]]
    if not all(marker.casefold() in folded for marker in markers):
        raise ValueError("generic bounty source drift or challenge page")
    record_id = source["id"]
    item = {
        "id": record_id,
        "title": source["title"],
        "category": source["category"],
        "source_url": source["source_url"],
        "provider": source["provider"],
        "status": source.get("status", "unknown"),
        "deadline": {"kind": source.get("deadline_kind", "rolling"), "at": None},
        "eligible_countries": source.get("eligible_countries", ["GLOBAL"]),
        "eligibility_text": source["eligibility_text"],
        "value": {
            "kind": source.get("value_kind", "variable"),
            "amount": source.get("value_amount"),
            "currency": source.get("value_currency"),
            "guaranteed": source.get("value_guaranteed"),
        },
        "cost": {"fee_amount": None, "currency": None, "auto_renewal": None, "notes": source["cost_notes"]},
        "terms": {
            "acceptance_criteria": "Not extracted; review the current official acceptance criteria.",
            "authorization_scope": "Only act within the authorization stated by the official source.",
            "payout_condition": "Not extracted; review the current official payout conditions.",
            "dispute_process": "Not extracted; review the current official dispute process.",
            **source.get("normalized_terms", {}),
        },
        "related_records": [],
        "provenance": {
            "evidence_kind": "captured",
            "source_id": source["id"],
            "source_record_id": record_id,
            "checked_at": checked_at,
            "raw_object_key": None,
            "bronze_manifest_key": None,
        },
    }
    return {
        "schema_version": source["schema_version"],
        "source": source["product"],
        "retrieved_at": checked_at,
        "data_status": "live",
        "items": [item],
    }


def normalize(raw, source, checked_at):
    if source.get("generic_html"):
        return _normalize_generic(raw, source, checked_at)
    """Turn the rules page into one conservative bounty program record."""
    if source["id"] != "github-bug-bounty-rules":
        raise ValueError("unknown bounty source")
    parser = Text()
    parser.feed(raw.decode("utf-8"))
    text = " ".join(" ".join(parser.parts).split())
    folded = text.casefold()
    required: tuple[str, ...] = (
        "rules of engagement",
        "github’s bug bounty program",
        "only test for vulnerabilities on sites you know to be operated by github",
        "legal safe harbor",
        "bounty@github.com",
        "written instructions for reproducing",
    )
    # The page has used both typographic and ASCII apostrophes over time.
    folded = folded.replace("’", "'")
    required = tuple(marker.replace("’", "'") for marker in required)
    if not all(marker in folded for marker in required):
        raise ValueError("GitHub Bug Bounty rules source drift or challenge page")

    # The rules page is a rolling program. It does not promise a bounty for
    # every report, so amount and guaranteed payment remain intentionally open.
    item = {
        "id": source["id"],
        "title": "GitHub Bug Bounty Program",
        "category": source["category"],
        "source_url": source["source_url"],
        "provider": source["provider"],
        "status": "open",
        "deadline": {"kind": "rolling", "at": None},
        "eligible_countries": [],
        "eligibility_text": (
            "GitHub's program is for eligible external researchers; employees and "
            "contractors, people in sanctioned countries or regions, and unlawful "
            "testing are excluded. Check the current rules before participating."
        ),
        "value": {
            "kind": "variable",
            "amount": None,
            "currency": "USD",
            "guaranteed": False,
        },
        "cost": {
            "fee_amount": None,
            "currency": None,
            "auto_renewal": None,
            "notes": (
                "No entry fee is extracted; do not incur testing costs or take actions outside the published rules."
            ),
        },
        "terms": {
            "acceptance_criteria": (
                "Provide a valid, reproducible vulnerability report with written "
                "reproduction steps; ineligible or duplicate reports may be closed "
                "or unpaid."
            ),
            "authorization_scope": (
                "Only test GitHub-operated assets listed in the official scope and "
                "target pages, use accounts and data you own, avoid third-party "
                "subdomains, and stay within the legal safe harbor and traffic limits."
            ),
            "payout_condition": (
                "GitHub determines bounty amounts under its severity guidelines; a "
                "valid report may receive a cash bounty or swag, but payment is "
                "discretionary and not guaranteed."
            ),
            "dispute_process": (
                "Keep the report on HackerOne, contact bounty@github.com when unsure, "
                "and do not publicly disclose details before the fix is available."
            ),
        },
        "related_records": [],
        "provenance": {
            "evidence_kind": "captured",
            "source_id": source["id"],
            "source_record_id": source["id"],
            "checked_at": checked_at,
            "raw_object_key": None,
            "bronze_manifest_key": None,
        },
    }
    # Validate the timestamp here so a malformed test or source clock cannot
    # create a record that the shared contract would later reject.
    datetime.fromisoformat(checked_at.replace("Z", "+00:00"))
    return {
        "schema_version": source["schema_version"],
        "source": source["product"],
        "retrieved_at": checked_at,
        "data_status": "live",
        "items": [item],
    }


def source_config(source_id=None):
    if source_id is None:
        return resource("source.json")
    if not re.fullmatch(r"[a-z0-9-]+", source_id):
        raise ValueError("invalid source id")
    base = resource("source.json")
    if base["id"] == source_id:
        return base
    try:
        return resource("source-" + source_id + ".json")
    except FileNotFoundError:
        raise ValueError("unknown source id") from None


def main(argv=None):
    selector = argparse.ArgumentParser(add_help=False)
    selector.add_argument("--source-id")
    selected, remaining = selector.parse_known_args(argv)
    root = os.environ.get("SOLO_DATA_LAKE_ROOT")
    if not root:
        print("Set SOLO_DATA_LAKE_ROOT to the local shared capture/lake runtime.", file=sys.stderr)
        return 2
    runtime = Path(root).resolve() / "infra/scripts"
    if not (runtime / "discovery/capture_runtime.py").is_file():
        print("Shared discovery runtime is unavailable.", file=sys.stderr)
        return 2
    sys.path.insert(0, str(runtime))
    from discovery.capture_runtime import VERSION, run

    if VERSION != 1:
        raise RuntimeError("unsupported shared capture runtime")
    source = source_config(selected.source_id)
    sentry = init_sentry(source["id"])
    return report_exit(sentry, source["id"], run(source, normalize, validate, remaining))


if __name__ == "__main__":
    raise SystemExit(main())
