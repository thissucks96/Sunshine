from __future__ import annotations

from pathlib import Path
import sys

from PIL import Image
from openai import OpenAI

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from config import get_config
from llm_pipeline import (
    GRAPH_EVIDENCE_EXTRACTION_MODEL,
    _responses_text,
    image_to_base64_png,
)
from utils import normalize_image_for_api


TARGET_IMAGE = Path("tests/GRAPH_CHECKER/graph_only_tagged_v1/Medium/graph is present (14).png")
RUNS = 3
TIMEOUT_SECONDS = 45

FORENSIC_PROMPT = (
    "Analyze this graph image in extreme detail.\n\n"
    "Describe the red curve. Where does it start and end?\n\n"
    "Locate the brown straight lines.\n\n"
    "Trace the vertical brown line down to the x-axis. What number does it touch exactly?\n\n"
    "Trace the horizontal brown line to the left to the y-axis. What number does it touch exactly?\n\n"
    "Do these two brown lines intersect? If so, does the intersection lie on the red curve?\n\n"
    "Based on this, what is the exact (x, y) coordinate of this intersection?"
)


def _load_image_b64(image_path: Path) -> str:
    cfg = get_config()
    with Image.open(str(image_path)) as im:
        prepared = normalize_image_for_api(im.convert("RGB"), cfg)
    return image_to_base64_png(prepared)


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    if not TARGET_IMAGE.exists():
        raise FileNotFoundError(f"Target image not found: {TARGET_IMAGE}")

    client = OpenAI()
    img_b64 = _load_image_b64(TARGET_IMAGE)

    payload = [
        {"role": "system", "content": [{"type": "input_text", "text": "You are a careful visual analyst."}]},
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": FORENSIC_PROMPT},
                {"type": "input_image", "image_url": f"data:image/png;base64,{img_b64}"},
            ],
        },
    ]

    print(f"Target: {TARGET_IMAGE}")
    print(f"Model: {GRAPH_EVIDENCE_EXTRACTION_MODEL}")
    print(f"Runs: {RUNS}, Temperature: 0")
    print("=" * 80)

    for idx in range(1, RUNS + 1):
        text = _responses_text(
            client=client,
            model_name=GRAPH_EVIDENCE_EXTRACTION_MODEL,
            input_payload=payload,
            timeout=TIMEOUT_SECONDS,
            temperature=0.0,
            max_output_tokens=900,
            flow_name="diagnose_file_14_forensic",
            request_id=f"diagnose-file-14-run-{idx}",
        )
        print(f"RUN {idx}")
        print("-" * 80)
        print((text or "").strip())
        print("=" * 80)


if __name__ == "__main__":
    main()
