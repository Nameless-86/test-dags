from deepeval.metrics import GEval
from deepeval.metrics.g_eval import Rubric
from deepeval.test_case import LLMTestCase, LLMTestCaseParams
from deepeval import evaluate
from deepeval.models import GPTModel
import json
import argparse

model = GPTModel(model="gpt-4.1-mini", temperature=0)

rubric_prompt = """
You are an expert in cloud telemetry and documentation.
Given a metric description and a related monitoring question, evaluate the quality of the description on a scale from 1 (poor) to 10 (excellent) based on:
- Clarity: Is the description understandable and concise?
- Coverage: Does it explain what is measured, units, context, and implications?
- Utility: Can this description help a user answer the provided question?
If the score is less than 8, provide a concrete suggestion for improvement.

IMPORTANT RULES:
- Respond ONLY with a JSON object.
- Do NOT include any text before or after the JSON.
- If unsure, output a JSON with {"score":1,"reason":"Invalid description","suggestion":"Review input"}.

IMPORTANT: Your entire response MUST be valid JSON, and nothing else. Do not include code blocks, explanations, or any extra text. Only output this object:
{
  "score": <integer from 1 to 10>,
  "reason": "<brief rationale>",
  "suggestion": "<concrete suggestion, or null if score >= 8>"
}

Description:
{context}
Question:
{input}
"""


description_quality_metric = GEval(
    name="Metric Description Quality",
    criteria=rubric_prompt,
    evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.RETRIEVAL_CONTEXT],
    threshold=0.8,  # score >= 8 is considered "pass"
    model=model,
    verbose_mode=True,
)


def load_results(path):
    with open(path) as f:
        return [json.loads(line) for line in f]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input", required=True, help="Input search_results.jsonl file"
    )
    args = parser.parse_args()

    data = load_results(args.input)
    test_cases = []

    for entry in data:
        query = entry["query"]
        expected_metric = entry["Metric Information"]

        # Asegurar que expected_metric sea string
        if not isinstance(expected_metric, str):
            expected_metric = json.dumps(expected_metric, ensure_ascii=False)

        context_metric_names = []
        for r in entry["results"]:
            m_dict = r.get("context_retrieved", {})
            metric_info = m_dict.get("Metric Information") or next(
                iter(m_dict.values()), ""
            )
            if not isinstance(metric_info, str):
                metric_info = json.dumps(metric_info, ensure_ascii=False)

            description = r.get("Description", "")
            if not isinstance(description, str):
                description = json.dumps(description, ensure_ascii=False)

            context_metric_names.append(f"{metric_info} - {description}")

        test_case = LLMTestCase(
            input=query,
            actual_output="",
            expected_output=expected_metric,
            retrieval_context=context_metric_names,
        )
        test_cases.append(test_case)

    evaluate(test_cases=test_cases, metrics=[description_quality_metric])


if __name__ == "__main__":
    main()
