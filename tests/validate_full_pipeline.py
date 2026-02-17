from __future__ import annotations

import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from openai import OpenAI, RateLimitError

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import llm_pipeline


DATASET_ROOT = REPO_ROOT / "tests" / "GRAPH_CHECKER" / "graph_only_tagged_v1"
LIGHT_REPORT = REPO_ROOT / "tests" / "GRAPH_CHECKER" / "system_acceptance_light_20260216.txt"
DARK_REPORT = REPO_ROOT / "tests" / "GRAPH_CHECKER" / "system_acceptance_dark_20260216.txt"
EXTRACTION_TIMEOUT = 45
DETECTION_TIMEOUT = 12
MAX_ATTEMPTS = 5


@dataclass
class CaseResult:
    tier: str
    file: str
    phase: str
    passed: bool
    reason: str
    parsed: Optional[Dict[str, object]]


def _parse_xy(token: str) -> Optional[Tuple[float, float]]:
    m = re.search(r"(?i)x\s*=\s*([+-]?\d+(?:\.\d+)?)\s*,\s*y\s*=\s*([+-]?\d+(?:\.\d+)?)", str(token or ""))
    if not m:
        return None
    try:
        return float(m.group(1)), float(m.group(2))
    except Exception:
        return None


def _contains_xy(tokens: List[str], x_target: float, y_target: float, tol: float = 0.30) -> bool:
    for token in tokens:
        parsed = _parse_xy(token)
        if parsed is None:
            continue
        x, y = parsed
        if abs(x - x_target) <= tol and abs(y - y_target) <= tol:
            return True
    return False


def _has_asymptote(parsed: Dict[str, object], target: str) -> bool:
    needle = str(target or "").lower().replace(" ", "")
    for token in (parsed.get("asymptotes", []) or []):
        hay = str(token or "").lower().replace(" ", "")
        if needle in hay:
            return True
    return False


def _retry_sleep_seconds(err_msg: str, attempt: int) -> float:
    m = re.search(r"try again in\s*([0-9]+)\s*ms", err_msg, re.I)
    if m:
        try:
            return max(1.0, int(m.group(1)) / 1000.0)
        except Exception:
            pass
    return min(10.0, 2.0 * (2 ** max(0, attempt - 1)))


def _run_detection(client: OpenAI, image_path: Path) -> Tuple[bool, str]:
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            detected = llm_pipeline.has_graph(
                image_path=str(image_path),
                client=client,
                timeout=DETECTION_TIMEOUT,
            )
            return detected, ""
        except RateLimitError as e:
            delay = _retry_sleep_seconds(str(e), attempt)
            time.sleep(delay)
        except Exception as e:
            return False, f"detection_error={e}"
    return False, "detection_error=rate_limited"


def _run_extraction(client: OpenAI, image_path: Path) -> Tuple[Optional[str], str]:
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            raw = llm_pipeline.extract_graph_evidence(
                image_path=str(image_path),
                client=client,
                model_name=llm_pipeline.GRAPH_EVIDENCE_EXTRACTION_MODEL,
                timeout=EXTRACTION_TIMEOUT,
            )
            if not raw or str(raw).strip().upper() == "INVALID_GRAPH":
                return None, "extract_invalid_graph"
            return raw, ""
        except RateLimitError as e:
            delay = _retry_sleep_seconds(str(e), attempt)
            time.sleep(delay)
        except Exception as e:
            return None, f"extract_error={e}"
    return None, "extract_error=rate_limited"


def _evaluate_strict(tier: str, file_name: str, parsed: Dict[str, object]) -> Tuple[bool, str]:
    left = parsed.get("left_endpoint", {}) or {}
    right = parsed.get("right_endpoint", {}) or {}
    left_marker = str(left.get("marker", "")).strip().lower()
    right_marker = str(right.get("marker", "")).strip().lower()
    valid_markers = {"open", "closed", "arrow", "unclear"}
    if left_marker not in valid_markers or right_marker not in valid_markers:
        return False, "invalid_endpoint_marker"

    intercepts = list(parsed.get("intercepts", []) or [])
    key_points = list(parsed.get("key_points", []) or [])

    if tier == "Easy":
        return True, "ok"

    if tier == "Medium":
        if file_name in {
            "graph is present (10).png",
            "graph is present (11).png",
            "graph is present (12).png",
            "graph is present (13).png",
        }:
            return (len(intercepts) > 0, "ok" if intercepts else "intercepts_empty")
        if file_name in {
            "graph is present (14).png",
            "graph is present (15).png",
            "graph is present (16).png",
        }:
            ok = _contains_xy(key_points, 5.0, 13.0, tol=0.30)
            return (ok, "ok" if ok else f"key_point_missing_(5,13)_got={key_points}")
        if file_name == "graph is present (17).png":
            return (len(key_points) > 0, "ok" if key_points else "key_points_empty")
        if file_name in {
            "graph is present (7).png",
            "graph is present (8).png",
            "graph is present (22).png",
            "graph is present (23).png",
            "graph is present (28).png",
            "graph is present (3).png",
            "graph is present (5).png",
        }:
            asymptotes = list(parsed.get("asymptotes", []) or [])
            return (len(asymptotes) > 0, "ok" if asymptotes else "asymptotes_empty")
        return True, "ok"

    if tier == "Hard":
        if file_name in {
            "graph is present 0.png",
            "graph is present (4).png",
            "graph is present (30).png",
            "graph is present (31).png",
        }:
            ok = _has_asymptote(parsed, "y=2")
            return (ok, "ok" if ok else f"missing_behavioral_asymptote_y=2 got={parsed.get('asymptotes', [])}")
        if file_name == "graph is present (29).png":
            need = ("x=1", "x=-1", "y=0")
            missing = [n for n in need if not _has_asymptote(parsed, n)]
            return (not missing, "ok" if not missing else f"missing_asymptotes={missing}")
        if "dark mode" in file_name.lower():
            # Stress rule: preserve prior dark-mode benchmark requirement.
            ok = _contains_xy(key_points, 2.0, -2.0, tol=0.30)
            return (ok, "ok" if ok else f"dark_key_point_missing_(2,-2)_got={key_points}")
        return True, "ok"

    return True, "ok"


