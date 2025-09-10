#!/usr/bin/env python3
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
    return datetime.now(UTC).isoformat(timespec="seconds")


def ws_url(host: str, port: int, endpoint_id: str) -> str:
    return f"ws://{host}:{port}/story/ep/{endpoint_id}/grun/ws"


def mk_request(test_case: Dict[str, Any], session_id: str) -> Dict[str, Any]:
    req = {
        "prompt": test_case["prompt"],
        "env_id": test_case.get("env_id", "default"),
        "session_id": session_id,
    }
    if isinstance(test_case.get("additional_params"), dict):
        req.update(test_case["additional_params"])
    return req


def should_close(frame: Any) -> bool:
    return isinstance(frame, dict) and frame.get("status") in {"success", "error"}


class JsonlLogger:
    def __init__(self, path: Path, flush_every: int = 5) -> None:
        self.path = path
        self.flush_every = flush_every
        self._n = 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # create file atomically
        self.path.touch(exist_ok=True)

    def write(self, obj: Dict[str, Any]) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
            self._n += 1
            if self._n % self.flush_every == 0:
                f.flush()
                os.fsync(f.fileno())


async def run_case(
    case: Dict[str, Any],
    host: str,
    port: int,
    endpoint_id: str,
    api_token: str,
    logger: JsonlLogger,
    recv_timeout: float = 300.0,
) -> None:
    session_id = str(uuid.uuid4())
    name = case["name"]
    url = ws_url(host, port, endpoint_id)

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
        async with websocket_connect(
            url, additional_headers=[("x-api-token", api_token)]
        ) as ws:
            logger.write(
                {
                    "event": "connection_open",
                    "case": name,
                    "session": session_id,
                    "ts": ts(),
                }
            )
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

            while True:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=recv_timeout)
                except asyncio.TimeoutError:
                    logger.write(
                        {
                            "event": "client_timeout",
                            "case": name,
                            "session": session_id,
                            "ts": ts(),
                        }
                    )
                    break

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

                # texto
                try:
                    payload = json.loads(raw)
                    if isinstance(payload, dict):
                        payload.setdefault("ts", ts())
                except json.JSONDecodeError:
                    payload = {"raw": raw, "ts": ts()}

                logger.write({"case": name, "session": session_id, "frame": payload})

                if should_close(payload):
                    break

    except Exception as e:
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
        logger.write(
            {
                "event": "connection_closed",
                "case": name,
                "session": session_id,
                "ts": ts(),
            }
        )


def load_cases(path: str) -> List[Dict[str, Any]]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def setup_log(runs_dir: str) -> JsonlLogger:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return JsonlLogger(Path(runs_dir) / f"{stamp}.log")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Slim WebSocket test client for story endpoints"
    )
    p.add_argument("--host", default="localhost")
    p.add_argument("--port", type=int, default=9999)
    p.add_argument("--endpoint-id", default="default")
    p.add_argument("--api-token", required=True)
    p.add_argument("--test-cases", default="test_cases.json")
    p.add_argument("--runs-dir", default="runs")
    p.add_argument("--flush-every", type=int, default=5)
    return p.parse_args()


async def main_async(args: argparse.Namespace) -> None:
    logger = setup_log(args.runs_dir)
    logger.write(
        {
            "event": "run_header",
            "ts": ts(),
            "endpoint_id": args.endpoint_id,
            "url": ws_url(args.host, args.port, args.endpoint_id),
        }
    )

    cases = load_cases(args.test_cases)
    for case in cases:
        await run_case(
            case, args.host, args.port, args.endpoint_id, args.api_token, logger
        )
    print(f"[OK] Raw frames saved to {logger.path}")


def main() -> None:
    args = parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
