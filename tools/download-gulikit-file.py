#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import requests


DOWNLOAD_PAGE = "https://www.gulikit.com/filedownload/{file_id}"
CAPTCHA_URL = "https://www.gulikit.com/FileUpload/Captcha"
VERIFY_URL = "https://www.gulikit.com/FileUpload/CheckVerificationImgCode"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch an official GuliKit download link through the site's captcha gate "
            "and optionally download the resulting file."
        )
    )
    parser.add_argument("--file-id", required=True, help="GuliKit filedownload ID, for example 2994052")
    parser.add_argument(
        "--captcha-token",
        default="solve",
        help=(
            "Opaque value passed as the captcha 'ran' token. Reuse a unique value per attempt "
            "so the saved captcha image matches the verification request."
        ),
    )
    parser.add_argument(
        "--captcha-code",
        help="Captcha text. If omitted, the script only saves the captcha image and session state.",
    )
    parser.add_argument(
        "--captcha-image",
        type=Path,
        default=Path("/tmp/gulikit-captcha.gif"),
        help="Where to save the captcha image for manual reading",
    )
    parser.add_argument(
        "--state-file",
        type=Path,
        default=Path("/tmp/gulikit-download-state.json"),
        help="Where to save the extracted CSRF token and cookies for reuse",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="If provided together with --captcha-code, download the signed file to this path",
    )
    parser.add_argument(
        "--reuse-state",
        action="store_true",
        help=(
            "Reuse the saved cookies, CSRF token, and captcha token from --state-file instead "
            "of fetching a fresh captcha."
        ),
    )
    return parser.parse_args()


def extract_csrf_token(html: str) -> str:
    match = re.search(r'name="__RequestVerificationToken" type="hidden" value="([^"]+)"', html)
    if not match:
        raise RuntimeError("Failed to extract __RequestVerificationToken from GuliKit download page")
    return match.group(1)

def load_saved_state(path: Path) -> dict:
    state = json.loads(path.read_text())
    required = ["file_id", "csrf_token", "captcha_token", "cookies"]
    missing = [key for key in required if key not in state]
    if missing:
        raise RuntimeError(f"Saved state is missing required keys: {', '.join(missing)}")
    return state


def main() -> int:
    args = parse_args()

    session = requests.Session()
    if args.reuse_state:
        if not args.captcha_code:
            raise RuntimeError("--reuse-state requires --captcha-code")
        state = load_saved_state(args.state_file)
        for key, value in state["cookies"].items():
            session.cookies.set(key, value, domain="www.gulikit.com", path="/")
        csrf = state["csrf_token"]
        captcha_token = state["captcha_token"]
        file_id = state["file_id"]
    else:
        page = session.get(DOWNLOAD_PAGE.format(file_id=args.file_id), timeout=20)
        page.raise_for_status()

        csrf = extract_csrf_token(page.text)
        captcha = session.get(CAPTCHA_URL, params={"ran": args.captcha_token}, timeout=20)
        captcha.raise_for_status()
        args.captcha_image.write_bytes(captcha.content)

        state = {
            "file_id": args.file_id,
            "csrf_token": csrf,
            "captcha_token": args.captcha_token,
            "cookies": requests.utils.dict_from_cookiejar(session.cookies),
            "captcha_image": str(args.captcha_image),
        }
        args.state_file.write_text(json.dumps(state, indent=2))
        captcha_token = args.captcha_token
        file_id = args.file_id

    if not args.captcha_code:
        print(json.dumps(state, indent=2))
        print(
            "\nCaptcha image saved. Read it, then rerun with "
            f"--captcha-code <code> and optionally --output {args.output or 'path/to/file.zip'}. "
            "Use --reuse-state to submit against the exact saved captcha."
        )
        return 0

    verify = session.post(
        VERIFY_URL,
        data={
            "__RequestVerificationToken": csrf,
            "code": args.captcha_code,
            "newRandomToken": captcha_token,
            "fileId": file_id,
            "password": "",
        },
        timeout=20,
    )
    verify.raise_for_status()
    result = verify.json()
    if not result.get("result"):
        raise RuntimeError(result.get("message", "GuliKit verification failed"))

    signed_url = result["message"]
    print(signed_url)

    if args.output:
        download = session.get(signed_url, timeout=60)
        download.raise_for_status()
        args.output.write_bytes(download.content)
        print(f"Saved {args.output} ({len(download.content)} bytes)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
