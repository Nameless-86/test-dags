import json
import argparse
from typing import Any, Dict, List, Optional

from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase, LLMTestCaseParams
from deepeval import evaluate
from deepeval.models import GPTModel


# ---------------------------------------------------------------------------
# Rubric for evaluating PQL quality
# ---------------------------------------------------------------------------
PQL_RUBRIC = """
ROLE: You are a senior reviewer for Autoptic's PQL DSL. Judge ACTUAL_OUTPUT (the generated PQL) for INPUT (the user prompt).

HARD VALIDITY CHECK:
- If ACTUAL_OUTPUT is empty OR does not look like PQL (e.g., missing core primitives such as where(…), when(…), what(…), request(…)),
  return exactly:
  {"score": 1, "reason": "invalid pql", "suggestion": "Include where(), when(), what(), and request() with correct syntax."}

SCORING (0-10):
Score by adding the following criteria. Cap the total at 10.

1) TIME RANGE FIDELITY (0-2)
   - Correctly interprets and applies the timeframe implied by INPUT (e.g., "last 24h" → when(24h)).
   - 2 = exact and explicit; 1 = present but ambiguous/mismatched; 0 = missing or wrong.

2) METRIC & SOURCE CORRECTNESS (0-3)
   - Chooses the right namespace(s)/metric(s) for the question (e.g., CloudWatch API Gateway 4XXError vs CloudFront 4xxErrorRate).
   - Avoids unrelated metrics unless clearly justified by the question.
   - 3 = all correct; 2 = mostly correct with minor drift; 1 = partially correct; 0 = wrong source/metric.

3) DIMENSIONS & GROUPING (0-2)
   - Uses appropriate dimensions/filters to answer the question (e.g., ApiName/Stage for API Gateway; DistributionId/Region for CloudFront; LoadBalancer/TargetGroup for ALB).
   - Wildcards (*) are acceptable if the prompt is broad; include grouping-ready dimensions when the prompt implies breakdowns.
   - 2 = appropriate and sufficient; 1 = present but incomplete/excessive; 0 = missing/misused.

4) STRUCTURE & SYNTAX QUALITY (0-2)
   - PQL is structurally coherent: where()->when()->what()->request()->as($var); indexes $where[i]/$what[j]/$when[k] are consistent; variables are unique/referenced correctly.
   - Charts/aggregations (e.g., average(), chart()) are consistent with the metric semantics (rate vs count).
   - 2 = clean and executable; 1 = minor issues; 0 = clearly broken.

5) FOCUS & PARSIMONY (0-1)
   - The PQL is minimal-yet-sufficient to answer INPUT (no unnecessary metrics/noise).
   - 1 = focused; 0 = unfocused or bloated.

OUTPUT FORMAT (STRICT):
Return ONLY one JSON object:
{"score": <integer 1..10>, "reason": "<brief rationale>", "suggestion": "<specific fix, or null if score >= 8>"}
If unsure, return:
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
# PQL detection (heuristic)
# ---------------------------------------------------------------------------
def is_probable_pql(pql_text: str) -> bool:
    """
    Heuristic check to decide if a string looks like Autoptic PQL.

    It requires:
      - Presence of core PQL primitives: where(), .when(), .what(), .request()
      - Presence of selector-like key/value hints commonly used in what(...)

    :param pql_text: Text to check.
    :return: True if the text looks like PQL; False otherwise.
    """
    if not isinstance(pql_text, str):
        return False

    if len(pql_text.strip()) == 0:
        return False

    compact_text: str = pql_text.replace(" ", "").lower()

    core_tokens: List[str] = ["where(", ".when(", ".what(", ".request("]
    core_primitives_present: bool = True

    for token in core_tokens:
        if token not in compact_text:
            core_primitives_present = False
            break

    if not core_primitives_present:
        return False

    selector_hints: List[str] = [
        "metricname='",
        "namespace='",
        "distributionid='",
        "targetgroup='",
        "loadbalancer='",
        "hostedzone='",
        "region='",
        "apiname='",
        "stage='",
    ]

    has_selector_like_kv: bool = False
    for hint in selector_hints:
        if hint in compact_text:
            has_selector_like_kv = True
            break

    if not has_selector_like_kv:
        return False

    return True


# ---------------------------------------------------------------------------
# PQL extraction helpers
# ---------------------------------------------------------------------------
def find_pql_in_step_list(
    step_list: List[Dict[str, Any]],
    required_message_substring: str,
) -> Optional[str]:
    """
    Search a list of progress/response steps (latest-first) for a step whose message contains
    the given substring and whose 'data' field looks like PQL.

    :param step_list: List of step dictionaries.
    :param required_message_substring: Substring that must appear in 'message' (or 'status').
    :return: The PQL string if found; otherwise None.
    """
    if step_list is None:
        return None

    # Iterate from the last element to the first (prefer the latest match).
    index: int = len(step_list) - 1
    while index >= 0:
        step: Dict[str, Any] = step_list[index]

        message_field_raw: Any = step.get("message")
        status_field_raw: Any = step.get("status")
        data_field_raw: Any = step.get("data")

        message_or_status: str = ""
        if isinstance(message_field_raw, str):
            message_or_status = message_field_raw
        elif isinstance(status_field_raw, str):
            message_or_status = status_field_raw

        if isinstance(message_or_status, str):
            if required_message_substring in message_or_status:
                if isinstance(data_field_raw, str):
                    if len(data_field_raw.strip()) > 0:
                        if is_probable_pql(data_field_raw):
                            return data_field_raw

        index = index - 1

    return None


def extract_pql_from_case(test_case_json: Dict[str, Any]) -> str:
    """
    Extract the raw PQL for a single test case. Fall back to 'responses'.

    :param test_case_json: A single test case dictionary.
    :return: Raw PQL string or a clear fallback marker.
    """
    responses: List[Dict[str, Any]] = test_case_json.get("responses") or []

    required_substring: str = "Workflow generated successfully"

    pql_from_responses: Optional[str] = find_pql_in_step_list(
        step_list=responses,
        required_message_substring=required_substring,
    )

    if pql_from_responses is not None:
        return pql_from_responses

    return "(no PQL found)"


# ---------------------------------------------------------------------------
# Test case construction
# ---------------------------------------------------------------------------
def build_deepeval_test_cases(
    test_cases_json: List[Dict[str, Any]]
) -> List[LLMTestCase]:
    """
    Convert Autoptic test cases into DeepEval LLMTestCase objects,
    where ACTUAL_OUTPUT is the raw PQL and INPUT is the original prompt.

    :param test_cases_json: List of test case dictionaries from the run file.
    :return: A list of DeepEval LLMTestCase instances.
    """
    deepeval_test_cases: List[LLMTestCase] = []

    for test_case_json in test_cases_json:
        request_object: Dict[str, Any] = test_case_json.get("request") or {}

        test_case_prompt: str = ""
        if isinstance(request_object.get("prompt"), str):
            test_case_prompt = request_object["prompt"]

        raw_pql: str = extract_pql_from_case(test_case_json)

        test_case_name: Optional[str] = test_case_json.get("name")

        tags: List[str] = []
        tags.append("pql")

        additional_metadata: Dict[str, Any] = {}
        additional_metadata["session_id"] = test_case_json.get("session_id")
        additional_metadata["when"] = request_object.get("when")
        additional_metadata["status"] = test_case_json.get("status")
        additional_metadata["duration"] = test_case_json.get("duration")

        deepeval_case: LLMTestCase = LLMTestCase(
            input=test_case_prompt,
            actual_output=raw_pql,
            expected_output=None,
            name=test_case_name,
            tags=tags,
            additional_metadata=additional_metadata,
        )

        deepeval_test_cases.append(deepeval_case)

    return deepeval_test_cases


# ---------------------------------------------------------------------------
# GEval metric factory
# ---------------------------------------------------------------------------
def create_pql_quality_metric(model_name: str) -> GEval:
    """
    Create the GEval metric configured with our PQL rubric.

    :param model_name: Model id for GPTModel (e.g., "gpt-4.1-mini").
    :return: Configured GEval instance.
    """
    base_model: GPTModel = GPTModel(model=model_name, temperature=0)

    pql_quality_metric: GEval = GEval(
        name="PQL Quality",
        criteria=PQL_RUBRIC,
        evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
        model=base_model,
        threshold=0.8,
        verbose_mode=True,
    )

    return pql_quality_metric


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
def main() -> None:
    """
    Program entrypoint. Loads the run JSON, builds DeepEval test cases,
    and runs the PQL quality evaluation.
    """
    argument_parser: argparse.ArgumentParser = argparse.ArgumentParser()
    argument_parser.add_argument(
        "--input",
        required=True,
        help="Path to the run JSON file containing 'test_cases'.",
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

    deepeval_test_cases: List[LLMTestCase] = build_deepeval_test_cases(test_cases_json)

    pql_quality_metric: GEval = create_pql_quality_metric(args.model)

    evaluate(
        test_cases=deepeval_test_cases,
        metrics=[pql_quality_metric],
    )


if __name__ == "__main__":
    main()
