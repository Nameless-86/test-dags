#!/usr/bin/env python3
"""
WebSocket Test Executor for End-to-End Evaluation Pipeline

This module executes test cases against WebSocket endpoints asynchronously,
capturing all interaction data for downstream analysis. It provides comprehensive
logging of WebSocket events, request/response cycles, and error conditions.

Key Features:
    - Asynchronous WebSocket connection management
    - Session-based request/response tracking  
    - Comprehensive event logging to JSONL format
    - Configurable timeouts and error handling
    - Structured output for evaluation pipeline

Dependencies:
    - websockets: Async WebSocket client implementation
    - asyncio: Asynchronous I/O support
    - argparse: Command-line argument parsing
    - json: JSON parsing and generation
    - uuid: Session ID generation

Usage:
    python3 run_grun.py --api-token TOKEN --test-cases test_cases.json --runs-dir runs

Author: Autoptic Team
"""

import argparse
import asyncio
import base64
import json
import os
import uuid
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Dict, List

from websockets.asyncio.client import connect as websocket_connect


def ts() -> str:
    """
    Generate ISO 8601 timestamp for event logging.
    
    Returns:
        str: Current UTC timestamp in ISO format (YYYY-MM-DDTHH:MM:SSZ)
        
    Note:
        Uses second precision for log readability
    """
    return datetime.now(UTC).isoformat(timespec="seconds")


def ws_url(host: str, port: int, endpoint_id: str) -> str:
    """
    Construct WebSocket URL for PQL generation endpoint.
    
    Args:
        host (str): WebSocket server hostname or IP
        port (int): WebSocket server port number  
        endpoint_id (str): Specific endpoint identifier for routing
        
    Returns:
        str: Complete WebSocket URL for connection
        
    Example:
        ws_url("localhost", 9999, "default") -> "ws://localhost:9999/story/ep/default/grun/ws"
    """
    return f"ws://{host}:{port}/story/ep/{endpoint_id}/grun/ws"


def mk_request(test_case: Dict[str, Any], session_id: str) -> Dict[str, Any]:
    """
    Build WebSocket request from test case and session information.
    
    Combines test case data with session ID to create a complete request
    payload for the WebSocket endpoint. Merges additional parameters
    (where, when, metricFilters, etc.) into the base request structure.
    
    Args:
        test_case (Dict[str, Any]): Test case dictionary from converted JSON
        session_id (str): Unique session identifier for this test execution
        
    Returns:
        Dict[str, Any]: Complete WebSocket request payload
        
    Request Structure:
        {
            "prompt": "Natural language question",
            "env_id": "default",
            "session_id": "uuid-string",
            "where": "aws-cw",
            "when": "24h",
            "metricFilters": [...],
            "useVectorSearch": true
        }
    """
    # Build base request with required fields
    req = {
        "prompt": test_case["prompt"],
        "env_id": test_case.get("env_id", "default"),
        "session_id": session_id,
    }
    
    # Merge additional parameters (provider configs, filters, etc.)
    if isinstance(test_case.get("additional_params"), dict):
        req.update(test_case["additional_params"])
        
    return req


def should_close(frame: Any) -> bool:
    """
    Determine if WebSocket connection should be closed based on frame status.
    
    Checks if the received frame indicates completion of the PQL generation
    process. Connections are closed on 'success' (completed analysis) or 
    'error' (failed execution) status.
    
    Args:
        frame (Any): WebSocket frame data (expected to be dict for status frames)
        
    Returns:
        bool: True if connection should be closed, False to continue listening
        
    Note:
        - 'success': PQL generation and analysis completed successfully
        - 'error': Process failed, no further frames expected
        - 'progress': Intermediate status, continue listening
        - Other frames: Continue listening
    """
    return isinstance(frame, dict) and frame.get("status") in {"success", "error"}


