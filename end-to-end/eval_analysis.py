import json
import argparse
from typing import Any, Dict, List, Optional

from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase, LLMTestCaseParams
from deepeval import evaluate
from deepeval.models import GPTModel


# ---------------------------------------------------------------------------
# Rubric for evaluating analysis quality
# ---------------------------------------------------------------------------
ANALYSIS_RUBRIC = """
ROLE: You are a senior cloud telemetry analyst. Judge ACTUAL_OUTPUT (the analysis) for INPUT (the monitoring prompt).

EVALUATION ORDER (follow in sequence):
1) NO-DATA CHECK (hard rule)
   - If ACTUAL_OUTPUT indicates insufficient data or empty analysis
     (e.g., "no time series", "no aggregates", "no datapoints", "empty result", "no data available"),
     OR the text is effectively a placeholder,
     THEN return exactly:
       {"score": 1, "reason": "no data", "suggestion": "Verify data exists for the stated time range, dimensions, and source; fix query/filters; re-run."}

2) DATA ACCURACY (0-4 points)
   - Time range fidelity; metric semantics (rate vs count); correct namespaces/sources.
   - No fabricated numbers or unsupported claims.

3) RELEVANCE TO QUESTION (0-3 points)
   - Directly answers INPUT; focuses on the asked signals/scope; clear conclusion tied to the prompt.

4) COMPLETENESS (0-3 points)
   - Covers requested aspects (anomalies/breakdowns/trends/alerts).
   - At least one actionable recommendation tied to findings.
   - States assumptions/limitations when relevant.

5) BONUS (0-1; cap total at 10)
   - If multi-source correlation is implied and done well, +1 (do not exceed 10).

SCORING:
- Start at 0; add sections 2-4; add bonus in 5; cap at 10.
- Strong analyses (>=8) are accurate, on-point, complete, and actionable.
- Generic boilerplate not grounded in INPUT should score <=3.

OUTPUT FORMAT (STRICT):
Return only one JSON object:
{"score": <integer 1..10>, "reason": "<brief>", "suggestion": "<specific improvement, or null if score >= 8>"}
If unsure or invalid, return:
{"score": 1, "reason": "Invalid response", "suggestion": "Review input"}
"""


# ---------------------------------------------------------------------------
# JSON loading
# ---------------------------------------------------------------------------
def load_run_file(file_path: str) -> Dict[str, Any]:
    """
    Load the run JSON file that contains a top-level 'test_cases' array.

    :param file_path: Path to the JSON file.
    :return: Parsed JSON as a dictionary.
    """
    with open(file_path, "r", encoding="utf-8") as file_handle:
        run_payload: Dict[str, Any] = json.load(file_handle)

    return run_payload


# ---------------------------------------------------------------------------
# Build ACTUAL_OUTPUT for the analysis judge
# ---------------------------------------------------------------------------
def build_analysis_actual_output(final_result: Dict[str, Any], mode: str) -> str:
    """
    Construct the text that will be judged as ACTUAL_OUTPUT.

    Modes:
      - "executive_summary": only the executive summary.
      - "key_findings": only the key findings.
      - "full": concatenation of several important fields.

    :param final_result: The 'final_result' object from a test case.
    :param mode: One of {"executive_summary", "key_findings", "full"}.
    :return: The analysis text to judge.
    """
    if not isinstance(final_result, dict):
        return "(no final_result)"

    if mode == "executive_summary":
        executive_summary: Optional[str] = final_result.get("executive_summary")
        if isinstance(executive_summary, str) and len(executive_summary) > 0:
            return executive_summary
        return "(no executive_summary)"

    if mode == "key_findings":
        key_findings: Optional[str] = final_result.get("key_findings")
        if isinstance(key_findings, str) and len(key_findings) > 0:
            return key_findings
        return "(no key_findings)"

    concatenated_parts: List[str] = []

    ordered_keys: List[str] = [
        "executive_summary",
        "key_findings",
        "trends_anomalies",
        "recommendations",
        "data_quality",
        "alerts",
        "context",
        "key_metrics",
    ]

    for field_name in ordered_keys:
        field_value: Any = final_result.get(field_name)
        if isinstance(field_value, str) and len(field_value) > 0:
            labeled_segment: str = f"{field_name}: {field_value}"
            concatenated_parts.append(labeled_segment)

    if len(concatenated_parts) == 0:
        return "(no final_result)"

    full_text: str = "\n\n".join(concatenated_parts)
    return full_text


