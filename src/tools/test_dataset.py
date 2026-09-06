"""Прогон классификатора по размеченному датасету.

    python -m tools.test_dataset data/dataset.jsonl [--config config] [--strict] [--verbose]

Формат строки: {"text": "...", "expected": true, "chat_location": "Аксай"?}
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.config.loader import Chat, load_config
from src.processing.classifier import Classifier


def load_dataset(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as e:
                raise SystemExit(f"{path}:{n}: bad json: {e}")
            if "text" not in row or "expected" not in row:
                raise SystemExit(f"{path}:{n}: 'text' and 'expected' are required")
            rows.append(row)
    return rows


def evaluate(classifier: Classifier, rows: list[dict]) -> dict:
    tp = fp = fn = tn = 0
    errors = []
    for row in rows:
        chat = Chat(id="dataset", name="dataset", location=row.get("chat_location")) if row.get("chat_location") else None
        c = classifier.classify(row["text"], chat)
        got, exp = c.is_lead, bool(row["expected"])
        if got and exp:
            tp += 1
        elif got and not exp:
            fp += 1
            errors.append(("FALSE POSITIVE", row["text"], c.verdict.explain()))
        elif not got and exp:
            fn += 1
            errors.append(("FALSE NEGATIVE", row["text"], c.verdict.explain()))
        else:
            tn += 1
    detected = tp + fp
    expected_total = tp + fn
    return {
        "messages": len(rows), "detected": detected, "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": tp / detected if detected else None,
        "recall": tp / expected_total if expected_total else None,
        "errors": errors,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset", type=Path)
    ap.add_argument("--config", type=Path, default=Path("config"))
    ap.add_argument("--strict", action="store_true", help="exit 1 if any mismatch")
    ap.add_argument("--verbose", action="store_true", help="print explanation for errors")
    args = ap.parse_args()

    classifier = Classifier(load_config(args.config))
    res = evaluate(classifier, load_dataset(args.dataset))

    pct = lambda v: "n/a" if v is None else f"{v * 100:.1f}%"
    print(f"Messages:       {res['messages']}")
    print(f"Detected:       {res['detected']}")
    print(f"True positive:  {res['tp']}")
    print(f"False positive: {res['fp']}")
    print(f"False negative: {res['fn']}")
    print(f"Precision:      {pct(res['precision'])}")
    print(f"Recall:         {pct(res['recall'])}")
    if res["errors"]:
        print("\n--- Mismatches ---")
        for kind, text, expl in res["errors"]:
            print(f"\n[{kind}] {text}")
            if args.verbose:
                print("    " + expl.replace("\n", "\n    "))
    if args.strict and res["errors"]:
        sys.exit(1)


if __name__ == "__main__":
    main()