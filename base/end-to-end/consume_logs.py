"""
Log Parser & Result Aggregator for End-to-End Evaluation Pipeline

This module converts raw JSONL WebSocket logs into structured test results with
extracted analysis data. It processes WebSocket event logs, reconstructs test
cases with their complete lifecycle, and generates summary statistics.

Key Features:
    - JSONL WebSocket log parsing and event reconstruction
    - Test case lifecycle tracking (start, progress, completion)
    - Analysis data extraction from success frames
    - Error handling and timeout detection
    - Summary statistics generation (success rates, durations)
    - Structured JSON output for evaluation tools

Data Processing:
    1. Parses JSONL log entries line by line
    2. Reconstructs test cases from WebSocket events
    3. Extracts analysis results from completion frames
    4. Handles errors, timeouts, and incomplete cases
    5. Generates comprehensive test run summaries

Dependencies:
    - json: JSON parsing and generation
    - argparse: Command-line argument parsing
    - pathlib: Cross-platform path handling
    - typing: Type hints for better code clarity
    - datetime: Timestamp processing and duration calculation

Usage:
    python3 consume_logs.py runs/20250101-120000.log --output test_results.json

Author: Autoptic Team
"""

import json
import argparse
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime


def parse_log_file(log_file_path: Path) -> Dict[str, Any]:
    """
    Parse JSONL WebSocket log file and extract structured test results.
    
    Processes a JSONL log file containing WebSocket events from test execution,
    reconstructing complete test cases with their lifecycle events, request data,
    response frames, and final results.
    
    Args:
        log_file_path (Path): Path to the JSONL log file from WebSocket test execution
        
    Returns:
        Dict[str, Any]: Structured test results with run info, test cases, and metadata
        
    Log Processing Flow:
        1. Parse each JSONL line as a log entry
        2. Extract run header information
        3. Track test case lifecycle (open -> request -> frames -> close)
        4. Process WebSocket frames for analysis data
        5. Handle errors and timeouts
        6. Finalize test cases with duration calculation
        
    Expected Log Events:
        - run_header: Test run metadata
        - connection_opening: Test case start
        - sent_request: Request data
        - frame: WebSocket response frames
        - connection_closed: Test case completion
        - client_error/client_timeout: Error conditions
        
    Output Structure:
        {
            "run_info": {"timestamp": ..., "endpoint_id": ...},
            "test_cases": [{"name": ..., "status": ..., "final_result": ...}, ...]
        }
        
    Error Handling:
        - Skips malformed JSON lines
        - Handles incomplete test cases gracefully
        - Records error events in test case data
    """
    with open(log_file_path, "r", encoding="utf-8") as file:
        lines = file.readlines()

    # Initialize results structure
    results = {"run_info": {}, "test_cases": []}
    current_test_case = None

    # Process each log line
    for line in lines:
        try:
            log_entry = json.loads(line.strip())
        except json.JSONDecodeError:
            # Skip malformed JSON lines
            continue

        event_type = log_entry.get("event")

        # Process different types of log events
        if event_type == "run_header":
            # Extract test run metadata
            results["run_info"] = extract_run_header(log_entry)

        elif event_type == "connection_opening":
            # Start new test case tracking
            current_test_case = initialize_test_case(log_entry)

        elif event_type == "sent_request":
            # Extract request data for current test case
            if current_test_case:
                current_test_case["request"] = extract_request_data(log_entry)

        elif "case" in log_entry and "frame" in log_entry:
            # Process WebSocket response frames
            if current_test_case and log_entry["case"] == current_test_case["name"]:
                process_frame_data(current_test_case, log_entry["frame"])

        elif event_type == "connection_closed":
            # Finalize test case and add to results
            if current_test_case:
                current_test_case["end_time"] = log_entry.get("ts")
                finalize_test_case(current_test_case)
                results["test_cases"].append(current_test_case)
                current_test_case = None

        elif event_type in ["client_error", "client_timeout"]:
            # Record error events
            if current_test_case:
                current_test_case["errors"].append(
                    {
                        "type": event_type,
                        "message": log_entry.get("error", "Timeout occurred"),
                        "timestamp": log_entry.get("ts"),
                    }
                )

    return results


