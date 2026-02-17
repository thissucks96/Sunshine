import argparse
import concurrent.futures
import os
import sys
import time
from datetime import datetime
from typing import List, Tuple

from openai import OpenAI, RateLimitError

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from config import get_config, resolve_api_key
from llm_pipeline import detect_graph_presence


_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff"}
_MAX_WORKERS = 1
_TIMEOUT_SEC = 45
_MAX_ATTEMPTS = 5
_BACKOFF_BASE_SECONDS = 10


def _configure_stdout_utf8() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _collect_images(folder: str) -> List[str]:
    out: List[str] = []
    for name in sorted(os.listdir(folder)):
        path = os.path.join(folder, name)
        if not os.path.isfile(path):
            continue
        _, ext = os.path.splitext(name)
        if ext.lower() in _IMAGE_EXTS:
            out.append(path)
    return out


def _expected_label_from_filename(path: str) -> str:
    name = os.path.basename(path).lower()
    if "not a graph" in name:
        return "NO"
    if "graph is present" in name:
        return "YES"
    if "table" in name:
        return "NO"
    return "NO"


def _normalize_model_label(raw: str) -> str:
    t = str(raw or "").strip().upper()
    if "YES" in t:
        return "YES"
    if "NO" in t:
        return "NO"
    return "NO"


def _rate_limit_sleep_seconds(attempt: int) -> float:
    # Aggressive exponential backoff for Tier-1 rate limits.
    return float(_BACKOFF_BASE_SECONDS * (2 ** max(0, attempt - 1)))


def _is_429_message(message: str) -> bool:
    t = str(message or "").lower()
    return ("rate_limit_exceeded" in t) or ("error code: 429" in t) or ("rate limit reached" in t)


def _append_activity_log(lines: List[str]) -> None:
    path = os.path.join(ROOT, "app_activity.log")
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(path, "a", encoding="utf-8") as f:
            for line in lines:
                f.write(f"{ts} | INFO | verify_classifier | {line}\n")
    except Exception:
        pass


def _classify_single(path: str, client: OpenAI) -> Tuple[str, str, str, str, str]:
    expected = _expected_label_from_filename(path)
    last_reason = ""
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            detection = detect_graph_presence(
                image_path=path,
                client=client,
                timeout=_TIMEOUT_SEC,
            )
        except RateLimitError as e:
            last_reason = f"api_error: {e}"
            if attempt >= _MAX_ATTEMPTS:
                return path, expected, "FATAL_API_ERROR", last_reason, "FATAL_API_ERROR"
            time.sleep(_rate_limit_sleep_seconds(attempt))
            continue

        actual = _normalize_model_label(detection.get("is_graph", "NO"))
        reasoning = str(detection.get("reasoning", "") or "").strip()
        if _is_429_message(reasoning):
            last_reason = reasoning
            if attempt >= _MAX_ATTEMPTS:
                return path, expected, "FATAL_API_ERROR", last_reason, "FATAL_API_ERROR"
            time.sleep(_rate_limit_sleep_seconds(attempt))
            continue
        return path, expected, actual, reasoning, "OK"

    return path, expected, "FATAL_API_ERROR", last_reason or "rate_limit_retry_exhausted", "FATAL_API_ERROR"


def main() -> int:
    _configure_stdout_utf8()
    parser = argparse.ArgumentParser(
        description="Run the graph scout classifier (YES/NO) over a folder of images."
    )
    parser.add_argument(
        "folder",
        nargs="?",
        default=os.path.join("tests", "GRAPH_CHECKER"),
        help="Folder containing graph/non-graph images",
    )
    args = parser.parse_args()
    folder = os.path.abspath(args.folder)

    if not os.path.isdir(folder):
        print(f"Folder not found: {folder}")
        return 1

    cfg = get_config()
    api_key = resolve_api_key(cfg)
    if not api_key:
        print("Missing API key (config.json or OPENAI_API_KEY).")
        return 1

    images = _collect_images(folder)
    if not images:
        print(f"No supported image files found in: {folder}")
        return 1

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_path = os.path.join(folder, f"classifier_results_{ts}.log")

    client = OpenAI(api_key=api_key, max_retries=0)
    try:
        rows: List[Tuple[str, str, str, str, str]] = []
        # max_workers=1 intentionally enforces sequential ground-truth execution.
        with concurrent.futures.ThreadPoolExecutor(max_workers=_MAX_WORKERS) as ex:
            futures = [ex.submit(_classify_single, path, client) for path in images]
            for fut in concurrent.futures.as_completed(futures):
                path, expected, actual, reasoning, status = fut.result()
                rows.append((path, expected, actual, reasoning, status))
                print(
                    f"{os.path.basename(path)} => status:{status} model:{actual} "
                    f"expected:{expected} reason:{reasoning}"
                )
    finally:
        try:
            client.close()
        except Exception:
            pass

    rows.sort(key=lambda x: os.path.basename(x[0]).lower())
    total = len(rows)
    fatal = [r for r in rows if r[4] == "FATAL_API_ERROR"]
    correct = sum(1 for _, expected, actual, _, _ in rows if expected == actual)
    incorrect = sum(1 for _, expected, actual, _, _ in rows if expected != actual)
    accuracy = (correct / total * 100.0) if total else 0.0
    failed = [
        (os.path.basename(path), actual, expected, reasoning)
        for path, expected, actual, reasoning, status in rows
        if expected != actual
    ]
    fatal_rows = [
        (os.path.basename(path), reasoning)
        for path, _, _, reasoning, status in fatal
    ]

    summary_lines = [
        "Classifier Validation Summary",
        f"Total Images Processed: {total}",
        f"Total Correct: {correct}",
        f"Total Incorrect: {incorrect}",
        f"Accuracy Percentage: {accuracy:.2f}%",
        f"Failed Files: {len(failed)}",
        f"Fatal API Errors (counted as incorrect): {len(fatal)}",
        f"Max Workers: {_MAX_WORKERS}",
        f"Per-call Timeout Seconds: {_TIMEOUT_SEC}",
        f"Max Retry Attempts: {_MAX_ATTEMPTS}",
        f"Backoff Base Seconds: {_BACKOFF_BASE_SECONDS}",
    ]
    if failed:
        summary_lines.append("Failed File Details:")
        for name, actual, expected, reasoning in failed:
            summary_lines.append(
                f"- {name} | Model: {actual} | Expected: {expected} | Reason: \"{reasoning}\""
            )
    if fatal_rows:
        summary_lines.append("Fatal API Errors:")
        for name, reason in fatal_rows:
            summary_lines.append(
                f"- {name} | Model: FATAL_API_ERROR | Expected: N/A | Reason: \"{reason}\""
            )

    with open(results_path, "w", encoding="utf-8") as f:
        for path, expected, actual, reasoning, status in rows:
            f.write(
                f"{os.path.basename(path)} => status:{status} model:{actual} "
                f"expected:{expected} reason:{reasoning}\n"
            )
        f.write("\n")
        for line in summary_lines:
            f.write(line + "\n")

    print("")
    for line in summary_lines:
        print(line)
    print(f"\nSaved classifier results: {results_path}")
    _append_activity_log(summary_lines)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
