from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def parse_int(value: object, *, field_name: str) -> int:
    if isinstance(value, str):
        return int(value, 0)
    if isinstance(value, int):
        return value
    raise RuntimeError(f"{field_name} must be an integer or integer-like string")


def parse_hex_bytes(value: str, *, field_name: str) -> bytes:
    cleaned = value.replace(" ", "").replace(":", "").replace("-", "")
    if len(cleaned) % 2:
        raise RuntimeError(f"{field_name} must contain an even number of hex nybbles")
    try:
        return bytes.fromhex(cleaned)
    except ValueError as exc:
        raise RuntimeError(f"{field_name} is not valid hex: {exc}") from exc


def parse_search_pattern(value: str) -> tuple[bytes, bytes]:
    normalized = value.replace(":", " ").replace("-", " ")
    parts = normalized.split()
    if not parts:
        cleaned = value.replace(" ", "").replace(":", "").replace("-", "")
        if len(cleaned) % 2:
            raise RuntimeError("find_hex must contain an even number of nybbles")
        parts = [cleaned[index : index + 2] for index in range(0, len(cleaned), 2)]

    pattern = bytearray()
    mask = bytearray()
    for part in parts:
        if part in {"??", "**"}:
            pattern.append(0)
            mask.append(0)
            continue
        if len(part) != 2:
            raise RuntimeError(
                "find_hex must use two-nybble bytes or wildcard bytes like '??'"
            )
        try:
            pattern.append(int(part, 16))
        except ValueError as exc:
            raise RuntimeError(f"find_hex contains invalid byte '{part}'") from exc
        mask.append(0xFF)

    return bytes(pattern), bytes(mask)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Apply a verified byte-level patch manifest to an official firmware blob. "
            "This is the re-application mechanism once concrete patch offsets or "
            "stable signature anchors are known."
        )
    )
    parser.add_argument("firmware", type=Path, help="Path to the official input firmware .bin")
    parser.add_argument("manifest", type=Path, help="Patch manifest JSON")
    parser.add_argument("output", type=Path, help="Path to write the patched firmware .bin")
    return parser.parse_args()


def load_manifest(path: Path) -> dict:
    manifest = json.loads(path.read_text())
    if "patches" not in manifest or not isinstance(manifest["patches"], list):
        raise RuntimeError("Patch manifest must contain a 'patches' array")
    return manifest


def verify_hash(data: bytes, manifest: dict) -> None:
    expected = manifest.get("input_sha256")
    if not expected:
        return
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        raise RuntimeError(
            "Input firmware hash mismatch.\n"
            f"Expected: {expected}\n"
            f"Actual:   {actual}"
        )


def find_pattern_offsets(data: bytes, pattern: bytes, mask: bytes) -> list[int]:
    if len(pattern) != len(mask):
        raise RuntimeError("internal error: pattern and mask lengths differ")
    if not pattern:
        raise RuntimeError("find_hex cannot be empty")
    if len(pattern) > len(data):
        return []

    offsets: list[int] = []
    window_len = len(pattern)
    for start in range(len(data) - window_len + 1):
        for index, expected in enumerate(pattern):
            if mask[index] and data[start + index] != expected:
                break
        else:
            offsets.append(start)
    return offsets


def resolve_patch_offset(data: bytes, patch: dict) -> int:
    if "offset" in patch:
        return parse_int(patch["offset"], field_name="offset")

    if "find_hex" not in patch:
        raise RuntimeError("Each patch must define either 'offset' or 'find_hex'")

    pattern, mask = parse_search_pattern(str(patch["find_hex"]))
    matches = find_pattern_offsets(data, pattern, mask)
    expected_matches = parse_int(
        patch.get("expected_matches", 1), field_name="expected_matches"
    )
    if len(matches) != expected_matches:
        raise RuntimeError(
            "Signature match count mismatch.\n"
            f"Description: {patch.get('description', '<none>')}\n"
            f"Pattern: {patch['find_hex']}\n"
            f"Expected matches: {expected_matches}\n"
            f"Actual matches:   {len(matches)}\n"
            f"Match offsets:    {[hex(offset) for offset in matches]}"
        )

    match_index = parse_int(patch.get("match_index", 0), field_name="match_index")
    if match_index < 0 or match_index >= len(matches):
        raise RuntimeError(
            f"match_index {match_index} is out of range for {len(matches)} matches"
        )

    offset_adjust = parse_int(patch.get("offset_adjust", 0), field_name="offset_adjust")
    return matches[match_index] + offset_adjust


def load_expected_bytes(patch: dict) -> bytes:
    if "expect_hex" in patch:
        return parse_hex_bytes(str(patch["expect_hex"]), field_name="expect_hex")

    if "find_hex" not in patch:
        raise RuntimeError("Patch must define 'expect_hex' when using a raw offset")

    if parse_int(patch.get("offset_adjust", 0), field_name="offset_adjust") != 0:
        raise RuntimeError(
            "Patch must define 'expect_hex' when offset_adjust is non-zero"
        )

    pattern, mask = parse_search_pattern(str(patch["find_hex"]))
    if any(mask_byte != 0xFF for mask_byte in mask):
        raise RuntimeError(
            "Patch must define 'expect_hex' when find_hex contains wildcard bytes"
        )
    return pattern


def apply_patches(data: bytearray, manifest: dict) -> bytearray:
    for patch in manifest["patches"]:
        # Offset patches are still supported, but signature-anchored patches are safer
        # when the same logical region moves across firmware revisions.
        offset = resolve_patch_offset(data, patch)
        expected = load_expected_bytes(patch)
        replacement = parse_hex_bytes(str(patch["replace_hex"]), field_name="replace_hex")

        if offset < 0:
            raise RuntimeError(f"Patch offset cannot be negative: {offset}")

        original = bytes(data[offset : offset + len(expected)])
        if original != expected:
            raise RuntimeError(
                "Patch precondition failed.\n"
                f"Description: {patch.get('description', '<none>')}\n"
                f"Offset: 0x{offset:x}\n"
                f"Expected: {expected.hex()}\n"
                f"Actual:   {original.hex()}"
            )

        if len(expected) != len(replacement):
            raise RuntimeError("This patcher only supports in-place same-length replacements")

        data[offset : offset + len(replacement)] = replacement

    return data


def main() -> int:
    args = parse_args()
    data = bytearray(args.firmware.read_bytes())
    manifest = load_manifest(args.manifest)

    verify_hash(data, manifest)
    patched = apply_patches(data, manifest)
    args.output.write_bytes(patched)

    print(f"input_sha256={hashlib.sha256(args.firmware.read_bytes()).hexdigest()}")
    print(f"output_sha256={hashlib.sha256(patched).hexdigest()}")
    print(f"patched_file={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