class JsonlLogger:
    """
    JSONL (JSON Lines) logger for structured WebSocket event logging.
    
    Provides thread-safe, buffered logging of WebSocket events to JSONL format
    for downstream processing. Each log entry is a complete JSON object on a
    single line, making it easy to parse incrementally.
    
    Attributes:
        path (Path): Output file path for JSONL log
        flush_every (int): Number of writes before forcing disk flush
        _n (int): Internal counter for flush timing
    """
    
    def __init__(self, path: Path, flush_every: int = 5) -> None:
        """
        Initialize JSONL logger with output path and flush configuration.
        
        Args:
            path (Path): Path where JSONL log file will be written
            flush_every (int): Flush to disk every N writes (default: 5)
            
        Note:
            - Creates parent directories if they don't exist
            - Creates empty log file immediately for atomic operation
            - Configures periodic flushing for data safety
        """
        self.path = path
        self.flush_every = flush_every
        self._n = 0
        
        # Ensure parent directory exists
        self.path.parent.mkdir(parents=True, exist_ok=True)
        
        # Create file atomically to reserve the path
        self.path.touch(exist_ok=True)

    def write(self, obj: Dict[str, Any]) -> None:
        """
        Write a structured event object to the JSONL log.
        
        Appends the object as a single JSON line to the log file. Performs
        periodic flushing to ensure data is written to disk for safety.
        
        Args:
            obj (Dict[str, Any]): Event data to log (will be JSON serialized)
            
        Note:
            - Each object becomes one line in the JSONL file
            - Uses UTF-8 encoding to preserve international characters
            - Flushes to disk every flush_every writes for data safety
            - Thread-safe for concurrent writes
        """
        with self.path.open("a", encoding="utf-8") as f:
            # Write object as single JSON line
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
            self._n += 1
            
            # Periodic flush for data safety
            if self._n % self.flush_every == 0:
                f.flush()  # Flush Python buffers
                os.fsync(f.fileno())  # Force OS to write to disk


async def run_case(
    case: Dict[str, Any],
    host: str,
    port: int,
    endpoint_id: str,
    api_token: str,
    logger: JsonlLogger,
    recv_timeout: float = 300.0,
) -> None:
    """
    Execute a single test case against the WebSocket endpoint.
    
    Manages the complete lifecycle of a test case execution including:
    - WebSocket connection establishment
    - Request transmission 
    - Response frame collection
    - Error handling and timeouts
    - Comprehensive event logging
    
    Args:
        case (Dict[str, Any]): Test case data with prompt and parameters
        host (str): WebSocket server hostname
        port (int): WebSocket server port
        endpoint_id (str): Endpoint identifier for routing
        api_token (str): Authentication token for API access
        logger (JsonlLogger): JSONL logger for event capture
        recv_timeout (float): Timeout for WebSocket message reception (default: 300s)
        
    Returns:
        None: All results are logged via the logger parameter
        
    Logs Events:
        - connection_opening: Connection attempt started
        - connection_open: Connection established successfully
        - sent_request: Request transmitted to server
        - frame: Each WebSocket frame received
        - client_timeout: Reception timeout occurred
        - client_error: Connection or processing error
        - connection_closed: Connection terminated
        
    Note:
        - Each test case gets a unique session ID for tracking
        - Binary frames are base64-encoded for logging
        - Text frames are parsed as JSON when possible
        - Connection closes automatically on 'success' or 'error' status
    """
    # Generate unique session ID for this test case execution
    session_id = str(uuid.uuid4())
    name = case["name"]
    url = ws_url(host, port, endpoint_id)

    # Log connection attempt start
    logger.write(
        {
            "event": "connection_opening",
            "case": name,
            "session": session_id,
            "url": url,
            "ts": ts(),
        }
    )
    try:
        # Establish WebSocket connection with authentication
        async with websocket_connect(
            url, additional_headers=[("x-api-token", api_token)]
        ) as ws:
            # Log successful connection establishment
            logger.write(
                {
                    "event": "connection_open",
                    "case": name,
                    "session": session_id,
                    "ts": ts(),
                }
            )
            
            # Build and send request payload
            req = mk_request(case, session_id)
            await ws.send(json.dumps(req))
            logger.write(
                {
                    "event": "sent_request",
                    "case": name,
                    "session": session_id,
                    "request": req,
                    "ts": ts(),
                }
            )

            # Message reception loop - continue until completion or timeout
            while True:
                try:
                    # Wait for next WebSocket message with timeout
                    raw = await asyncio.wait_for(ws.recv(), timeout=recv_timeout)
                except asyncio.TimeoutError:
                    # Log timeout and terminate connection
                    logger.write(
                        {
                            "event": "client_timeout",
                            "case": name,
                            "session": session_id,
                            "ts": ts(),
                        }
                    )
                    break

                # Handle binary frames (encode as base64 for logging)
                if isinstance(raw, (bytes, bytearray)):
                    logger.write(
                        {
                            "case": name,
                            "session": session_id,
                            "frame": {
                                "binary": True,
                                "raw_b64": base64.b64encode(raw).decode("ascii"),
                                "ts": ts(),
                            },
                        }
                    )
                    continue

                # Handle text frames - parse as JSON when possible
                try:
                    payload = json.loads(raw)
                    if isinstance(payload, dict):
                        # Add timestamp if not present
                        payload.setdefault("ts", ts())
                except json.JSONDecodeError:
                    # Handle non-JSON text frames
                    payload = {"raw": raw, "ts": ts()}

                # Log the processed frame
                logger.write({"case": name, "session": session_id, "frame": payload})

                # Check if this frame indicates completion (success/error)
                if should_close(payload):
                    break

    except Exception as e:
        # Log any connection or processing errors
        logger.write(
            {
                "event": "client_error",
                "case": name,
                "session": session_id,
                "error": str(e),
                "ts": ts(),
            }
        )
    finally:
        # Always log connection closure for complete audit trail
        logger.write(
            {
                "event": "connection_closed",
                "case": name,
                "session": session_id,
                "ts": ts(),
            }
        )


