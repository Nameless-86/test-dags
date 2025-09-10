#!/usr/bin/env python3
import argparse
import json
import time
import logging
from pathlib import Path

import pandas as pd
from tqdm.auto import tqdm
from langchain_ollama import ChatOllama

# ─── Logging setup ────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ─── Labels ────────────────────────────────────────────────────────────────────
LABELS = [
    "MISSING_METRIC",
    "WRONG_CONTEXT",
    "LACKS_CLARITY",
    "LACKS_UTILITY",
]


# ─── Helpers ──────────────────────────────────────────────────────────────────
def load_and_filter(path: Path, threshold: float) -> pd.DataFrame:
    """
    Load DeepEval results JSON, build DataFrame, and filter to score < threshold.
    """
    data = json.loads(path.read_text())
    rows = []
    for enc, val in data["test_cases_lookup_map"].items():
        tc = json.loads(enc)
        mdata = val["cached_metrics_data"][0]["metric_data"]
        rows.append(
            {
                "input": tc["input"],
                "expected_output": tc["expected_output"],
                "score": mdata.get("score", 0.0),
                "reason": mdata.get("reason", "").strip(),
            }
        )
    df = pd.DataFrame(rows)
    logger.info(f"Total cases loaded: {len(df)}")
    df_low = df[df["score"] < threshold].reset_index(drop=True)
    logger.info(f"Filtered cases (score < {threshold}): {len(df_low)}")
    return df_low


def build_prompt(reason: str) -> str:
    """Compose a classification prompt for a single reason."""
    opts = "\n".join(f"- {lbl}" for lbl in LABELS)
    return (
        "You are an expert evaluator of monitoring explanation quality.\n"
        "Choose exactly one label from:\n"
        f"{opts}\n\n"
        "Then explain your choice in one short sentence.\n\n"
        f'Explanation:\n"""{reason}"""\n\n'
        "Respond ONLY with JSON:\n"
        '{ "label": "<one of the above>", "justification": "<one-sentence>" }'
    )


def classify_reason(llm: ChatOllama, reason: str, retries: int = 2, delay: float = 0.5):
    """Attempt LLM classification, with retries."""
    prompt = build_prompt(reason)
    for attempt in range(retries + 1):
        try:
            resp = llm.invoke(prompt).content.strip()
            return json.loads(resp)
        except Exception as e:
            logger.warning(f"Attempt {attempt+1} failed: {e}")
            time.sleep(delay)
    return {"label": "ERROR", "justification": "LLM classification failed"}


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Classify low-score reasons via LLM")
    parser.add_argument("--input", required=True, help="DeepEval JSON file")
    parser.add_argument("--output", required=True, help="CSV output path")
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.8,
        help="Filter threshold: classify cases with score < threshold",
    )
    parser.add_argument("--model", default="llama3.1:8b", help="LLM model name")
    parser.add_argument("--base-url", required=True, help="LLM endpoint base URL")
    args = parser.parse_args()

    # Load & filter
    df_low = load_and_filter(Path(args.input), args.threshold)

    # Init LLM
    llm = ChatOllama(model=args.model, temperature=0.1, base_url=args.base_url)

    # Classify each reason
    output_rows = []
    for _, row in tqdm(df_low.iterrows(), total=len(df_low), desc="Classifying"):
        result = classify_reason(llm, row["reason"])
        output_rows.append(
            {
                "input": row["input"],
                "expected_output": row["expected_output"],
                "score": row["score"],
                "label": result.get("label", ""),
                "justification": result.get("justification", ""),
            }
        )
        time.sleep(0.5)  # rate-limit safety

    # Save CSV
    pd.DataFrame(output_rows).to_csv(args.output, index=False)
    logger.info(f"Wrote {len(output_rows)} rows to {args.output}")


if __name__ == "__main__":
    main()
