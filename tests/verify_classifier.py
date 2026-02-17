import argparse
import os
from datetime import datetime
from typing import List

from openai import OpenAI

from config import get_config, resolve_api_key
from llm_pipeline import detect_graph_presence


_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff"}


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


def main() -> int:
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

    timeout = int(cfg.get("classify_timeout", 8))
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_path = os.path.join(folder, f"classifier_results_{ts}.log")

    client = OpenAI(api_key=api_key, max_retries=0)
    try:
        lines: List[str] = []
        for path in images:
            result = detect_graph_presence(
                image_path=path,
                client=client,
                timeout=timeout,
            )
            line = f"{os.path.basename(path)} => {result}"
            lines.append(line)
            print(line)
    finally:
        try:
            client.close()
        except Exception:
            pass

    with open(results_path, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\n")

    print(f"\nSaved classifier results: {results_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
