from deepeval.metrics import ContextualRecallMetric, ContextualRelevancyMetric
from deepeval.metrics.contextual_relevancy import ContextualRelevancyTemplate
from deepeval.test_case import LLMTestCase
from deepeval import evaluate
import json
import argparse
from deepeval.models import GPTModel

model = GPTModel(model="gpt-3.5-turbo-0125", temperature=0)


def load_results(path):
    with open(path) as f:
        return [json.loads(line) for line in f]


class CustomTemplate(ContextualRelevancyTemplate):
    @staticmethod
    def generate_verdicts(input: str, context: str):
        return f"""
You are evaluating a set of retrieved metric contexts for the following DevOps monitoring question:

Input (query): "{input}"

Context: Each statement below consists of a metric name and its description as returned by the system.

For each context statement:
- Assign 'verdict': 'yes' if the metric is clearly relevant to answering the user's monitoring question (e.g., if the metric name or its description directly refers to the metric/concept the question is about).
- Assign 'verdict': 'no' if the metric is unrelated, refers to a different concept, or the description does not help answer the question.
- For each 'no', briefly quote what in the statement makes it irrelevant (e.g., "metric describes 5XX errors, but the question is about 4XX errors").
- You may use the metric name and description for reasoning.
- Always return a JSON as shown below.

Example JSON:
{{
    "verdicts": [
        {{
            "verdict": "yes",
            "statement": "4XXError - The 4XXError metric measures the number of client-side errors...",
        }},
        {{
            "verdict": "no",
            "statement": "5XXError - The 5XXError metric measures the number of server-side errors...",
            "reason": "Statement is about server-side errors (5XX), but the query is about client-side errors (4XX)."
        }}
    ]
}}

Input:
{input}

Context:
{context}

JSON:
"""


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
        expected_metric = entry["metric_name"]

        # Extraer el nombre de la métrica, robusto por si cambia el formato
        metrics = []
        for r in entry["results"]:
            m_dict = r.get("context_retrieved", {})
            metric_name = m_dict.get("MetricName") or next(iter(m_dict.values()), "")
            metrics.append(metric_name)
        descriptions = [r["text"] for r in entry["results"]]
        context_metric_names = [
            f"{metric} - {description}"
            for metric, description in zip(metrics, descriptions)
        ]

        test_case = LLMTestCase(
            input=query,
            actual_output="",
            expected_output=expected_metric,
            retrieval_context=context_metric_names,
        )
        test_cases.append(test_case)

    evaluate(
        test_cases=test_cases,
        metrics=[
            ContextualRecallMetric(
                threshold=0.7, model=model, include_reason=True, verbose_mode=True
            ),
            ContextualRelevancyMetric(
                threshold=0.7,
                model=model,
                include_reason=True,
                evaluation_template=CustomTemplate,
                verbose_mode=True,
            ),
        ],
    )


if __name__ == "__main__":
    main()
