#!/usr/bin/env python3
"""
Test Case Converter for End-to-End Evaluation Pipeline

This module converts JSONL format test cases to WebSocket-compatible test format
with provider-specific configurations. It handles metric filter extraction,
provider-specific parameter mapping, and test case naming.

Dependencies:
    - json: JSON parsing and generation
    - argparse: Command-line argument parsing
    - pathlib: Cross-platform path handling
    - typing: Type hints for better code clarity

Usage:
    python3 make_test_cases.py input.jsonl --output test_cases.json

Author: Autoptic Team
"""

import json
import argparse
from pathlib import Path
from typing import List, Dict, Any


def determine_provider_config(provider: str) -> Dict[str, Any]:
    """
    Determine WebSocket request configuration based on provider type.
    
    Maps provider names to their specific query configurations including:
    - where: The data source namespace for PQL queries
    - when: Default time range for queries
    - useVectorSearch: Whether to enable vector-based metric search
    
    Args:
        provider (str): Provider name (e.g., 'prometheus', 'aws', 'cloudwatch')
        
    Returns:
        Dict[str, Any]: Configuration dictionary with where, when, and useVectorSearch keys
        
    Note:
        - Prometheus uses 1-hour default time range
        - AWS/CloudWatch use 24-hour default time range
        - All providers default to vector search enabled
        - Unknown providers fall back to provider name as 'where' value
    """
    # Provider-specific configuration mapping
    provider_configs = {
        "prometheus": {"where": "prometheus", "when": "1h", "useVectorSearch": True},
        "aws": {"where": "aws-cw", "when": "24h", "useVectorSearch": True},
        "cloudwatch": {"where": "aws-cw", "when": "24h", "useVectorSearch": True},
    }

    # Return specific config or default for unknown providers
    return provider_configs.get(
        provider.lower(), {"where": provider, "when": "1h", "useVectorSearch": True}
    )


def extract_metric_filters(metric_info: Dict[str, Any]) -> List[str]:
    """
    Extract metric filters from metric information dictionary.
    
    Processes metric metadata to extract searchable filter terms including:
    - Primary metric name (MetricName field)
    - Additional dimensional values (excluding wildcards)
    - List values are flattened into individual filter terms
    
    Args:
        metric_info (Dict[str, Any]): Metric metadata dictionary from JSONL input
        
    Returns:
        List[str]: List of filter terms for metric searching
        
    Note:
        - Wildcards ("*") are excluded from filters
        - List values are expanded into individual filter terms
        - MetricName is always included first if present
    """
    filters = []

    # Always include primary metric name first
    metric_name = metric_info.get("MetricName")
    if metric_name:
        filters.append(metric_name)

    # Add other relevant fields as filters, excluding wildcards
    for key, value in metric_info.items():
        if key != "MetricName" and value != "*":
            if isinstance(value, list):
                # Flatten list values into individual filters
                filters.extend(value)
            else:
                # Convert single values to string filters
                filters.append(str(value))

    return filters


def generate_test_case_name(test_case_id: str, provider: str, metric_name: str) -> str:
    """
    Generate a descriptive, human-readable test case name.
    
    Creates standardized test case names for easy identification in logs and reports.
    Format: "{Provider Display Name} - {Formatted Metric Name} ({Test Case ID})"
    
    Args:
        test_case_id (str): Unique identifier from the original JSONL test case
        provider (str): Provider name (prometheus, aws, cloudwatch)
        metric_name (str): Primary metric name from metric_information
        
    Returns:
        str: Formatted test case name for display purposes
        
    Example:
        generate_test_case_name("tc_001", "aws", "4XXError") 
        -> "AWS CloudWatch - 4 X X Error (tc_001)"
    """
    # Map provider codes to display names
    provider_names = {
        "prometheus": "Prometheus",
        "aws": "AWS CloudWatch",
        "cloudwatch": "AWS CloudWatch",
    }

    provider_display = provider_names.get(provider.lower(), provider.title())

    # Clean up metric name for display (replace underscores, title case)
    metric_display = metric_name.replace("_", " ").title()

    return f"{provider_display} - {metric_display} ({test_case_id})"


