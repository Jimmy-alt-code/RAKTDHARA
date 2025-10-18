import os
import re
import sys
import json
import base64
from pathlib import Path
import requests

# Configuration
WORKDIR = Path(__file__).resolve().parent
MARKDOWN_FILE = WORKDIR / "ARCHITECTURE.md"
OUTPUT_DIR = WORKDIR / "docs" / "diagrams"
KROKI_URL = os.environ.get("KROKI_URL", "https://kroki.io")
FORMAT = "png"

# Map diagram titles (closest preceding heading) to output filenames
FILENAME_BY_TITLE = {
    "High-level Architecture (from User)": "high_level.png",
    "Login & Role Routing Flow": "login_flow.png",
    "Donor Registration & Availability": "donor_registration.png",
    "Create Blood Request (Requester or Public Form)": "create_request.png",
    "Admin Management & Matching": "admin_management.png",
    "Data Model Overview": "data_model.png",
}

HEADING_RE = re.compile(r"^#{2,6}\s*(.+?)\s*$")
MERMAID_START = re.compile(r"^```mermaid\s*$")
MERMAID_END = re.compile(r"^```\s*$")


def ensure_output_dir() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def read_markdown() -> str:
    if not MARKDOWN_FILE.exists():
        print(f"Missing file: {MARKDOWN_FILE}", file=sys.stderr)
        sys.exit(1)
    return MARKDOWN_FILE.read_text(encoding="utf-8")


def extract_mermaid_blocks(md_text: str):
    blocks = []
    current_heading = None
    lines = md_text.splitlines()
    inside = False
    buf = []
    heading_for_block = None

    for line in lines:
        m = HEADING_RE.match(line)
        if m and not inside:
            current_heading = m.group(1).strip()
            continue

        if MERMAID_START.match(line):
            inside = True
            buf = []
            heading_for_block = current_heading
            continue

        if inside and MERMAID_END.match(line):
            inside = False
            code = "\n".join(buf).strip() + "\n"
            blocks.append((heading_for_block, code))
            buf = []
            heading_for_block = None
            continue

        if inside:
            buf.append(line)

    return blocks


def render_with_kroki(mermaid_code: str) -> bytes:
    # Kroki diagram endpoint: /mermaid/png (POST with text/plain body)
    url = f"{KROKI_URL.rstrip('/')}/mermaid/{FORMAT}"
    headers = {"Content-Type": "text/plain"}
    resp = requests.post(url, data=mermaid_code.encode("utf-8"), headers=headers, timeout=60)
    if resp.status_code != 200:
        raise RuntimeError(f"Kroki error {resp.status_code}: {resp.text[:300]}")
    return resp.content


def main():
    ensure_output_dir()
    md_text = read_markdown()
    blocks = extract_mermaid_blocks(md_text)
    if not blocks:
        print("No mermaid blocks found.")
        return

    summary = []

    for title, code in blocks:
        filename = None
        if title and title in FILENAME_BY_TITLE:
            filename = FILENAME_BY_TITLE[title]
        else:
            # Fallback: create a safe filename from title or index
            base = (title or "diagram").lower().replace(" ", "_").replace("/", "-")
            filename = f"{base}.png"

        out_path = OUTPUT_DIR / filename
        try:
            png_data = render_with_kroki(code)
            out_path.write_bytes(png_data)
            summary.append({"title": title or "(untitled)", "file": str(out_path.relative_to(WORKDIR))})
            print(f"Rendered: {out_path}")
        except Exception as e:
            print(f"Failed to render '{title}': {e}", file=sys.stderr)

    # Write a small manifest for convenience
    manifest_path = OUTPUT_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Manifest written: {manifest_path}")


if __name__ == "__main__":
    main()
