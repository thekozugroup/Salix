"""Source-aware social references and descriptive style measurements (stdlib)."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import unicodedata
from collections import defaultdict
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .stats import aggregate, analyze

LIMITATIONS = [
    "Descriptive measurements, not a fine-tuned writing model or engagement prediction.",
    "Short posts, selection bias, topic, formatting and optional NLP dependencies affect results.",
    "Public reaction counts lack exposure, timing and audience controls; missing counts are unknown.",
    "External metrics provenance is a caller attestation, not independently verified source truth.",
]
SLUG = re.compile(r"[a-z0-9][a-z0-9_-]{0,99}\Z")
SOURCE_TYPES = {"original_post", "comment", "repost", "summary"}


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _string(record, key):
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a nonempty string")
    return value


def _url(value):
    if not isinstance(value, str) or any(c.isspace() or ord(c) < 32 or c in '<>"\\' for c in value):
        raise ValueError("source_url must be an HTTP(S) URL")
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username:
        raise ValueError("source_url must be an HTTP(S) URL without credentials")
    query = [(k, v) for k, v in parse_qsl(parts.query) if not k.startswith("utm_")]
    return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path.rstrip("/"),
                       urlencode(query), ""))


def _date(value, key):
    if not isinstance(value, str):
        raise ValueError(f"{key} must be an ISO date or timestamp")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{key} must be an ISO date or timestamp") from exc


@lru_cache(maxsize=1)
def _stats_template():
    return analyze("")


def validate_stats(stats):
    """Reject partial, aggregated, nonfinite or invented feature dictionaries."""
    if not isinstance(stats, dict) or set(stats) != set(_stats_template()):
        raise ValueError("stats must contain exactly the raw lib.stats.analyze feature keys")
    for key, template in _stats_template().items():
        value = stats[key]
        if isinstance(template, list):
            if not isinstance(value, list):
                raise ValueError(f"stats.{key} must be a list")
            seen = set()
            for pair in value:
                if (not isinstance(pair, list) or len(pair) != 2
                        or not isinstance(pair[0], str) or pair[0] in seen
                        or isinstance(pair[1], bool) or not isinstance(pair[1], (int, float))
                        or not math.isfinite(pair[1]) or pair[1] < 0):
                    raise ValueError(f"invalid stats.{key} distribution")
                seen.add(pair[0])
        elif isinstance(template, str):
            if value not in {"spacy", "suffix_proxy"}:
                raise ValueError("invalid formality_source")
        elif isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"stats.{key} must be a finite number")
    for key in ("word_count", "sentence_count", "paragraph_count", "type_count"):
        if not isinstance(stats[key], int) or stats[key] < 0:
            raise ValueError(f"stats.{key} must be a nonnegative integer")
    if stats["word_count"] == 0:
        raise ValueError("original text must contain at least one word")


def eligible(record):
    return record.get("text_complete") is True and (
        (record["source_type"] == "original_post" and record.get("measured_from") == "original_text")
        or (record["source_type"] == "repost" and record.get("measured_from") == "original_caption"
            and record.get("attribution_verified") is True)
    )


def prepare_record(raw, metrics_only=False):
    if (not isinstance(raw, dict) or type(raw.get("schema_version")) is not int
            or raw["schema_version"] != 1):
        raise ValueError("each record must be an object with schema_version: 1")
    record = dict(raw)
    author = _string(record, "author_id")
    if not SLUG.fullmatch(author):
        raise ValueError("author_id must be a lowercase slug, at most 100 characters")
    record["source_url"] = _url(record.get("source_url"))
    if record.get("source_type") not in SOURCE_TYPES:
        raise ValueError(f"source_type must be one of {sorted(SOURCE_TYPES)}")
    _date(record.get("retrieved_at"), "retrieved_at")
    if record.get("published_at") is not None:
        _date(record["published_at"], "published_at")
    record_id = record.setdefault("id", digest(author + record["source_url"])[:20])
    if not isinstance(record_id, str) or not SLUG.fullmatch(record_id):
        raise ValueError("id must be a lowercase slug, at most 100 characters")
    for key in ("excerpt", "summary", "notes"):
        if key in record and not isinstance(record[key], str):
            raise ValueError(f"{key} must be a string")
    if len(record.get("excerpt", "").split()) > 25:
        raise ValueError("excerpt must be at most 25 whitespace-delimited words")
    counts = record.get("metrics", {})
    if not isinstance(counts, dict):
        raise ValueError("metrics must be an object")
    for key in ("reactions", "comments", "reposts", "impressions", "followers"):
        value = counts.get(key)
        if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
            raise ValueError(f"metrics.{key} must be a nonnegative integer or null")
    has_body = "original_text" in record
    if has_body:
        text = _string(record, "original_text")
        if "stats" in record:
            raise ValueError("provide original_text or stats, not both")
        # A supplied body never upgrades a summary, comment, or incomplete capture.
        record.setdefault("measured_from", "original_text")
        record.setdefault("text_complete", False)
        record["body_sha256"] = digest(text)
        if eligible(record):
            record["stats"] = analyze(text)
            validate_stats(record["stats"])
            record["measurement_origin"] = "local_lib.stats.analyze"
        if metrics_only:
            record.pop("original_text")
    elif "stats" in record:
        _string(record, "capture_method")
        body_hash = record.get("body_sha256")
        if not isinstance(body_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", body_hash):
            raise ValueError("external stats require body_sha256 (SHA256 of UTF-8 original body)")
        validate_stats(record["stats"])
        record["measurement_origin"] = "external_lib.stats.analyze_attestation"
    if "stats" in record:
        record["body_word_count"] = record["stats"]["word_count"]
    record["profile_eligible"] = eligible(record) and "stats" in record
    record["exclusion_reason"] = None if record["profile_eligible"] else (
        "Requires complete original author prose; summaries, comments and shared bodies are excluded."
    )
    return record


def load_records(path):
    if path.is_dir():
        files = sorted(path.rglob("*.post.json"))
        if not files:
            raise ValueError("no *.post.json records found")
        raw = [json.loads(p.read_text(encoding="utf-8")) for p in files]
    else:
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw = raw if isinstance(raw, list) else [raw]
    if not raw:
        raise ValueError("at least one record is required")
    # Re-read stored body records by recomputing stats rather than trusting stale metrics.
    for record in raw:
        if isinstance(record, dict) and "original_text" in record and "measurement_origin" in record:
            record.pop("stats", None)
    return raw


def unique_records(records):
    ids, sources, bodies = set(), {}, set()
    kept, skipped = [], []
    for record in records:
        source = record["source_url"]
        author = record["author_id"]
        if source in sources and sources[source] != author:
            raise ValueError(f"conflicting author attribution for {source}")
        sources[source] = author
        key = (author, record["id"])
        body = (author, record.get("body_sha256"))
        if key in ids or any(r["source_url"] == source for r in kept) or (body[1] and body in bodies):
            skipped.append({"author_id": author, "id": record["id"], "reason": "duplicate id, source or body"})
            continue
        ids.add(key)
        bodies.add(body)
        kept.append(record)
    return kept, skipped


def build_profiles(records, min_posts=10, min_words=3000):
    if min_posts < 1 or min_words < 1:
        raise ValueError("sufficiency thresholds must be positive")
    records, duplicates = unique_records(records)
    grouped = defaultdict(list)
    for record in records:
        grouped[record["author_id"]].append(record)
    profiles = []
    for author, posts in sorted(grouped.items()):
        used = [p for p in posts if p["profile_eligible"]]
        words = sum(p["stats"]["word_count"] for p in used)
        sufficient = len(used) >= min_posts and words >= min_words
        profiles.append({
            "author_id": author, "name": author, "schema_version": 2,
            "status": "descriptive" if sufficient else "provisional",
            "sufficiency": {"sample_count": len(used), "total_word_count": words,
                            "min_posts": min_posts, "min_words": min_words,
                            "thresholds_met": sufficient,
                            "note": "Heuristic corpus floor; passing is not proof of stability or predictive validity."},
            "stats": aggregate([p["stats"] for p in used]),
            "posts": used,
            "excluded": [{"id": p["id"], "source_url": p["source_url"], "reason": p["exclusion_reason"]}
                         for p in posts if not p["profile_eligible"]],
        })
    return {"schema_version": 1, "kind": "salix_social_profiles", "profiles": profiles,
            "duplicates": duplicates, "limitations": LIMITATIONS}


def reference_markdown(record):
    metadata = {k: v for k, v in record.items() if k not in {"original_text", "stats"}}
    # JSON fence length accommodates arbitrary imported strings; metadata is never training prose.
    encoded = json.dumps(metadata, ensure_ascii=False, indent=2)
    fence = "`" * max(3, max((len(m[0]) + 1 for m in re.finditer(r"`+", encoded)), default=3))
    lines = ["<!-- salix-social-reference:v1 -->", "# Social reference", "", f"Source: <{record['source_url']}>", "",
             "## Metadata — excluded from style measurements", "", fence + "json", encoded, fence, ""]
    if "original_text" in record:
        lines += ["## Captured text — use the paired JSON eligibility and provenance", "", record["original_text"], ""]
    else:
        lines += ["Full body not retained. Measurements are in the paired .post.json record.", ""]
    return "\n".join(lines)


def comparison(profiles):
    if profiles.get("kind") != "salix_social_profiles":
        raise ValueError("compare expects social profile output")
    rows = []
    for profile in profiles["profiles"]:
        for post in profile["posts"]:
            # Long-form rows retain actual units, source links and missing values.
            for metric, value in post["stats"].items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    rows.append({"author_id": profile["author_id"], "post_id": post["id"],
                                 "source_url": post["source_url"], "metric": metric, "value": value,
                                 "kind": "style", "profile_status": profile["status"]})
            for metric in ("reactions", "comments", "reposts", "impressions", "followers"):
                rows.append({"author_id": profile["author_id"], "post_id": post["id"],
                             "source_url": post["source_url"], "metric": metric,
                             "value": post.get("metrics", {}).get(metric), "kind": "observed_count",
                             "profile_status": profile["status"]})
    return {"schema_version": 1, "kind": "salix_social_comparison", "rows": rows,
            "authors": [{k: p[k] for k in ("author_id", "status", "sufficiency", "stats")}
                        for p in profiles["profiles"]], "limitations": LIMITATIONS}


def review_draft(text, policy):
    if not isinstance(policy, dict):
        raise ValueError("review policy must be an object")
    terms = policy.get("excluded_terms", [])
    if not isinstance(terms, list) or any(not isinstance(t, str) or not t.strip() for t in terms):
        raise ValueError("excluded_terms must be a list of nonempty strings")
    normalize = lambda s: unicodedata.normalize("NFKC", s).casefold()
    normalized = normalize(text)
    matches = []
    for term in terms:
        pattern = r"(?<!\w)" + r"\s+".join(re.escape(t) for t in normalize(term).split()) + r"(?!\w)"
        count = len(re.findall(pattern, normalized))
        if count:
            matches.append({"term": term, "count": count})
    factual = policy.get("factual_state", "unverified")
    approval = policy.get("approval_state", "draft")
    if factual not in {"unverified", "needs_review", "verified"}:
        raise ValueError("invalid factual_state")
    if approval not in {"draft", "needs_review", "approved", "rejected"}:
        raise ValueError("invalid approval_state")
    claims = policy.get("claims", [])
    if not isinstance(claims, list):
        raise ValueError("claims must be a list")
    for claim in claims:
        if not isinstance(claim, dict) or not isinstance(claim.get("claim"), str):
            raise ValueError("each claim requires claim text")
        if claim.get("status") not in {"unverified", "verified", "rejected"}:
            raise ValueError("invalid claim status")
        if claim.get("status") == "verified":
            _string(claim, "evidence")
    draft_hash = digest(text)
    bound = policy.get("draft_sha256") == draft_hash
    blockers = []
    if matches:
        blockers.append("excluded_terms")
    if not bound:
        blockers.append("state_not_bound_to_current_draft")
    if factual != "verified" or any(c["status"] != "verified" for c in claims):
        blockers.append("factual_review_required")
    if approval != "approved":
        blockers.append("approval_required")
    return {"schema_version": 1, "draft_sha256": draft_hash, "excluded_term_matches": matches,
            "factual_state": factual, "approval_state": approval, "states_apply_to_current_draft": bound,
            "claims": claims, "blockers": blockers, "recorded_checks_pass": not blockers,
            "limitation": "Records caller fact-check and approval attestations; does not verify facts, claim coverage, identity, or publishing permission."}


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def run(args):
    try:
        if args.social_command == "ingest":
            records = [prepare_record(r, args.metrics_only) for r in load_records(Path(args.input))]
            records, duplicates = unique_records(records)
            out = Path(args.out_dir)
            # Validate the entire batch before creating any reference files.
            for record in records:
                target = out / record["author_id"] / record["id"]
                if target.with_suffix(".post.json").exists() or target.with_suffix(".md").exists():
                    raise ValueError(f"reference exists: {target}; choose a new output directory")
            for record in records:
                target = out / record["author_id"] / record["id"]
                write_json(target.with_suffix(".post.json"), record)
                target.with_suffix(".md").write_text(reference_markdown(record), encoding="utf-8")
            print(json.dumps({"records_written": len(records), "duplicates": duplicates}))
            return 0
        if args.social_command == "profile":
            records = [prepare_record(r, metrics_only=True) for r in load_records(Path(args.input))]
            result = build_profiles(records, args.min_posts, args.min_words)
        elif args.social_command == "compare":
            result = comparison(json.loads(Path(args.input).read_text(encoding="utf-8")))
        else:
            result = review_draft(Path(args.input).read_text(encoding="utf-8"),
                                  json.loads(Path(args.policy).read_text(encoding="utf-8")))
        if args.out:
            write_json(Path(args.out), result)
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 1 if args.social_command == "review" and result["blockers"] else 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        raise SystemExit(f"salix social: {exc}") from exc


def add_parser(sub):
    parser = sub.add_parser("social", help="Source-linked social references, author profiles and draft review")
    commands = parser.add_subparsers(dest="social_command", required=True)
    ingest = commands.add_parser("ingest", help="Measure original prose or import attested Salix stats")
    ingest.add_argument("input")
    ingest.add_argument("--out-dir", required=True)
    ingest.add_argument("--metrics-only", action="store_true", help="Omit full body from saved records")
    profile = commands.add_parser("profile", help="Aggregate isolated author profiles")
    profile.add_argument("input")
    profile.add_argument("--min-posts", type=int, default=10)
    profile.add_argument("--min-words", type=int, default=3000)
    compare = commands.add_parser("compare", help="Export descriptive chart-ready long-form rows")
    compare.add_argument("input")
    review = commands.add_parser("review", help="Check exclusions and recorded factual/approval state")
    review.add_argument("input")
    review.add_argument("--policy", required=True)
    for command in (profile, compare, review):
        command.add_argument("--out")
    for command in (ingest, profile, compare, review):
        command.set_defaults(fn=run)


def main():
    parser = argparse.ArgumentParser(prog="python -m lib.social")
    add_parser(parser.add_subparsers(required=True))
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