def _collect_cases(filter_mode: str) -> List[Tuple[str, Path]]:
    cases: List[Tuple[str, Path]] = []
    for tier in ("Easy", "Medium", "Hard"):
        tier_dir = DATASET_ROOT / tier
        if not tier_dir.exists():
            continue
        for path in sorted(tier_dir.glob("*.png")):
            is_dark = "dark mode" in path.name.lower()
            if filter_mode == "light" and is_dark:
                continue
            if filter_mode == "dark" and not is_dark:
                continue
            cases.append((tier, path))
    return cases


def _write_report(path: Path, title: str, cases: List[CaseResult]) -> None:
    passed = sum(1 for c in cases if c.passed)
    total = len(cases)
    pct = (passed / total * 100.0) if total else 0.0
    lines: List[str] = []
    lines.append(title)
    lines.append(f"Total: {passed}/{total} = {pct:.2f}%")
    lines.append("")
    for c in cases:
        status = "PASS" if c.passed else "FAIL"
        lines.append(f"[{c.tier}] {c.file} | {status} | {c.reason}")
    lines.append("")
    lines.append("Failure Summary:")
    failures = [c for c in cases if not c.passed]
    if not failures:
        lines.append("- none")
    else:
        for c in failures:
            lines.append(f"- [{c.tier}] {c.file}: {c.reason}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _run_phase(filter_mode: str, title: str, out_path: Path) -> Tuple[int, int]:
    client = OpenAI()
    results: List[CaseResult] = []
    try:
        for tier, image_path in _collect_cases(filter_mode):
            file_name = image_path.name
            detected, detect_err = _run_detection(client, image_path)
            if detect_err:
                results.append(CaseResult(tier, file_name, filter_mode, False, detect_err, None))
                print(f"[{filter_mode}] [{tier}] {file_name} -> FAIL | {detect_err}")
                continue
            if not detected:
                results.append(CaseResult(tier, file_name, filter_mode, False, "false_negative_detector", None))
                print(f"[{filter_mode}] [{tier}] {file_name} -> FAIL | false_negative_detector")
                continue

            raw, extract_err = _run_extraction(client, image_path)
            if extract_err:
                results.append(CaseResult(tier, file_name, filter_mode, False, extract_err, None))
                print(f"[{filter_mode}] [{tier}] {file_name} -> FAIL | {extract_err}")
                continue

            parsed = llm_pipeline._extract_graph_evidence_block(raw or "")
            if parsed is None:
                results.append(CaseResult(tier, file_name, filter_mode, False, "parse_failed", None))
                print(f"[{filter_mode}] [{tier}] {file_name} -> FAIL | parse_failed")
                continue

            ok, reason = _evaluate_strict(tier, file_name, parsed)
            results.append(CaseResult(tier, file_name, filter_mode, ok, reason, parsed))
            print(f"[{filter_mode}] [{tier}] {file_name} -> {'PASS' if ok else 'FAIL'} | {reason}")
    finally:
        try:
            client.close()
        except Exception:
            pass

    _write_report(out_path, title, results)
    passed = sum(1 for c in results if c.passed)
    total = len(results)
    return passed, total


def main() -> None:
    light_passed, light_total = _run_phase(
        filter_mode="light",
        title="System Acceptance — Light Mode Production Set",
        out_path=LIGHT_REPORT,
    )
    dark_passed, dark_total = _run_phase(
        filter_mode="dark",
        title="System Acceptance — Dark Mode Stress Set",
        out_path=DARK_REPORT,
    )
    print("")
    print(f"LIGHT: {light_passed}/{light_total}")
    print(f"DARK : {dark_passed}/{dark_total}")
    print(f"WROTE: {LIGHT_REPORT}")
    print(f"WROTE: {DARK_REPORT}")


if __name__ == "__main__":
    main()
