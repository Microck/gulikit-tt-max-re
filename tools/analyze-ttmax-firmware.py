#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import math
import re
from collections import Counter
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fingerprint and compare TT MAX / TT PRO firmware blobs."
    )
    parser.add_argument("firmware", nargs="+", type=Path, help="One or more firmware .bin files")
    parser.add_argument(
        "--compare",
        action="store_true",
        help="When two files are provided, emit basic similarity metrics as well",
    )
    return parser.parse_args()


def shannon_entropy(data: bytes) -> float:
    counts = Counter(data)
    total = len(data)
    return -sum((count / total) * math.log2(count / total) for count in counts.values())


def rolling_window_entropy(data: bytes, window: int = 1024) -> tuple[tuple[int, float], tuple[int, float]]:
    values = []
    for offset in range(0, len(data) - window + 1, window):
        values.append((offset, shannon_entropy(data[offset : offset + window])))
    return min(values, key=lambda item: item[1]), max(values, key=lambda item: item[1])


def find_printable_islands(data: bytes, limit: int = 5) -> list[tuple[int, bytes]]:
    matches = []
    for match in re.finditer(rb"[ -~]{8,}", data):
        matches.append((match.start(), match.group()))
        if len(matches) >= limit:
            break
    return matches


def find_cortex_m_vector_candidates(data: bytes, limit: int = 10) -> list[tuple[int, int, int]]:
    candidates = []
    for offset in range(0, len(data) - 8, 4):
        initial_sp = int.from_bytes(data[offset : offset + 4], "little")
        reset_pc = int.from_bytes(data[offset + 4 : offset + 8], "little")
        if 0x20000000 <= initial_sp <= 0x20080000 and reset_pc & 1:
            reset_base = reset_pc & ~1
            if 0x00000000 <= reset_base <= 0x00200000 or 0x08000000 <= reset_base <= 0x08200000:
                candidates.append((offset, initial_sp, reset_pc))
                if len(candidates) >= limit:
                    break
    return candidates


def duplicate_block_count(data: bytes, block_size: int) -> tuple[int, int]:
    blocks = [
        data[offset : offset + block_size]
        for offset in range(0, len(data) - (len(data) % block_size), block_size)
    ]
    duplicate_blocks = sum(count - 1 for count in Counter(blocks).values() if count > 1)
    return duplicate_blocks, len(blocks)


def aligned_identical_blocks(left: bytes, right: bytes, block_size: int) -> tuple[int, int]:
    length = min(len(left), len(right))
    same = 0
    total = 0
    for offset in range(0, length - (length % block_size), block_size):
        total += 1
        if left[offset : offset + block_size] == right[offset : offset + block_size]:
            same += 1
    return same, total


def shared_unique_block_count(left: bytes, right: bytes, block_size: int) -> int:
    left_blocks = {
        left[offset : offset + block_size]
        for offset in range(0, len(left) - (len(left) % block_size), block_size)
    }
    right_blocks = {
        right[offset : offset + block_size]
        for offset in range(0, len(right) - (len(right) % block_size), block_size)
    }
    return len(left_blocks & right_blocks)


def analyze(path: Path) -> None:
    data = path.read_bytes()
    min_entropy, max_entropy = rolling_window_entropy(data)

    print(f"FILE {path}")
    print(f"  size: {len(data)} bytes")
    print(f"  sha256: {hashlib.sha256(data).hexdigest()}")
    print(f"  entropy: {shannon_entropy(data):.6f}")
    print(f"  head16: {data[:16].hex()}")
    print(f"  tail16: {data[-16:].hex()}")
    print(f"  rolling_entropy_min: offset=0x{min_entropy[0]:x} value={min_entropy[1]:.6f}")
    print(f"  rolling_entropy_max: offset=0x{max_entropy[0]:x} value={max_entropy[1]:.6f}")

    islands = find_printable_islands(data)
    if islands:
        print("  printable_islands:")
        for offset, chunk in islands:
            print(f"    - offset=0x{offset:x} bytes={chunk!r}")
    else:
        print("  printable_islands: none >= 8 bytes")

    vectors = find_cortex_m_vector_candidates(data)
    if vectors:
        print("  cortex_m_vector_candidates:")
        for offset, initial_sp, reset_pc in vectors:
            print(f"    - offset=0x{offset:x} sp=0x{initial_sp:08x} pc=0x{reset_pc:08x}")
    else:
        print("  cortex_m_vector_candidates: none")

    print("  duplicate_aligned_blocks:")
    for block_size in (8, 16, 32):
        duplicates, total = duplicate_block_count(data, block_size)
        print(f"    - size={block_size} duplicates={duplicates} total={total}")


def compare(left: Path, right: Path) -> None:
    a = left.read_bytes()
    b = right.read_bytes()
    length = min(len(a), len(b))
    same_positions = sum(1 for left_byte, right_byte in zip(a[:length], b[:length]) if left_byte == right_byte)
    xor_stream = bytes(left_byte ^ right_byte for left_byte, right_byte in zip(a[:length], b[:length]))

    common_prefix = 0
    for left_byte, right_byte in zip(a, b):
        if left_byte != right_byte:
            break
        common_prefix += 1

    common_suffix = 0
    for left_byte, right_byte in zip(reversed(a), reversed(b)):
        if left_byte != right_byte:
            break
        common_suffix += 1

    print(f"COMPARE {left} <-> {right}")
    print(f"  same_position_ratio: {same_positions / length:.6f}")
    print(f"  common_prefix: {common_prefix} bytes")
    print(f"  common_suffix: {common_suffix} bytes")
    print(f"  xor_entropy: {shannon_entropy(xor_stream):.6f}")
    print(f"  xor_zeroes: {xor_stream.count(0)}")
    print("  aligned_identical_blocks:")
    for block_size in (8, 16, 32):
        same, total = aligned_identical_blocks(a, b, block_size)
        print(f"    - size={block_size} same={same} total={total}")
    print("  shared_unique_blocks:")
    for block_size in (8, 16, 32):
        shared = shared_unique_block_count(a, b, block_size)
        print(f"    - size={block_size} shared={shared}")


def main() -> int:
    args = parse_args()
    for path in args.firmware:
        analyze(path)

    if args.compare:
        if len(args.firmware) != 2:
            raise SystemExit("--compare requires exactly two firmware files")
        compare(args.firmware[0], args.firmware[1])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
