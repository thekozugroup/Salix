#!/usr/bin/env python3
"""Explicit opt-in experiment using real Codex calls and Salix measurement feedback."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import _path  # noqa: F401

from lib import stats as stats_module
from lib.distance import compute_gaps
from lib.stats import aggregate, analyze

ROOT = Path(__file__).resolve().parents[1]
SOURCE_URL = "https://www.gutenberg.org/cache/epub/1661/pg1661.txt"
MODEL = "gpt-5.6-sol"
BASE_PROMPT = (
    "Write a 400-550-word Baker Street case note narrated in first person by Dr Watson. "
    "Use these fixed fictional facts: the client is Clara Bell; her return railway ticket "
    "is missing; her train departs from Euston at 6:40; it is raining; the ticket is "
    "eventually found inside her folded newspaper; the newspaper's interior is dry, "
    "and Holmes uses that observation to deduce where the ticket is hidden. No theft "
    "has occurred and there is no culprit. Do not change these facts or introduce a "
    "different solution. Return only the finished case note, no heading or commentary. "
    "Do not use tools or access files."
)
STYLE_PROMPT = BASE_PROMPT + " Write in the style of Arthur Conan Doyle's Sherlock Holmes stories."
LIMITATIONS = [
    "One model, one fictional prompt, one author and book, and one run: not a general performance estimate.",
    "A controlled Salix-feedback harness, not a test of automatic host skill selection.",
    "Held-out passages never enter prompts, feedback, or score-based selection.",
    "Lexical copying and factual token checks are mechanical screens, not semantic or originality proof.",
    "Model pretraining may include the book; an eight-word overlap screen cannot exclude paraphrased memorization.",
    "Fifty attempts exceed the production skill's normal plateau limit to expose metric over-optimization.",
    "Best-so-far training scores are selected; raw candidate and held-out scores must also remain visible.",
    "Fallback formality and syllables are heuristics; POS features are unavailable, not perfect matches.",
    "No universal convergence, zero-distance target, or percentage voice match is claimed.",
]


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def fallback_metrics():
    return patch.multiple(stats_module, _SPACY_LOAD_ATTEMPTED=True, _SPACY_NLP=None,
                          _PYPHEN_ATTEMPTED=True, _PYPHEN_DIC=None)


def select_corpus(source: str) -> dict:
    headings = list(re.finditer(r"(?m)^[IVX]+\. [A-Z][A-Z '’-]+\s*$", source))
    if len(headings) < 6:
        raise ValueError("Expected at least six story headings in the source.")
    passages = []
    for index, heading in enumerate(headings[:6]):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(source)
        paragraphs = [re.sub(r"\s+", " ", p).strip()
                      for p in re.split(r"\n\s*\n", source[heading.end():end])]
        chosen, words = [], 0
        for paragraph in paragraphs:
            count = len(paragraph.split())
            if count < 8:
                continue
            chosen.append(paragraph)
            words += count
            if words >= 500:
                break
        if words < 500:
            raise ValueError("Source story is too short for the recorded selection method.")
        text = "\n\n".join(chosen)
        passages.append({"story": heading.group().strip(), "text": text, "sha256": sha256(text)})
    return {"url": SOURCE_URL, "sha256": sha256(source),
            "selection": "First complete paragraphs totaling at least 500 whitespace words from stories 1-6; odd stories train, even stories held out.",
            "training": passages[::2], "heldout": passages[1::2]}


def phrases(text: str, length: int = 8) -> set[tuple[str, ...]]:
    words = re.findall(r"[a-z]+(?:'[a-z]+)?", text.lower())
    return {tuple(words[index:index + length]) for index in range(len(words) - length + 1)}


def screen(text: str, source_phrases: set[tuple[str, ...]]) -> list[str]:
    reasons = []
    required = {
        "client": r"\bClara Bell\b", "station": r"\bEuston\b", "departure": r"6[.:]40|six[- ]forty",
        "rain": r"\brain(?:ing)?\b", "ticket": r"\bticket\b", "newspaper": r"\bnewspaper\b",
        "fold": r"\bfold(?:ed|s|ing)?\b", "dry": r"\bdry\b", "Holmes": r"\bHolmes\b",
        "Watson narration": r"\bI\b", "no theft": r"no (?:theft|thief)|not (?:been )?stolen|never (?:been )?stolen|nothing (?:had been |was )?stolen|no one (?:had )?stolen",
    }
    for fact, pattern in required.items():
        if not re.search(pattern, text, flags=re.IGNORECASE):
            reasons.append("missing factual token: " + fact)
    if not 400 <= len(text.split()) <= 550:
        reasons.append("outside 400-550 whitespace words")
    if phrases(text) & source_phrases:
        reasons.append("eight-word source overlap")
    return reasons


def safe_events(stdout: str) -> dict:
    usages, agent_texts, tool_events = [], [], 0
    completed = False
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "turn.completed":
            completed = True
            usage = event.get("usage", {})
            usages.append({key: value for key, value in usage.items()
                           if key in {"input_tokens", "output_tokens", "cached_input_tokens", "reasoning_output_tokens"}
                           and type(value) is int and value >= 0})
        item = event.get("item", {})
        if event.get("type") == "item.completed" and item.get("type") == "agent_message":
            agent_texts.append(item.get("text", ""))
        if item.get("type") in {"command_execution", "mcp_tool_call", "web_search", "file_change"}:
            tool_events += 1
    return {"completed": completed, "usage": usages, "agent_texts": agent_texts, "tool_events": tool_events}


def model_call(prompt: str, binary: str, model: str, home: Path, timeout: int) -> dict:
    output = home / "response.txt"
    output.unlink(missing_ok=True)
    env = os.environ.copy()
    for key in ("SALIX_HOME", "SALIX_SCOPE", "SALIX_GLOBAL_HOME", "SALIX_HOOKS"):
        env.pop(key, None)
    env.update(HOME=str(home), CODEX_HOME=str(home / ".codex"))
    command = [binary, "exec", "--ignore-user-config", "--ephemeral", "--skip-git-repo-check",
               "--sandbox", "read-only", "-C", str(home / "project"), "-m", model,
               "-c", "model_reasoning_effort=low", "--json", "-o", str(output), "-"]
    started = time.monotonic()
    result = subprocess.run(command, input=prompt, text=True, capture_output=True, env=env, timeout=timeout)
    events = safe_events(result.stdout)
    if result.returncode or not events["completed"] or not output.is_file():
        raise RuntimeError(f"Codex call failed (exit {result.returncode}); no output accepted. Raw diagnostics not saved.")
    text = output.read_text(encoding="utf-8").strip()
    if text not in events["agent_texts"] or events["tool_events"]:
        raise RuntimeError("Output does not match final agent event or a tool was used.")
    events.pop("agent_texts")
    return {"prompt": prompt, "text": text, "sha256": sha256(text),
            "seconds": round(time.monotonic() - started, 3), "events": events}


def measure(record: dict, training: dict, heldout: dict) -> dict:
    stats = analyze(record["text"])
    return {**record, "stats": stats, "training_distance": compute_gaps(stats, training)["total_distance"],
            "heldout_distance": compute_gaps(stats, heldout)["total_distance"]}


def feedback_prompt(draft: dict, training: dict, corpus: dict) -> str:
    gaps = compute_gaps(draft["stats"], training)
    feedback = [{key: gap[key] for key in ("feature", "target", "benchmark", "direction", "edit_hint")}
                for gap in gaps["top_gaps"][:6]]
    return (BASE_PROMPT + "\n\nRevise the draft below to match the writing profile learned from these "
            "public-domain samples. Preserve all fixed facts and a natural coherent story; do not "
            "optimize numbers at the cost of meaning. Do not copy any eight consecutive words from "
            "the samples. Do not insert unrelated training-story characters or events. Salix "
            "measurements suggest these changes, but safety and readability come first:\n" +
            json.dumps(feedback) + "\n\nTRAINING SAMPLES:\n" +
            "\n\n---\n\n".join(sample["text"] for sample in corpus["training"]) +
            "\n\nDRAFT TO REVISE:\n" + draft["text"])


def validate_payload(payload: dict) -> None:
    if payload.get("schema_version") != 1 or payload.get("evidence_type") != "recorded_ai_feedback_experiment":
        raise ValueError("Unsupported recorded experiment.")
    if payload.get("limitations") != LIMITATIONS or payload["completion"]["convergence_proven"] is not False:
        raise ValueError("Experiment limitations or convergence claims changed.")
    corpus = payload["corpus"]
    for sample in [*corpus["training"], *corpus["heldout"]]:
        if sha256(sample["text"]) != sample["sha256"]:
            raise ValueError("Corpus hash mismatch.")
    with fallback_metrics():
        training = aggregate([analyze(sample["text"]) for sample in corpus["training"]])
        heldout = aggregate([analyze(sample["text"]) for sample in corpus["heldout"]])
        if payload["benchmarks"] != {"training": training, "heldout": heldout}:
            raise ValueError("Corpus profile mismatch.")
        for record in payload["calls"]:
            if sha256(record["text"]) != record["sha256"]:
                raise ValueError("Output text hash mismatch.")
            measured = measure(record, training, heldout)
            if any(record[key] != measured[key] for key in ("stats", "training_distance", "heldout_distance")):
                raise ValueError("Recorded measurements do not match text.")
            if record["events"]["completed"] is not True or record["events"]["tool_events"] != 0:
                raise ValueError("Recorded call must complete without tools.")
        calls = payload["calls"]
        source_phrases = set().union(*(phrases(sample["text"]) for sample in corpus["training"] + corpus["heldout"]))
        best = 0
        if len(calls) != len(payload["iterations"]) + 1:
            raise ValueError("Calls must include two baselines and one real call per attempt.")
        for index, row in enumerate(payload["iterations"]):
            candidate = 0 if index == 0 else index + 1
            reasons = screen(calls[candidate]["text"], source_phrases)
            accepted = index > 0 and not reasons and calls[candidate]["training_distance"] < calls[best]["training_distance"]
            if accepted:
                best = candidate
            expected = {"iteration": index, "candidate": candidate, "retained": best,
                        "accepted": accepted, "screen_rejections": reasons}
            if row != expected:
                raise ValueError("Selection history is inconsistent with recorded candidates.")
            expected_prompt = BASE_PROMPT if index == 0 else feedback_prompt(calls[payload["iterations"][index - 1]["retained"]], training, corpus)
            if calls[candidate]["prompt"] != expected_prompt:
                raise ValueError("Prompt history mismatch or held-out feedback leak.")
        if calls[1]["prompt"] != STYLE_PROMPT:
            raise ValueError("Explicit-style baseline prompt mismatch.")
        if payload["completion"]["attempts"] != len(payload["iterations"]) - 1 or payload["completion"]["retained"] != best:
            raise ValueError("Completion counts are inconsistent.")


def save(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def run(args) -> dict:
    binary = shutil.which("codex")
    auth_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    auth = auth_home / "auth.json"
    if not binary or not auth.is_file():
        raise ValueError("Requires an installed, logged-in Codex CLI using auth.json.")
    with urllib.request.urlopen(SOURCE_URL, timeout=30) as response:
        source = response.read(2_000_001)
    if len(source) > 2_000_000:
        raise ValueError("Source exceeds experiment download limit.")
    corpus = select_corpus(source.decode("utf-8-sig"))
    with fallback_metrics(), tempfile.TemporaryDirectory(prefix="salix-live-") as temporary:
        home = Path(temporary)
        (home / ".codex").mkdir()
        (home / "project").mkdir()
        (home / ".codex/auth.json").symlink_to(auth.resolve())
        training = aggregate([analyze(sample["text"]) for sample in corpus["training"]])
        heldout = aggregate([analyze(sample["text"]) for sample in corpus["heldout"]])
        source_phrases = set().union(*(phrases(sample["text"]) for sample in corpus["training"] + corpus["heldout"]))
        payload = {"schema_version": 1, "evidence_type": "recorded_ai_feedback_experiment",
                   "started_at": datetime.now(timezone.utc).isoformat(), "prompt": BASE_PROMPT,
                   "runtime": {"provider": "OpenAI via Codex CLI", "requested_model": args.model,
                               "reasoning_effort": "low", "python": sys.version.split()[0],
                               "codex_version": subprocess.check_output([binary, "--version"], text=True).strip(),
                               "pos_backend": "unavailable; heuristic formality", "syllable_backend": "vowel-group heuristic"},
                   "source_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                                     for name in ("scripts/live_convergence.py", "lib/stats.py", "lib/distance.py", "lib/function_words.py", "lib/tone.py")},
                   "limitations": list(LIMITATIONS), "corpus": corpus,
                   "benchmarks": {"training": training, "heldout": heldout}, "calls": [], "iterations": [],
                   "completion": {"attempts": 0, "retained": 0, "status": "running", "convergence_proven": False}}
        for prompt in (BASE_PROMPT, STYLE_PROMPT):
            payload["calls"].append(measure(model_call(prompt, binary, args.model, home, args.timeout), training, heldout))
            print(f"Recorded baseline {len(payload['calls'])}: {payload['calls'][-1]['training_distance']}", flush=True)
        payload["iterations"].append({"iteration": 0, "candidate": 0, "retained": 0, "accepted": False,
                                      "screen_rejections": screen(payload["calls"][0]["text"], source_phrases)})
        save(Path(args.out), payload)
        for iteration in range(1, args.attempts + 1):
            best = payload["completion"]["retained"]
            candidate = len(payload["calls"])
            record = measure(model_call(feedback_prompt(payload["calls"][best], training, corpus), binary,
                                        args.model, home, args.timeout), training, heldout)
            payload["calls"].append(record)
            reasons = screen(record["text"], source_phrases)
            accepted = not reasons and record["training_distance"] < payload["calls"][best]["training_distance"]
            if accepted:
                best = candidate
            payload["iterations"].append({"iteration": iteration, "candidate": candidate, "retained": best,
                                          "accepted": accepted, "screen_rejections": reasons})
            payload["completion"].update(attempts=iteration, retained=best)
            save(Path(args.out), payload)
            print(f"Attempt {iteration}/{args.attempts}: candidate={record['training_distance']}; retained={payload['calls'][best]['training_distance']}; accepted={accepted}; screens={reasons}", flush=True)
        payload["completion"].update(status="attempt_budget_exhausted", completed_at=datetime.now(timezone.utc).isoformat())
        validate_payload(payload)
        save(Path(args.out), payload)
        return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="Explicitly authorize live model calls against your Codex account")
    parser.add_argument("--validate", type=Path, help="Remeasure an existing record without model calls")
    parser.add_argument("--out", default="examples/live_convergence.json")
    parser.add_argument("--attempts", type=int, default=50)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--model", default=MODEL)
    args = parser.parse_args()
    if args.validate:
        validate_payload(json.loads(args.validate.read_text(encoding="utf-8")))
        print("Recorded text/hash/metrics/selection checks passed. Semantic quality is not certified.")
        return 0
    if not args.run:
        parser.error("Use --run for live generation, or --validate FILE for offline checks.")
    if not 0 <= args.attempts <= 100 or args.timeout <= 0:
        parser.error("Attempts must be 0-100 and timeout must be positive.")
    try:
        run(args)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"Experiment stopped: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