def convert_jsonl_to_test_cases(jsonl_file_path: Path) -> List[Dict[str, Any]]:
    """
    Convert JSONL format test cases to WebSocket-compatible test case format.
    
    Processes each line of a JSONL file containing test cases and converts them
    to the structured format expected by the WebSocket test executor. Handles
    provider-specific configurations, metric filter extraction, and metadata preservation.
    
    Args:
        jsonl_file_path (Path): Path to the JSONL input file
        
    Returns:
        List[Dict[str, Any]]: List of WebSocket-compatible test case dictionaries
        
    Raises:
        FileNotFoundError: If the input JSONL file doesn't exist
        json.JSONDecodeError: If a line contains invalid JSON (logged and skipped)
        
    Expected JSONL format:
        {"id": "tc_001", "provider": "aws", "metric_information": {...}, "generated_question": "..."}
        
    Output test case format:
        {
            "name": "Descriptive Name",
            "prompt": "Natural language question",
            "env_id": "default",
            "additional_params": {"where": "aws-cw", "when": "24h", ...},
            "metadata": {"original_id": "tc_001", ...}
        }
    """
    test_cases = []

    with open(jsonl_file_path, "r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, 1):
            line = line.strip()
            if not line:  # Skip empty lines
                continue

            try:
                jsonl_case = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"Warning: Skipping invalid JSON on line {line_number}: {e}")
                continue

            # Extract required fields with fallbacks
            test_case_id = jsonl_case.get("id", f"case_{line_number}")
            provider = jsonl_case.get("provider", "unknown")
            metric_info = jsonl_case.get("metric_information", {})
            question = jsonl_case.get("generated_question", "")

            # Get provider-specific configuration (where, when, useVectorSearch)
            provider_config = determine_provider_config(provider)

            # Extract searchable metric filters from metric metadata
            metric_filters = extract_metric_filters(metric_info)

            # Generate descriptive test case name for logging/reporting
            metric_name = metric_info.get("MetricName", "Unknown Metric")
            test_case_name = generate_test_case_name(
                test_case_id, provider, metric_name
            )

            # Build WebSocket-compatible test case structure
            test_case = {
                "name": test_case_name,
                "prompt": question,
                "env_id": "default",  # Standard environment for all tests
                "additional_params": {
                    "where": provider_config["where"],  # Data source namespace
                    "when": provider_config["when"],    # Time range
                    "metricFilters": metric_filters,     # Search filters
                    "useVectorSearch": provider_config["useVectorSearch"],
                },
            }

            # Preserve original metadata for analysis and debugging
            test_case["metadata"] = {
                "original_id": test_case_id,
                "provider": provider,
                "metric_information": metric_info,
            }

            test_cases.append(test_case)

    return test_cases


def save_test_cases(test_cases: List[Dict[str, Any]], output_file: Path):
    """
    Save converted test cases to JSON file for WebSocket execution.
    
    Writes the list of test cases to a JSON file with proper formatting
    for readability and UTF-8 encoding for international characters.
    
    Args:
        test_cases (List[Dict[str, Any]]): List of converted test case dictionaries
        output_file (Path): Path where the JSON file should be saved
        
    Raises:
        IOError: If the output file cannot be written
        
    Note:
        - Uses 2-space indentation for readability
        - Preserves Unicode characters (ensure_ascii=False)
        - Creates parent directories if they don't exist
    """
    # Ensure parent directory exists
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, "w", encoding="utf-8") as file:
        json.dump(test_cases, file, indent=2, ensure_ascii=False)


def print_conversion_summary(test_cases: List[Dict[str, Any]]):
    """
    Print a summary of the converted test cases to stdout.
    
    Displays statistics about the conversion including:
    - Total number of test cases converted
    - Breakdown by provider type
    - Sample test cases with truncated prompts
    - Metric filters for each sample
    
    Args:
        test_cases (List[Dict[str, Any]]): List of converted test case dictionaries
        
    Note:
        - Shows up to 3 sample test cases for verification
        - Truncates prompts longer than 80 characters for readability
        - Groups statistics by provider for easier analysis
    """
    print(f"\nConversion Summary:")
    print(f"Total test cases converted: {len(test_cases)}")

    # Group test cases by provider for statistics
    providers = {}
    for case in test_cases:
        provider = case["metadata"]["provider"]
        providers[provider] = providers.get(provider, 0) + 1

    # Display provider breakdown
    print("\nBy provider:")
    for provider, count in providers.items():
        print(f"  {provider}: {count} cases")

    # Show sample test cases for verification
    print("\nSample test cases:")
    for i, case in enumerate(test_cases[:3]):  # Limit to first 3 cases
        print(f"  {i+1}. {case['name']}")
        # Truncate long prompts for readability
        prompt = case['prompt']
        truncated_prompt = f"{prompt[:80]}{'...' if len(prompt) > 80 else ''}"
        print(f"     Prompt: {truncated_prompt}")
        print(f"     Filters: {case['additional_params']['metricFilters']}")


def main():
    """
    Main entry point for the test case converter.
    
    Handles command-line argument parsing, file validation, test case conversion,
    and result output. Provides error handling and user feedback throughout the process.
    
    Returns:
        int: Exit code (0 for success, 1 for failure)
        
    Command-line Arguments:
        jsonl_file: Path to input JSONL file with test cases
        --output, -o: Output JSON file path (default: converted_test_cases.json)
        --quiet, -q: Suppress informational output messages
        
    Examples:
        python3 make_test_cases.py input.jsonl
        python3 make_test_cases.py input.jsonl --output my_tests.json --quiet
    """
    # Set up command-line argument parsing
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

    # Validate input and output paths
    jsonl_file_path = Path(args.jsonl_file)
    output_file_path = Path(args.output)

    # Check if input file exists
    if not jsonl_file_path.exists():
        print(f"Error: JSONL file {jsonl_file_path} not found")
        return 1

    # Start conversion process
    if not args.quiet:
        print(f"Converting JSONL file: {jsonl_file_path}")

    try:
        # Convert JSONL test cases to WebSocket format
        test_cases = convert_jsonl_to_test_cases(jsonl_file_path)

        # Validate that we have test cases to save
        if not test_cases:
            print("Warning: No valid test cases found in input file")
            return 1

        # Save converted test cases to output file
        save_test_cases(test_cases, output_file_path)

        # Provide user feedback unless in quiet mode
        if not args.quiet:
            print(f"Test cases saved to: {output_file_path}")
            print_conversion_summary(test_cases)

        return 0

    except Exception as e:
        print(f"Error during conversion: {e}")
        return 1


if __name__ == "__main__":
    # Execute main function and exit with appropriate code
    exit(main())
