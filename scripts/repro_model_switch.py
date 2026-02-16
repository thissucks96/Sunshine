import argparse
import json
import os
import time
import uuid
from typing import Dict, List

from openai import OpenAI


def _is_gpt5_family(model_name: str) -> bool:
    return str(model_name or "").strip().lower().startswith("gpt-5")


def _request_payload(prompt: str) -> List[Dict[str, object]]:
    return [{"role": "user", "content": [{"type": "input_text", "text": prompt}]}]


def _run_call(api_key: str, model: str, timeout: int, max_output_tokens: int, prompt: str) -> Dict[str, object]:
    request_id = f"repro-{uuid.uuid4().hex[:10]}"
    started_unix = time.time()
    started_mono = time.monotonic()
    req = {
        "model": model,
        "input": _request_payload(prompt),
        "timeout": timeout,
        "max_output_tokens": max_output_tokens,
    }
    if not _is_gpt5_family(model):
        req["temperature"] = 0.0

    client = OpenAI(api_key=api_key, max_retries=0)
    try:
        response = client.responses.create(**req)
        ended_unix = time.time()
        elapsed_ms = int((time.monotonic() - started_mono) * 1000)
        output_text = str(getattr(response, "output_text", "") or "").strip()
        return {
            "request_id": request_id,
            "model": model,
            "ok": True,
            "time_started_unix": started_unix,
            "time_completed_unix": ended_unix,
            "time_to_first_byte_ms": None,
            "time_completed_ms": elapsed_ms,
            "retries": 0,
            "timeout_type": "",
            "exception_payload": None,
            "response_model": str(getattr(response, "model", "") or ""),
            "response_status": str(getattr(response, "status", "") or ""),
            "response_incomplete": str(getattr(response, "incomplete_details", "") or ""),
            "output_len": len(output_text),
            "output_sample": output_text[:120],
        }
    except Exception as exc:
        ended_unix = time.time()
        elapsed_ms = int((time.monotonic() - started_mono) * 1000)
        msg = str(exc or "")
        low = msg.lower()
        timeout_type = "request" if "timed out" in low or "timeout" in low else ""
        return {
            "request_id": request_id,
            "model": model,
            "ok": False,
            "time_started_unix": started_unix,
            "time_completed_unix": ended_unix,
            "time_to_first_byte_ms": None,
            "time_completed_ms": elapsed_ms,
            "retries": 0,
            "timeout_type": timeout_type,
            "exception_payload": {
                "type": type(exc).__name__,
                "message": msg,
                "is_timeout": bool(timeout_type),
                "timeout_type": timeout_type,
            },
            "response_model": "",
            "response_status": "",
            "response_incomplete": "",
            "output_len": 0,
            "output_sample": "",
        }
    finally:
        client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Reproduce mid-run model switching call behavior.")
    parser.add_argument("--model-a", default="gpt-5-mini")
    parser.add_argument("--model-b", default="gpt-5.2")
    parser.add_argument("--calls-before", type=int, default=3)
    parser.add_argument("--calls-after", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--max-output-tokens", type=int, default=2200)
    parser.add_argument(
        "--prompt",
        default="Solve quickly: what is the domain and range of y = x^2? Use WORK and FINAL ANSWER.",
    )
    args = parser.parse_args()

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is required.")

    sequence = [args.model_a] * max(1, args.calls_before) + [args.model_b] * max(1, args.calls_after)
    summary = {"total": 0, "ok": 0, "errors": 0, "empty_output": 0}

    print(json.dumps({"event": "repro_start", "model_a": args.model_a, "model_b": args.model_b}))
    for idx, model_name in enumerate(sequence, start=1):
        result = _run_call(
            api_key=api_key,
            model=model_name,
            timeout=max(1, int(args.timeout)),
            max_output_tokens=max(16, int(args.max_output_tokens)),
            prompt=str(args.prompt),
        )
        result["seq"] = idx
        print(json.dumps(result, ensure_ascii=False))
        summary["total"] += 1
        if result.get("ok"):
            summary["ok"] += 1
            if int(result.get("output_len", 0)) <= 0:
                summary["empty_output"] += 1
        else:
            summary["errors"] += 1

    print(json.dumps({"event": "repro_done", "summary": summary}))


if __name__ == "__main__":
    main()
