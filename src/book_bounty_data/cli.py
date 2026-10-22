"""Read-only contract validation and explicit synthetic demo; no ingestion."""
import argparse
import json
import re
import sys
import unicodedata
from datetime import date, datetime, timedelta, timezone
from importlib.resources import files
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator, FormatChecker


def resource(name):
    return json.loads(files(__package__).joinpath(name).read_text(encoding="utf-8"))


RFC3339 = re.compile(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d+))?(Z|[+-]\d{2}:\d{2})", re.ASCII)


def timestamp(value):
    match = RFC3339.fullmatch(value)
    if not match:
        raise ValueError("RFC3339 timestamp required")
    base, fraction, offset = match.groups()
    # Python 3.10 fromisoformat accepts only 3 or 6 fractional digits; normalise to
    # microseconds so every supported interpreter accepts the same RFC3339 values.
    micro = "." + (fraction + "000000")[:6] if fraction else ""
    result = datetime.fromisoformat(base + micro + ("+00:00" if offset == "Z" else offset))
    if result.tzinfo is None:
        raise ValueError("timezone required")
    return result.astimezone(timezone.utc)


# Zero-width space/non-joiner/joiner, word joiner, BOM and soft hyphen render as nothing.
INVISIBLE = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff\u00ad"))
THAI_DIGITS = {0x0E50 + n: str(n) for n in range(10)}


def visible(text):
    """NFKC text without invisible characters or surrounding whitespace."""
    return unicodedata.normalize("NFKC", text).translate(INVISIBLE).strip()


def fold(text):
    """Search key: NFKC (full-width Latin, Thai SARA AM == NIKHAHIT + SARA AA),
    Thai digits as ASCII, nikhahit/tone-mark order unified, case-folded."""
    text = visible(text).translate(THAI_DIGITS)
    return re.sub("\u0e4d([\u0e48-\u0e4b])", "\\1\u0e4d", text).casefold()


FORMATS = FormatChecker()


@FORMATS.checks("date-time", raises=(ValueError, TypeError))
def valid_datetime(value):
    return not isinstance(value, str) or bool(timestamp(value))


@FORMATS.checks("date", raises=(ValueError, TypeError))
def valid_date(value):
    if not isinstance(value, str):
        return True
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) and date.fromisoformat(value))


def validate(payload):
    validator = Draft202012Validator(resource("schema.json"), format_checker=FORMATS)
    errors = list(validator.iter_errors(payload))
    if errors:
        # Do not echo input values or private payloads in error messages.
        raise ValueError("contract validation failed")
    try:
        # Python's json module turns NaN, Infinity and overflowing literals such as
        # 1e400 into non-finite floats that JSON Schema "number" accepts; reject them.
        json.dumps(payload, allow_nan=False)
    except (TypeError, ValueError):
        raise ValueError("payload must contain only finite JSON numbers") from None
    ids = set()
    observed = timestamp(payload["retrieved_at"])
    for item in payload["items"]:
        # minLength 1 accepts " " or a lone U+200B; required text must be visible.
        if not all(visible(item[key]) for key in ("id", "title", "provider", "eligibility_text")):
            raise ValueError("required text field is blank")
        record_id = visible(item["id"])
        if record_id in ids:
            raise ValueError("duplicate record ID")
        ids.add(record_id)
        checked = timestamp(item["provenance"]["checked_at"])
        if checked > observed:
            raise ValueError("source check is later than retrieval")
        url = urlsplit(item["source_url"])
        if url.scheme not in {"https", "http"} or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError("source URL must be a public canonical URL without credentials or query")
        if payload["data_status"] == "live":
            if item["provenance"]["evidence_kind"] != "captured" or not item["provenance"]["raw_object_key"] or not item["provenance"]["bronze_manifest_key"]:
                raise ValueError("live records require captured lake lineage")
            host = url.hostname.rstrip(".")  # "example.org." is the same DNS name
            if host == "example.org" or host.endswith(".example.org"):
                raise ValueError("synthetic source cannot be live")
        elif item["provenance"]["evidence_kind"] != "fixture":
            raise ValueError("fixture envelope requires fixture records")
        amount, currency = item["value"]["amount"], item["value"]["currency"]
        if amount is not None and currency is None:
            raise ValueError("monetary amount requires currency")
        if item["cost"]["fee_amount"] is not None and item["cost"]["currency"] is None:
            raise ValueError("fee amount requires currency")
    return payload


def filter_items(payload, as_of, open_only=False, query="", max_age_hours=72):
    validate(payload)
    now = timestamp(as_of)
    if max_age_hours < 0:
        raise ValueError("max age must be nonnegative")
    result = []
    for item in payload["items"]:
        if fold(query) not in fold(item["title"] + " " + item["category"]):
            continue
        if open_only:
            deadline = item["deadline"]
            checked = timestamp(item["provenance"]["checked_at"])
            if item["status"] != "open" or deadline["kind"] == "unknown":
                continue
            if checked > now or now - checked > timedelta(hours=max_age_hours):
                continue
            if deadline["kind"] == "fixed" and timestamp(deadline["at"]) <= now:
                continue
        result.append(item)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("contract")
    check = sub.add_parser("validate")
    check.add_argument("file", help="Explicit normalized export; input is never persisted")
    demo = sub.add_parser("demo")
    demo.add_argument("--as-of", default="2026-09-07T00:00:00Z", help="Synthetic demo clock")
    demo.add_argument("--open-only", action="store_true")
    demo.add_argument("--query", default="")
    demo.add_argument("--max-age-hours", type=int, default=72)
    args = parser.parse_args(argv)
    try:
        if args.command == "contract":
            output = resource("schema.json")
        elif args.command == "validate":
            with open(args.file, encoding="utf-8") as source:
                payload = validate(json.load(source))
            output = {"valid": True, "schema_version": payload["schema_version"], "data_status": payload["data_status"], "count": len(payload["items"])}
        else:
            payload = resource("demo.json")
            output = dict(payload, items=filter_items(payload, args.as_of, args.open_only, args.query, args.max_age_hours))
            output["demo_as_of"] = args.as_of
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, OverflowError):
        print("Input rejected: check contract, timestamps, source lineage and file access.", file=sys.stderr)
        return 2