def extract_run_header(log_entry: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract test run header information from run_header event.
    
    Args:
        log_entry (Dict[str, Any]): Log entry containing run header data
        
    Returns:
        Dict[str, Any]: Run metadata including timestamp, endpoint, and URL
        
    Header Information:
        - timestamp: When the test run started
        - endpoint_id: WebSocket endpoint identifier used
        - websocket_url: Complete WebSocket URL for the run
    """
    return {
        "timestamp": log_entry.get("ts"),
        "endpoint_id": log_entry.get("endpoint_id"),
        "websocket_url": log_entry.get("url"),
    }


def initialize_test_case(log_entry: Dict[str, Any]) -> Dict[str, Any]:
    """
    Initialize new test case structure from connection_opening event.
    
    Creates the base structure for tracking a test case execution through
    its complete lifecycle from connection opening to closure.
    
    Args:
        log_entry (Dict[str, Any]): Log entry containing connection opening data
        
    Returns:
        Dict[str, Any]: Initialized test case structure ready for population
        
    Test Case Structure:
        - name: Test case name from original test data
        - session_id: Unique session identifier for this execution
        - start_time/end_time: Execution timing boundaries
        - duration: Calculated execution time (populated on finalization)
        - status: Current execution status (running -> success/error/incomplete)
        - request: Request data sent to WebSocket
        - responses: All WebSocket response frames received
        - final_result: Extracted analysis data from successful completion
        - errors: Any error events encountered
        - progress_messages: Progress updates during execution
    """
    return {
        "name": log_entry.get("case"),
        "session_id": log_entry.get("session"),
        "start_time": log_entry.get("ts"),
        "end_time": None,
        "duration": None,
        "status": "running",           # Initial status
        "request": {},                 # Populated from sent_request event
        "responses": [],               # Populated from frame events
        "final_result": {},            # Populated from success frames
        "errors": [],                  # Populated from error events
        "progress_messages": [],       # Populated from progress frames
    }


def extract_request_data(log_entry: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract and structure request data from sent_request event.
    
    Processes the request payload that was sent to the WebSocket endpoint,
    organizing it into a structured format for analysis and evaluation.
    
    Args:
        log_entry (Dict[str, Any]): Log entry containing sent_request data
        
    Returns:
        Dict[str, Any]: Structured request data with normalized field names
        
    Request Data Structure:
        - prompt: Natural language monitoring question
        - env_id: Environment identifier (usually "default")
        - where: Data source namespace (e.g., "aws-cw", "prometheus")
        - when: Time range for query (e.g., "24h", "1h")
        - metric_filters: List of metric search filters
        - use_vector_search: Whether vector search was enabled
        - additional_params: Any other parameters not covered above
        
    Note:
        Separates core PQL parameters from additional parameters for
        easier analysis and debugging of request configurations.
    """
    request_data = log_entry.get("request", {})
    
    # Extract core request parameters
    structured_request = {
        "prompt": request_data.get("prompt"),
        "env_id": request_data.get("env_id"),
        "where": request_data.get("where"),
        "when": request_data.get("when"),
        "metric_filters": request_data.get("metricFilters", []),
        "use_vector_search": request_data.get("useVectorSearch", False),
    }
    
    # Capture any additional parameters not in core set
    core_params = {
        "prompt", "env_id", "session_id", "where", "when", 
        "metricFilters", "useVectorSearch"
    }
    
    structured_request["additional_params"] = {
        k: v for k, v in request_data.items() 
        if k not in core_params
    }
    
    return structured_request


def process_frame_data(test_case: Dict[str, Any], frame: Dict[str, Any]):
    """
    Process WebSocket response frame and update test case state.
    
    Handles different types of WebSocket frames (progress, success, error)
    and updates the test case structure accordingly. Extracts analysis data
    from successful completion frames.
    
    Args:
        test_case (Dict[str, Any]): Test case structure being updated
        frame (Dict[str, Any]): WebSocket frame data to process
        
    Frame Processing:
        - All frames are recorded in responses array
        - Progress frames are tracked separately for debugging
        - Success frames trigger final result extraction
        - Error frames update test case status and record error details
        
    Frame Types:
        - progress: Intermediate status updates during execution
        - success: Successful completion with analysis results
        - error: Execution failure with error details
        - other: General response frames (logged but not specially processed)
    """
    frame_status = frame.get("status")
    frame_message = frame.get("message", "")
    frame_timestamp = frame.get("ts")

    # Record all frames in responses for complete audit trail
    test_case["responses"].append(
        {
            "status": frame_status,
            "message": frame_message,
            "timestamp": frame_timestamp,
            "data": frame.get("data"),
        }
    )

    # Handle specific frame types
    if frame_status == "progress":
        # Track progress messages separately for debugging
        test_case["progress_messages"].append(
            {
                "message": frame_message,
                "timestamp": frame_timestamp,
                "data": frame.get("data"),
            }
        )

    elif frame_status == "success":
        # Successful completion - extract analysis results
        test_case["status"] = "success"
        test_case["final_result"] = extract_success_data(frame)

    elif frame_status == "error":
        # Execution error - record error details
        test_case["status"] = "error"
        test_case["errors"].append(
            {
                "type": "execution_error",
                "message": frame_message,
                "timestamp": frame_timestamp,
                "data": frame.get("data"),
            }
        )


def extract_success_data(frame: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract analysis results from successful completion frame.
    
    Processes the data field from success frames to extract the complete
    analysis results generated by the PQL system. Organizes the data into
    a structured format for downstream evaluation.
    
    Args:
        frame (Dict[str, Any]): Success frame containing analysis results
        
    Returns:
        Dict[str, Any]: Structured analysis results ready for evaluation
        
    Analysis Structure:
        - message/timestamp: Completion metadata
        - key_findings: Primary insights from analysis
        - trends_anomalies: Pattern and anomaly analysis
        - recommendations: Actionable suggestions
        - data_quality: Assessment of data completeness/reliability
        - executive_summary: High-level overview
        - key_metrics: Important metric values and thresholds
        - alerts: Alert conditions and recommendations
        - context: Background information and assumptions
        - scores: Quality scores if available
        - evaluation_notes: Additional evaluation metadata
        
    Note:
        This structure matches the expected format for eval_analysis.py
        evaluation modes (executive_summary, key_findings, full).
    """
    data = frame.get("data", {})

    return {
        # Completion metadata
        "message": frame.get("message"),
        "timestamp": frame.get("ts"),
        
        # Core analysis sections
        "key_findings": data.get("key_findings"),
        "trends_anomalies": data.get("trends_anomalies"), 
        "recommendations": data.get("recommendations"),
        "data_quality": data.get("data_quality"),
        "executive_summary": data.get("executive_summary"),
        "key_metrics": data.get("key_metrics"),
        "alerts": data.get("alerts"),
        "context": data.get("context"),
        
        # Quality scoring if available
        "scores": {
            "relevance": data.get("relevance_score"),
            "completeness": data.get("completeness_score"),
            "quality": data.get("quality_score"),
        },
        
        # Additional evaluation metadata
        "evaluation_notes": data.get("evaluation_notes"),
    }


def finalize_test_case(test_case: Dict[str, Any]):
    """
    Finalize test case by calculating duration and determining final status.
    
    Performs final processing of a test case when its WebSocket connection
    is closed. Calculates execution duration and determines final status
    based on execution events.
    
    Args:
        test_case (Dict[str, Any]): Test case structure to finalize
        
    Processing Steps:
        1. Calculate execution duration from start/end timestamps
        2. Determine final status if still "running"
        3. Handle timestamp parsing errors gracefully
        
    Status Determination:
        - "success": Successfully completed (set by success frame)
        - "error": Error occurred (set by error frame or has errors)
        - "incomplete": Connection closed without clear completion
        
    Duration Calculation:
        - Uses ISO format timestamps from WebSocket events
        - Handles timezone information (Z suffix -> +00:00)
        - Sets duration to None if calculation fails
    """
    start_time_str = test_case.get("start_time")
    end_time_str = test_case.get("end_time")

    # Calculate execution duration if timestamps available
    if start_time_str and end_time_str:
        try:
            # Parse ISO timestamps with timezone handling
            start_time = datetime.fromisoformat(start_time_str.replace("Z", "+00:00"))
            end_time = datetime.fromisoformat(end_time_str.replace("Z", "+00:00"))
            duration = (end_time - start_time).total_seconds()
            test_case["duration"] = duration
        except ValueError:
            # Handle timestamp parsing errors
            test_case["duration"] = None
    else:
        test_case["duration"] = None

    # Determine final status if still running
    if test_case["status"] == "running":
        if test_case["errors"]:
            # Had errors during execution
            test_case["status"] = "error"
        else:
            # No clear completion or error
            test_case["status"] = "incomplete"


def generate_summary(results: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate comprehensive summary statistics from test execution results.
    
    Analyzes test case results to provide statistical overview of test run
    performance, success rates, and execution metrics.
    
    Args:
        results (Dict[str, Any]): Complete test results with test_cases array
        
    Returns:
        Dict[str, Any]: Summary statistics for the test run
        
    Summary Metrics:
        - total_tests: Total number of test cases executed
        - successful_tests: Count of successfully completed test cases
        - failed_tests: Count of test cases that encountered errors
        - incomplete_tests: Count of test cases that didn't complete cleanly
        - success_rate: Percentage of tests that completed successfully
        - total_duration: Sum of all test case execution times
        - average_duration: Mean execution time per test case
        - test_names: List of all test case names for reference
        
    Calculation Notes:
        - Success rate calculated as successful_tests / total_tests
        - Duration calculations exclude test cases without timing data
        - Handles division by zero for empty test runs
    """
    test_cases = results.get("test_cases", [])

    # Count test cases by status
    total_tests = len(test_cases)
    successful_tests = len([tc for tc in test_cases if tc["status"] == "success"])
    failed_tests = len([tc for tc in test_cases if tc["status"] == "error"])
    incomplete_tests = len([tc for tc in test_cases if tc["status"] == "incomplete"])

    # Calculate timing statistics
    test_durations = [tc.get("duration", 0) for tc in test_cases if tc.get("duration")]
    total_duration = sum(test_durations)
    average_duration = total_duration / total_tests if total_tests > 0 else 0

    return {
        "total_tests": total_tests,
        "successful_tests": successful_tests,
        "failed_tests": failed_tests,
        "incomplete_tests": incomplete_tests,
        "success_rate": successful_tests / total_tests if total_tests > 0 else 0,
        "total_duration": total_duration,
        "average_duration": average_duration,
        "test_names": [tc["name"] for tc in test_cases],
    }


def save_results(results: Dict[str, Any], output_file: Path):
    """
    Save structured test results to JSON file with summary statistics.
    
    Adds summary statistics and generation timestamp to results before
    saving to JSON file. Creates parent directories if needed.
    
    Args:
        results (Dict[str, Any]): Complete test results to save
        output_file (Path): Path where JSON file should be written
        
    Output Enhancements:
        - Adds "summary" section with test run statistics
        - Adds "generated_at" timestamp for result freshness tracking
        - Uses proper JSON formatting with indentation
        - Preserves Unicode characters in output
        
    File Format:
        - 2-space indentation for readability
        - UTF-8 encoding for international character support
        - Complete test case data preserved for evaluation tools
    """
    # Add summary statistics to results
    results["summary"] = generate_summary(results)
    results["generated_at"] = datetime.now().isoformat()

    # Ensure parent directory exists
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Save with proper formatting
    with open(output_file, "w", encoding="utf-8") as file:
        json.dump(results, file, indent=2, ensure_ascii=False)


def main():
    """
    Main entry point for log parsing and result generation.
    
    Handles command-line arguments, file validation, log parsing,
    and result output. Provides user feedback and error handling
    throughout the process.
    
    Command-line Arguments:
        log_file: Path to JSONL log file from WebSocket test execution
        --output, -o: Output JSON file path (default: test_results.json)
        
    Returns:
        int: Exit code (0 for success, 1 for failure)
        
    Process Flow:
        1. Validate input log file exists
        2. Parse JSONL log into structured results
        3. Generate summary statistics
        4. Save to JSON file with formatting
        5. Display summary to user
        
    Output Display:
        - Total test cases processed
        - Individual test case status and timing
        - Success/error/incomplete breakdown via summary
    """
    # Configure command-line argument parsing
    parser = argparse.ArgumentParser(
        description="Parse JSONL test log files and generate structured JSON results"
    )
    parser.add_argument("log_file", help="Path to JSONL log file to parse")
    parser.add_argument(
        "--output", "-o", default="test_results.json", 
        help="Output JSON file path (default: test_results.json)"
    )
    args = parser.parse_args()

    # Validate input and output paths
    log_file_path = Path(args.log_file)
    output_file_path = Path(args.output)

    # Check if input file exists
    if not log_file_path.exists():
        print(f"Error: Log file {log_file_path} not found")
        return 1

    # Process log file
    print(f"Parsing log file: {log_file_path}")
    results = parse_log_file(log_file_path)

    # Save structured results
    print(f"Saving results to: {output_file_path}")
    save_results(results, output_file_path)

    # Display processing summary
    print("Parsing completed successfully")
    print(f"Found {len(results['test_cases'])} test cases")

    # Show individual test case results
    for test_case in results["test_cases"]:
        status = test_case["status"]
        name = test_case["name"]
        duration = test_case.get("duration")
        duration_str = f" ({duration:.2f}s)" if duration else ""
        print(f"  - {name}: {status}{duration_str}")

    return 0


if __name__ == "__main__":
    # Execute main function and exit with appropriate code
    exit(main())
