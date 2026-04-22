from __future__ import annotations

import argparse
import json
import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests


VERIFY_URL = "https://www.gulikit.com/FileUpload/CheckVerificationImgCode"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Probe a narrow GuliKit filedownload ID range from a saved captcha session. "
            "Observed behavior suggests a successful verification consumes the captcha, "
            "so this is best-effort and usually yields at most one hit per run."
        )
    )
    parser.add_argument("state_file", type=Path, help="JSON state emitted by download-gulikit-file.py")
    parser.add_argument("--captcha-code", required=True, help="Solved captcha text for the saved state")
    parser.add_argument("--start", type=int, required=True, help="First file ID to probe")
    parser.add_argument("--end", type=int, required=True, help="Last file ID to probe, inclusive")
    parser.add_argument(
        "--workers",
        type=int,
        default=24,
        help="Concurrent verification workers. Higher values widen the single-use race window.",
    )
    return parser.parse_args()


def load_state(path: Path) -> dict:
    state = json.loads(path.read_text())
    required = ["csrf_token", "captcha_token", "cookies"]
    missing = [key for key in required if key not in state]
    if missing:
        raise RuntimeError(f"Saved state is missing required keys: {', '.join(missing)}")
    return state


def verify_candidate(state: dict, captcha_code: str, file_id: int) -> dict:
    session = requests.Session()
    for key, value in state["cookies"].items():
        session.cookies.set(key, value, domain="www.gulikit.com", path="/")

    response = session.post(
        VERIFY_URL,
        data={
            "__RequestVerificationToken": state["csrf_token"],
            "code": captcha_code,
            "newRandomToken": state["captcha_token"],
            "fileId": str(file_id),
            "password": "",
        },
        timeout=20,
    )
    response.raise_for_status()
    return {"file_id": file_id, "result": response.json()}


def extract_filename(url: str) -> str:
    match = re.search(r"filename%3D([^&]+)", url)
    if not match:
        return "<unknown>"
    return urllib.parse.unquote(match.group(1))


def main() -> int:
    args = parse_args()
    state = load_state(args.state_file)
    ids = list(range(args.start, args.end + 1))

    successes = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        for item in executor.map(lambda file_id: verify_candidate(state, args.captcha_code, file_id), ids):
            result = item["result"]
            if result.get("result"):
                url = result["message"]
                filename = extract_filename(url)
                successes.append((item["file_id"], filename, url))
                print(f"success file_id={item['file_id']} filename={filename}")

    print(f"total_successes={len(successes)}")
    for file_id, filename, url in successes:
        print(f"file_id={file_id}")
        print(f"filename={filename}")
        print(f"signed_url={url}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
