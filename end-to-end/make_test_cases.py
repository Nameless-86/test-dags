#!/usr/bin/env python3

import json
import argparse
from pathlib import Path
from typing import List, Dict, Any


def determine_provider_config(provider: str) -> Dict[str, Any]:
    """Determine configuration based on provider type."""
    provider_configs = {
        "prometheus": {"where": "prometheus", "when": "1h", "useVectorSearch": True},
        "aws": {"where": "aws-cw", "when": "24h", "useVectorSearch": True},
        "cloudwatch": {"where": "aws-cw", "when": "24h", "useVectorSearch": True},
    }

    return provider_configs.get(
        provider.lower(), {"where": provider, "when": "1h", "useVectorSearch": True}
    )


def extract_metric_filters(metric_info: Dict[str, Any]) -> List[str]:
    """Extract metric filters from metric information."""
    filters = []

    metric_name = metric_info.get("MetricName")
    if metric_name:
        filters.append(metric_name)

    # Add other relevant fields as filters
    for key, value in metric_info.items():
        if key != "MetricName" and value != "*":
            if isinstance(value, list):
                filters.extend(value)
            else:
                filters.append(str(value))

    return filters


def generate_test_case_name(test_case_id: str, provider: str, metric_name: str) -> str:
    """Generate a descriptive test case name."""
    provider_names = {
        "prometheus": "Prometheus",
        "aws": "AWS CloudWatch",
        "cloudwatch": "AWS CloudWatch",
    }

    provider_display = provider_names.get(provider.lower(), provider.title())

    # Clean up metric name for display
    metric_display = metric_name.replace("_", " ").title()

    return f"{provider_display} - {metric_display} ({test_case_id})"


def convert_jsonl_to_test_cases(jsonl_file_path: Path) -> List[Dict[str, Any]]:
    """Convert JSONL test cases to WebSocket test case format."""
    test_cases = []

    with open(jsonl_file_path, "r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, 1):
            line = line.strip()
            if not line:
                continue

            try:
                jsonl_case = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"Warning: Skipping invalid JSON on line {line_number}: {e}")
                continue

            test_case_id = jsonl_case.get("id", f"case_{line_number}")
            provider = jsonl_case.get("provider", "unknown")
            metric_info = jsonl_case.get("metric_information", {})
            question = jsonl_case.get("generated_question", "")

            # Get provider-specific configuration
            provider_config = determine_provider_config(provider)

            # Extract metric filters
            metric_filters = extract_metric_filters(metric_info)

            # Generate test case name
            metric_name = metric_info.get("MetricName", "Unknown Metric")
            test_case_name = generate_test_case_name(
                test_case_id, provider, metric_name
            )

            # Build test case
            test_case = {
                "name": test_case_name,
                "prompt": question,
                "env_id": "default",
                "additional_params": {
                    "where": provider_config["where"],
                    "when": provider_config["when"],
                    "metricFilters": metric_filters,
                    "useVectorSearch": provider_config["useVectorSearch"],
                },
            }

            # Add original metadata for reference
            test_case["metadata"] = {
                "original_id": test_case_id,
                "provider": provider,
                "metric_information": metric_info,
            }

            test_cases.append(test_case)

    return test_cases


def save_test_cases(test_cases: List[Dict[str, Any]], output_file: Path):
    """Save test cases to JSON file."""
    with open(output_file, "w", encoding="utf-8") as file:
        json.dump(test_cases, file, indent=2, ensure_ascii=False)


def print_conversion_summary(test_cases: List[Dict[str, Any]]):
    """Print summary of converted test cases."""
    print(f"\nConversion Summary:")
    print(f"Total test cases converted: {len(test_cases)}")

    # Group by provider
    providers = {}
    for case in test_cases:
        provider = case["metadata"]["provider"]
        providers[provider] = providers.get(provider, 0) + 1

    print("\nBy provider:")
    for provider, count in providers.items():
        print(f"  {provider}: {count} cases")

    print("\nSample test cases:")
    for i, case in enumerate(test_cases[:3]):
        print(f"  {i+1}. {case['name']}")
        print(
            f"     Prompt: {case['prompt'][:80]}{'...' if len(case['prompt']) > 80 else ''}"
        )
        print(f"     Filters: {case['additional_params']['metricFilters']}")


def main():
    parser = argparse.ArgumentParser(
        description="Convert JSONL test cases to WebSocket test case format"
    )
    parser.add_argument("jsonl_file", help="Path to JSONL file with test cases")
    parser.add_argument(
        "--output", "-o", default="converted_test_cases.json", help="Output JSON file"
    )
    parser.add_argument(
        "--quiet", "-q", action="store_true", help="Suppress output messages"
    )
    args = parser.parse_args()

    jsonl_file_path = Path(args.jsonl_file)
    output_file_path = Path(args.output)

    if not jsonl_file_path.exists():
        print(f"Error: JSONL file {jsonl_file_path} not found")
        return 1

    if not args.quiet:
        print(f"Converting JSONL file: {jsonl_file_path}")

    try:
        test_cases = convert_jsonl_to_test_cases(jsonl_file_path)

        if not test_cases:
            print("Warning: No valid test cases found in input file")
            return 1

        save_test_cases(test_cases, output_file_path)

        if not args.quiet:
            print(f"Test cases saved to: {output_file_path}")
            print_conversion_summary(test_cases)

        return 0

    except Exception as e:
        print(f"Error during conversion: {e}")
        return 1


if __name__ == "__main__":
    exit(main())
