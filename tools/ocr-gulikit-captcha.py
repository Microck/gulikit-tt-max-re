from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

from PIL import Image


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Preprocess a GuliKit captcha image into larger, easier-to-read artifacts and "
            "attempt a best-effort per-digit OCR pass."
        )
    )
    parser.add_argument("image", type=Path, help="Path to the source captcha image")
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Directory for the generated debug artifacts (defaults next to the image)",
    )
    parser.add_argument(
        "--scale",
        type=int,
        default=10,
        help="Nearest-neighbor upscale factor before segmentation",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=620,
        help="Dark-pixel threshold using r+g+b; lower is stricter",
    )
    parser.add_argument(
        "--crop-top-ratio",
        type=float,
        default=0.18,
        help="Ignore this fraction of the top image to drop the black header noise",
    )
    return parser.parse_args()


def is_dark(pixel: tuple[int, int, int], threshold: int) -> bool:
    return sum(pixel) < threshold


def content_band(image: Image.Image, threshold: int) -> tuple[int, int]:
    width, height = image.size
    row_hits = []
    for y in range(height):
        dark_count = 0
        for x in range(width):
            if is_dark(image.getpixel((x, y)), threshold):
                dark_count += 1
        row_hits.append(dark_count)

    rows = [index for index, count in enumerate(row_hits) if count > max(4, width // 80)]
    if not rows:
        return 0, height - 1
    return rows[0], rows[-1]


def content_spans(image: Image.Image, threshold: int, merge_gap: int) -> list[tuple[int, int]]:
    width, height = image.size
    spans: list[tuple[int, int]] = []
    in_run = False
    start = 0

    for x in range(width):
        dark_count = 0
        for y in range(height):
            if is_dark(image.getpixel((x, y)), threshold):
                dark_count += 1

        if dark_count > 0 and not in_run:
            start = x
            in_run = True
        elif dark_count == 0 and in_run:
            spans.append((start, x - 1))
            in_run = False

    if in_run:
        spans.append((start, width - 1))

    if not spans:
        return [(0, width - 1)]

    merged = [spans[0]]
    for start, end in spans[1:]:
        previous_start, previous_end = merged[-1]
        if start - previous_end <= merge_gap:
            merged[-1] = (previous_start, end)
        else:
            merged.append((start, end))
    return merged


def fallback_quartiles(image: Image.Image) -> list[tuple[int, int]]:
    width, _ = image.size
    left = max(0, width // 20)
    right = min(width, width - left)
    usable = right - left
    step = max(1, usable // 4)

    spans = []
    for index in range(4):
        start = left + index * step
        end = right - 1 if index == 3 else min(right - 1, left + (index + 1) * step - 1)
        spans.append((start, end))
    return spans


def normalize_digit_count(spans: list[tuple[int, int]], image: Image.Image) -> list[tuple[int, int]]:
    if len(spans) == 4:
        return spans
    return fallback_quartiles(image)


def save_contact_sheet(digits: list[Image.Image], path: Path) -> None:
    width = sum(image.width for image in digits)
    height = max(image.height for image in digits)
    sheet = Image.new("RGB", (width, height), "white")

    cursor = 0
    for image in digits:
        sheet.paste(image, (cursor, 0))
        cursor += image.width

    sheet.save(path)


def ocr_digit(image_path: Path) -> str:
    if not shutil.which("tesseract"):
        return "?"

    result = subprocess.run(
        [
            "tesseract",
            str(image_path),
            "stdout",
            "--psm",
            "10",
            "-c",
            "tessedit_char_whitelist=0123456789",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    guess = result.stdout.strip()
    return guess or "?"


def main() -> int:
    args = parse_args()

    output_dir = args.output_dir or args.image.with_suffix("")
    output_dir.mkdir(parents=True, exist_ok=True)

    image = Image.open(args.image).convert("RGB")
    image = image.resize((image.width * args.scale, image.height * args.scale), Image.Resampling.NEAREST)

    crop_top = int(image.height * args.crop_top_ratio)
    image = image.crop((0, crop_top, image.width, image.height))

    top, bottom = content_band(image, args.threshold)
    image = image.crop((0, top, image.width, bottom + 1))

    processed_path = output_dir / "processed.png"
    image.save(processed_path)

    spans = content_spans(image, args.threshold, merge_gap=max(2, args.scale // 2))
    spans = normalize_digit_count(spans, image)

    digits: list[Image.Image] = []
    digit_paths: list[Path] = []
    for index, (start, end) in enumerate(spans, start=1):
        digit = image.crop((max(0, start - 4), 0, min(image.width, end + 5), image.height))
        digit = digit.resize((digit.width * 2, digit.height * 2), Image.Resampling.NEAREST)
        digit_path = output_dir / f"digit-{index}.png"
        digit.save(digit_path)
        digits.append(digit)
        digit_paths.append(digit_path)

    sheet_path = output_dir / "digits.png"
    save_contact_sheet(digits, sheet_path)

    guesses = [ocr_digit(path) for path in digit_paths]

    print(f"processed_image={processed_path}")
    print(f"digits_sheet={sheet_path}")
    for index, path in enumerate(digit_paths, start=1):
        print(f"digit_{index}={path}")
    print(f"ocr_guess={''.join(guesses)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