# ---------------------------------------------------------------------------
# Optional retrieval context
# ---------------------------------------------------------------------------
def build_retrieval_context(final_result: Dict[str, Any]) -> List[str]:
    """
    Build a retrieval context list out of selected fields.
    Not required for the GEval rubric here but useful if swapping metrics later.

    :param final_result: The 'final_result' object from a test case.
    :return: List of context strings.
    """
    retrieval_context: List[str] = []

    if not isinstance(final_result, dict):
        return retrieval_context

    candidate_keys: List[str] = ["key_metrics", "recommendations", "context", "alerts"]

    for field_name in candidate_keys:
        field_value: Any = final_result.get(field_name)
        if isinstance(field_value, str) and len(field_value) > 0:
            retrieval_context.append(field_value)

    return retrieval_context


# ---------------------------------------------------------------------------
# Test case construction
# ---------------------------------------------------------------------------
def build_deepeval_test_cases(
    test_cases_json: List[Dict[str, Any]],
    actual_mode: str,
) -> List[LLMTestCase]:
    """
    Convert Autoptic test cases into DeepEval LLMTestCase objects,
    where ACTUAL_OUTPUT is the analysis text and INPUT is the original prompt.

    :param test_cases_json: List of test case dictionaries from the run file.
    :param actual_mode: One of {"executive_summary", "key_findings", "full"}.
    :return: A list of DeepEval LLMTestCase instances.
    """
    deepeval_test_cases: List[LLMTestCase] = []

    for test_case_json in test_cases_json:
        request_object: Dict[str, Any] = test_case_json.get("request") or {}

        monitoring_prompt: str = ""
        prompt_raw: Any = request_object.get("prompt")
        if isinstance(prompt_raw, str):
            monitoring_prompt = prompt_raw

        final_result: Dict[str, Any] = test_case_json.get("final_result") or {}

        actual_output_text: str = build_analysis_actual_output(
            final_result=final_result,
            mode=actual_mode,
        )

        retrieval_context: List[str] = build_retrieval_context(
            final_result=final_result
        )

        test_case_name: Optional[str] = test_case_json.get("name")

        tags: List[str] = []
        tags.append("analysis")
        tags.append(actual_mode)

        additional_metadata: Dict[str, Any] = {}
        additional_metadata["session_id"] = test_case_json.get("session_id")
        additional_metadata["when"] = request_object.get("when")
        additional_metadata["status"] = test_case_json.get("status")
        additional_metadata["duration"] = test_case_json.get("duration")

        deepeval_case: LLMTestCase = LLMTestCase(
            input=monitoring_prompt,
            actual_output=actual_output_text,
            expected_output=None,
            retrieval_context=retrieval_context if len(retrieval_context) > 0 else None,
            name=test_case_name,
            tags=tags,
            additional_metadata=additional_metadata,
        )

        deepeval_test_cases.append(deepeval_case)

    return deepeval_test_cases


# ---------------------------------------------------------------------------
# GEval metric factory
# ---------------------------------------------------------------------------
def create_analysis_quality_metric(model_name: str) -> GEval:
    """
    Create the GEval metric configured with our analysis rubric.

    :param model_name: Model id for GPTModel (e.g., "gpt-4.1-mini").
    :return: Configured GEval instance.
    """
    base_model: GPTModel = GPTModel(model=model_name, temperature=0)

    analysis_quality_metric: GEval = GEval(
        name="Analysis Quality",
        criteria=ANALYSIS_RUBRIC,
        evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
        model=base_model,
        threshold=0.8,
        verbose_mode=True,
    )

    return analysis_quality_metric


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
def main() -> None:
    """
    Program entrypoint. Loads the run JSON, builds DeepEval test cases,
    and runs the analysis quality evaluation.
    """
    argument_parser: argparse.ArgumentParser = argparse.ArgumentParser()
    argument_parser.add_argument(
        "--input",
        required=True,
        help="Path to the run JSON file containing 'test_cases'.",
    )
    argument_parser.add_argument(
        "--actual_mode",
        choices=["executive_summary", "key_findings", "full"],
        default="executive_summary",
        help="Which part of final_result to judge as ACTUAL_OUTPUT.",
    )
    argument_parser.add_argument(
        "--model",
        default="gpt-4.1-mini",
        help="LLM model name to use with DeepEval (default: gpt-4.1-mini).",
    )

    args = argument_parser.parse_args()

    run_payload: Dict[str, Any] = load_run_file(args.input)

    test_cases_json: List[Dict[str, Any]] = run_payload.get("test_cases") or []
    if len(test_cases_json) == 0:
        raise SystemExit("No test_cases found in the input JSON.")

    deepeval_test_cases: List[LLMTestCase] = build_deepeval_test_cases(
        test_cases_json=test_cases_json,
        actual_mode=args.actual_mode,
    )

    analysis_quality_metric: GEval = create_analysis_quality_metric(args.model)

    evaluate(
        test_cases=deepeval_test_cases,
        metrics=[analysis_quality_metric],
    )


if __name__ == "__main__":
    main()
