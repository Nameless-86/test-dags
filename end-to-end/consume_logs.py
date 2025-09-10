import json
import argparse
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime


def parse_log_file(log_file_path: Path) -> Dict[str, Any]:
    """Parse a log file and extract structured test results."""
    with open(log_file_path, "r", encoding="utf-8") as file:
        lines = file.readlines()

    results = {"run_info": {}, "test_cases": []}

    current_test_case = None

    for line in lines:
        try:
            log_entry = json.loads(line.strip())
        except json.JSONDecodeError:
            continue

        event_type = log_entry.get("event")

        if event_type == "run_header":
            results["run_info"] = extract_run_header(log_entry)

        elif event_type == "connection_opening":
            current_test_case = initialize_test_case(log_entry)

        elif event_type == "sent_request":
            if current_test_case:
                current_test_case["request"] = extract_request_data(log_entry)

        elif "case" in log_entry and "frame" in log_entry:
            if current_test_case and log_entry["case"] == current_test_case["name"]:
                process_frame_data(current_test_case, log_entry["frame"])

        elif event_type == "connection_closed":
            if current_test_case:
                current_test_case["end_time"] = log_entry.get("ts")
                finalize_test_case(current_test_case)
                results["test_cases"].append(current_test_case)
                current_test_case = None

        elif event_type in ["client_error", "client_timeout"]:
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
    """Extract run header information."""
    return {
        "timestamp": log_entry.get("ts"),
        "endpoint_id": log_entry.get("endpoint_id"),
        "websocket_url": log_entry.get("url"),
    }


def initialize_test_case(log_entry: Dict[str, Any]) -> Dict[str, Any]:
    """Initialize a new test case structure."""
    return {
        "name": log_entry.get("case"),
        "session_id": log_entry.get("session"),
        "start_time": log_entry.get("ts"),
        "end_time": None,
        "duration": None,
        "status": "running",
        "request": {},
        "responses": [],
        "final_result": {},
        "errors": [],
        "progress_messages": [],
    }


def extract_request_data(log_entry: Dict[str, Any]) -> Dict[str, Any]:
    """Extract request data from sent_request event."""
    request_data = log_entry.get("request", {})
    return {
        "prompt": request_data.get("prompt"),
        "env_id": request_data.get("env_id"),
        "where": request_data.get("where"),
        "when": request_data.get("when"),
        "metric_filters": request_data.get("metricFilters", []),
        "use_vector_search": request_data.get("useVectorSearch", False),
        "additional_params": {
            k: v
            for k, v in request_data.items()
            if k
            not in [
                "prompt",
                "env_id",
                "session_id",
                "where",
                "when",
                "metricFilters",
                "useVectorSearch",
            ]
        },
    }


def process_frame_data(test_case: Dict[str, Any], frame: Dict[str, Any]):
    """Process frame data and update test case."""
    frame_status = frame.get("status")
    frame_message = frame.get("message", "")
    frame_timestamp = frame.get("ts")

    test_case["responses"].append(
        {
            "status": frame_status,
            "message": frame_message,
            "timestamp": frame_timestamp,
            "data": frame.get("data"),
        }
    )

    if frame_status == "progress":
        test_case["progress_messages"].append(
            {
                "message": frame_message,
                "timestamp": frame_timestamp,
                "data": frame.get("data"),
            }
        )

    elif frame_status == "success":
        test_case["status"] = "success"
        test_case["final_result"] = extract_success_data(frame)

    elif frame_status == "error":
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
    """Extract success data from final frame."""
    data = frame.get("data", {})

    return {
        "message": frame.get("message"),
        "timestamp": frame.get("ts"),
        "key_findings": data.get("key_findings"),
        "trends_anomalies": data.get("trends_anomalies"),
        "recommendations": data.get("recommendations"),
        "data_quality": data.get("data_quality"),
        "executive_summary": data.get("executive_summary"),
        "key_metrics": data.get("key_metrics"),
        "alerts": data.get("alerts"),
        "context": data.get("context"),
        "scores": {
            "relevance": data.get("relevance_score"),
            "completeness": data.get("completeness_score"),
            "quality": data.get("quality_score"),
        },
        "evaluation_notes": data.get("evaluation_notes"),
    }


def finalize_test_case(test_case: Dict[str, Any]):
    """Finalize test case by calculating duration and final status."""
    start_time_str = test_case.get("start_time")
    end_time_str = test_case.get("end_time")

    if start_time_str and end_time_str:
        try:
            start_time = datetime.fromisoformat(start_time_str.replace("Z", "+00:00"))
            end_time = datetime.fromisoformat(end_time_str.replace("Z", "+00:00"))
            duration = (end_time - start_time).total_seconds()
            test_case["duration"] = duration
        except ValueError:
            test_case["duration"] = None
    else:
        test_case["duration"] = None

    if test_case["status"] == "running":
        if test_case["errors"]:
            test_case["status"] = "error"
        else:
            test_case["status"] = "incomplete"


def generate_summary(results: Dict[str, Any]) -> Dict[str, Any]:
    """Generate summary statistics from test results."""
    test_cases = results.get("test_cases", [])

    total_tests = len(test_cases)
    successful_tests = len([tc for tc in test_cases if tc["status"] == "success"])
    failed_tests = len([tc for tc in test_cases if tc["status"] == "error"])
    incomplete_tests = len([tc for tc in test_cases if tc["status"] == "incomplete"])

    total_duration = sum(
        [tc.get("duration", 0) for tc in test_cases if tc.get("duration")]
    )
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
    """Save results to JSON file."""
    results["summary"] = generate_summary(results)
    results["generated_at"] = datetime.now().isoformat()

    with open(output_file, "w", encoding="utf-8") as file:
        json.dump(results, file, indent=2, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser(
        description="Parse test log files and generate structured JSON results"
    )
    parser.add_argument("log_file", help="Path to the log file to parse")
    parser.add_argument(
        "--output", "-o", default="test_results.json", help="Output JSON file"
    )
    args = parser.parse_args()

    log_file_path = Path(args.log_file)
    output_file_path = Path(args.output)

    if not log_file_path.exists():
        print(f"Error: Log file {log_file_path} not found")
        return 1

    print(f"Parsing log file: {log_file_path}")
    results = parse_log_file(log_file_path)

    print(f"Saving results to: {output_file_path}")
    save_results(results, output_file_path)

    print("Parsing completed successfully")
    print(f"Found {len(results['test_cases'])} test cases")

    for test_case in results["test_cases"]:
        status = test_case["status"]
        name = test_case["name"]
        duration = test_case.get("duration")
        duration_str = f" ({duration:.2f}s)" if duration else ""
        print(f"  - {name}: {status}{duration_str}")

    return 0


if __name__ == "__main__":
    exit(main())