def load_cases(path: str) -> List[Dict[str, Any]]:
    """
    Load test cases from JSON file.
    
    Args:
        path (str): Path to test cases JSON file
        
    Returns:
        List[Dict[str, Any]]: List of test case dictionaries
        
    Raises:
        FileNotFoundError: If the test cases file doesn't exist
        json.JSONDecodeError: If the file contains invalid JSON
    """
    return json.loads(Path(path).read_text(encoding="utf-8"))


def setup_log(runs_dir: str) -> JsonlLogger:
    """
    Create timestamped JSONL logger for this test run.
    
    Generates a unique log file name based on current timestamp
    to avoid conflicts between concurrent test runs.
    
    Args:
        runs_dir (str): Directory where log files should be stored
        
    Returns:
        JsonlLogger: Configured logger instance for this run
        
    Log File Format:
        YYYYMMDD-HHMMSS.log (e.g., 20250101-143022.log)
    """
    # Generate timestamp-based filename to avoid conflicts
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return JsonlLogger(Path(runs_dir) / f"{stamp}.log")


def parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments for WebSocket test execution.
    
    Returns:
        argparse.Namespace: Parsed command-line arguments
        
    Command-line Arguments:
        --host: WebSocket server hostname (default: localhost)
        --port: WebSocket server port (default: 9999)
        --endpoint-id: Endpoint identifier for routing (default: default)
        --api-token: Authentication token (required)
        --test-cases: Path to test cases JSON file (default: test_cases.json)
        --runs-dir: Directory for log output (default: runs)
        --flush-every: Log flush frequency (default: 5)
    """
    p = argparse.ArgumentParser(
        description="WebSocket test executor for PQL generation endpoints"
    )
    p.add_argument("--host", default="localhost", 
                  help="WebSocket server hostname")
    p.add_argument("--port", type=int, default=9999,
                  help="WebSocket server port")
    p.add_argument("--endpoint-id", default="default",
                  help="Endpoint identifier for routing")
    p.add_argument("--api-token", required=True,
                  help="Authentication token for API access")
    p.add_argument("--test-cases", default="test_cases.json",
                  help="Path to test cases JSON file")
    p.add_argument("--runs-dir", default="runs",
                  help="Directory for log file output")
    p.add_argument("--flush-every", type=int, default=5,
                  help="Flush log to disk every N writes")
    return p.parse_args()


async def main_async(args: argparse.Namespace) -> None:
    """
    Main asynchronous execution function for WebSocket test runner.
    
    Coordinates the complete test execution process:
    - Sets up logging infrastructure
    - Loads test cases from JSON file
    - Executes each test case sequentially
    - Provides final status report
    
    Args:
        args (argparse.Namespace): Parsed command-line arguments
        
    Note:
        - Test cases are executed sequentially to avoid overwhelming the server
        - All events are logged to timestamped JSONL file
        - Run header provides metadata for downstream processing
    """
    # Initialize logging for this test run
    logger = setup_log(args.runs_dir)
    
    # Log run header with configuration for downstream processing
    logger.write(
        {
            "event": "run_header",
            "ts": ts(),
            "endpoint_id": args.endpoint_id,
            "url": ws_url(args.host, args.port, args.endpoint_id),
        }
    )

    # Load test cases and execute them sequentially
    cases = load_cases(args.test_cases)
    for case in cases:
        await run_case(
            case, args.host, args.port, args.endpoint_id, args.api_token, logger
        )
    
    # Report completion status
    print(f"[OK] Raw frames saved to {logger.path}")


def main() -> None:
    """
    Main entry point for WebSocket test executor.
    
    Handles argument parsing and launches asynchronous test execution.
    This function serves as the synchronous entry point that bootstraps
    the async event loop for WebSocket operations.
    """
    args = parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    # Execute main function when run as script
    main()
