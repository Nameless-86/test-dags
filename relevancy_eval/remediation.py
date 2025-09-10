#!/usr/bin/env python3
"""
remediation.py

Reads a CSV of low-scoring metrics (with columns: input, expected_output, score, label, justification),
loads the original metric JSON files from a directory, and for each flagged metric:
  • builds a label-specific remediation prompt
  • invokes an LLM to rewrite the description
  • injects the new description back into the original JSON
  • writes updated JSONs into an output directory

Usage:
  python remediation.py \
    --csv     cloudtrail_reason_classification.csv \
    --in_dir  ../vector/ \
    --out_dir remediated_vector/ \
    --model   llama3.1:8b \
    --base_url https://your-ngrok-url

"""

import argparse
import csv
import json
from pathlib import Path
import time

from langchain_openai import ChatOpenAI
from textwrap import dedent

# ────────────────────────────────────────────────────────────────────────────────
REMEDIATION_TEMPLATES = {
    "MISSING_METRIC": dedent(
        """
        The provided description for **{metric}** in {provider} **does not match** the intended metric or includes irrelevant details:

        “{old_description}”

        → Correct and expand it so that it:
           • Focuses solely on **{metric}**'s purpose and what it returns in {provider}.
           • Covers technical dimensions (units, data source).
           • Highlights when and why an unusual value should trigger an alert.
        Output: (only the new description)
    """
    ),
    "LACKS_METRIC": dedent(
        """
        The provided description for **{metric}** in {provider} **does not match** the intended metric or includes irrelevant details:

        “{old_description}”

        → Correct and expand it so that it:
           • Focuses solely on **{metric}**'s purpose and what it returns in {provider}.
           • Covers technical dimensions (units, data source).
           • Highlights when and why an unusual value should trigger an alert.
        Output: (only the new description)
    """
    ),
    "WRONG_CONTEXT": dedent(
        """
        The provided description for **{metric}** in {provider} **does not match** the intended metric or includes irrelevant details:

        “{old_description}”

        → Correct and expand it so that it:
           • Focuses solely on **{metric}**'s purpose and what it returns in {provider}.
           • Covers technical dimensions (units, data source).
           • Highlights when and why an unusual value should trigger an alert.
        Output: (only the new description)
    """
    ),
    "LACKS_CLARITY": dedent(
        """
        The description for **{metric}** is unclear or overly vague:

        “{old_description}”

        → Rewrite it for maximum clarity:
           • Use 3-4 concise sentences.
           • Precisely define what **{metric}** measures and in which unit.
        Output: (only the new description)
    """
    ),
    "LACKS_UTILITY": dedent(
        """
        The description for **{metric}** does not provide actionable guidance:

        “{old_description}”

        → Improve it so that an SRE can:
           • Understand **{metric}**'s purpose in {provider}.
           • Know which threshold would trigger an alert.
           • Grasp the impact of high or low values.
           • See an example of using **{metric}** in a dashboard or alert rule.
        Output: (only the new description)
    """
    ),
}
# ────────────────────────────────────────────────────────────────────────────────


def load_flags(csv_path):
    """
    Read the CSV of flagged metrics; return a dict mapping:
      provider -> metric_query_json_str -> (label, old_description)
    """
    flags = {}
    with open(csv_path, newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            # infer provider by filename stem in CSV path
            provider = Path(csv_path).stem
            metric = row["expected_output"]
            label = row["label"]
            old_desc = row["justification"]  # or use original reason?
            flags.setdefault(provider, {})[metric] = (label, old_desc)
    return flags


def remediate_file(src_path, out_path, llm, flags_for_provider):
    """
    Load a single metrics JSON, rewrite flagged descriptions, write to out_path.
    """
    provider = src_path.stem.lower()
    metrics = json.loads(src_path.read_text())
    updated = False

    for entry in metrics:
        # reconstruct the metric key as stored in CSV expected_output
        key = json.dumps(entry["query"], ensure_ascii=False)
        if key in flags_for_provider:
            label, old_justification = flags_for_provider[key]
            template = REMEDIATION_TEMPLATES[label]
            prompt = template.format(
                provider=provider, metric=key, old_description=entry["description"]
            )

            # call LLM
            resp = llm.invoke(prompt)
            new_desc = resp.content.strip()

            # replace
            entry["description"] = new_desc
            updated = True

            print(f"[OK] {provider} {key} → remediated ({label})")
            time.sleep(0.5)

    # only write if any change
    if updated:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(metrics, indent=2, ensure_ascii=False))
        print(f"[WRITE] {out_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True, help="CSV of low-scoring metrics")
    ap.add_argument(
        "--in_dir", required=True, help="Directory of original JSON metrics"
    )
    ap.add_argument("--out_dir", required=True, help="Where to write remediated JSONs")
    ap.add_argument("--model", default="llama3.1:8b", help="LLM model name")
    ap.add_argument("--base_url", required=False, help="LLM endpoint base URL")
    args = ap.parse_args()

    flags = load_flags(args.csv)

    llm = ChatOpenAI(
        model="gpt-4.1-mini",
        temperature=0.1,
    )

    in_dir = Path(args.in_dir)
    out_dir = Path(args.out_dir)

    for src_path in sorted(in_dir.glob("*.json")):
        provider = src_path.stem.lower()
        if provider not in flags:
            continue
        out_path = out_dir / src_path.name
        remediate_file(src_path, out_path, llm, flags[provider])

    print("✅ Remediation complete.")


if __name__ == "__main__":
    main()
