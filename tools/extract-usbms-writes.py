from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class WriteRequest:
    request_frame: int
    lba: int
    sectors: int
    transfer_bytes: int


@dataclass(slots=True)
class WriteRecord:
    request_frame: int
    data_frame: int
    status_frame: int | None
    lba: int
    sectors: int
    transfer_bytes: int
    payload: bytes

    @property
    def payload_sha256(self) -> str:
        return hashlib.sha256(self.payload).hexdigest()


@dataclass(slots=True)
class CommandRecord:
    request_frame: int
    tag: int | None
    opcode: int | None
    command_name: str
    cdb_length: int | None
    transfer_bytes: int
    lba: int | None = None
    sectors: int | None = None
    prevent: int | None = None
    data_frames: list[dict] | None = None
    status_frame: int | None = None
    status: int | None = None
    sense_key: int | None = None
    sense_asc: int | None = None
    sense_ascq: int | None = None


SCSI_COMMAND_NAMES: dict[int, str] = {
    0x00: "Test Unit Ready",
    0x03: "Request Sense",
    0x1E: "Prevent/Allow Medium Removal",
    0x2A: "Write(10)",
}

SCSI_STATUS_NAMES: dict[int, str] = {
    0x00: "Good",
    0x02: "Check Condition",
}

SENSE_KEY_NAMES: dict[int, str] = {
    0x05: "Illegal Request",
}

SENSE_ASC_ASCQ_NAMES: dict[tuple[int, int], str] = {
    (0x20, 0x00): "Invalid Command Operation Code",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Extract USB mass-storage WRITE(10) payloads from a USBPcap capture and "
            "optionally reconstruct the final FAT volume image."
        )
    )
    parser.add_argument("pcap", type=Path, help="Path to the .pcapng capture")
    parser.add_argument(
        "--dump-dir",
        type=Path,
        help="Write each recovered payload as a standalone .bin into this directory",
    )
    parser.add_argument(
        "--reconstruct-image",
        type=Path,
        help="Write a sparse final-image reconstruction to this path",
    )
    parser.add_argument(
        "--match-file",
        type=Path,
        help="Optional file to compare against any recovered payload or FAT file entry",
    )
    parser.add_argument("--json", action="store_true", help="Emit structured JSON")
    return parser.parse_args()


def run_tshark_fields(pcap: Path, display_filter: str, fields: list[str]) -> list[list[str]]:
    cmd = [
        "tshark",
        "-r",
        str(pcap),
        "-Y",
        display_filter,
        "-T",
        "fields",
    ]
    for field in fields:
        cmd.extend(["-e", field])

    output = subprocess.check_output(cmd, text=True)
    rows: list[list[str]] = []
    reader = csv.reader(output.splitlines(), delimiter="\t")
    for row in reader:
        if not row:
            continue
        rows.append(row)
    return rows


def run_tshark_jsonraw(pcap: Path, display_filter: str) -> list[dict]:
    cmd = [
        "tshark",
        "-r",
        str(pcap),
        "-Y",
        display_filter,
        "-T",
        "jsonraw",
    ]
    output = subprocess.check_output(cmd, text=True, encoding="utf-8", errors="replace")
    return json.loads(output)


def parse_field_int(value: str) -> int | None:
    if not value:
        return None
    if value.lower().startswith("0x"):
        return int(value, 16)
    return int(value)


def command_name(opcode: int | None) -> str:
    if opcode is None:
        return "Unknown"
    return SCSI_COMMAND_NAMES.get(opcode, f"Opcode 0x{opcode:02x}")


def scsi_status_name(status: int | None) -> str | None:
    if status is None:
        return None
    return SCSI_STATUS_NAMES.get(status, f"0x{status:02x}")


def sense_key_name(key: int | None) -> str | None:
    if key is None:
        return None
    return SENSE_KEY_NAMES.get(key, f"0x{key:02x}")


def sense_asc_ascq_name(asc: int | None, ascq: int | None) -> str | None:
    if asc is None or ascq is None:
        return None
    return SENSE_ASC_ASCQ_NAMES.get((asc, ascq), f"0x{asc:02x}/0x{ascq:02x}")


def collect_command_records(pcap: Path) -> list[CommandRecord]:
    request_rows = run_tshark_fields(
        pcap,
        "usbms.dCBWTag && usb.endpoint_address == 0x03",
        [
            "frame.number",
            "usbms.dCBWTag",
            "usbms.dCBWDataTransferLength",
            "usbms.dCBWCBLength",
            "scsi.spc.opcode",
            "scsi_sbc.opcode",
            "scsi.prevent_allow.prevent",
            "scsi_sbc.rdwr10.lba",
            "scsi_sbc.rdwr10.xferlen",
        ],
    )

    records: dict[int, CommandRecord] = {}
    for row in request_rows:
        padded = row + [""] * (9 - len(row))
        (
            frame_text,
            tag_text,
            transfer_text,
            cdb_length_text,
            spc_opcode_text,
            sbc_opcode_text,
            prevent_text,
            lba_text,
            sectors_text,
        ) = padded[:9]

        opcode = parse_field_int(spc_opcode_text) if spc_opcode_text else parse_field_int(sbc_opcode_text)
        request_frame = int(frame_text)
        records[request_frame] = CommandRecord(
            request_frame=request_frame,
            tag=parse_field_int(tag_text),
            opcode=opcode,
            command_name=command_name(opcode),
            cdb_length=parse_field_int(cdb_length_text),
            transfer_bytes=parse_field_int(transfer_text) or 0,
            lba=parse_field_int(lba_text),
            sectors=parse_field_int(sectors_text),
            prevent=parse_field_int(prevent_text),
            data_frames=[],
        )

    response_rows = run_tshark_fields(
        pcap,
        "scsi.request_frame",
        [
            "frame.number",
            "scsi.request_frame",
            "usb.endpoint_address",
            "usb.data_len",
            "scsi.status",
            "scsi.sns.key",
            "scsi.sns.asc",
            "scsi.sns.ascq",
        ],
    )

    for row in response_rows:
        padded = row + [""] * (8 - len(row))
        (
            frame_text,
            request_text,
            endpoint_text,
            data_len_text,
            status_text,
            sense_key_text,
            asc_text,
            ascq_text,
        ) = padded[:8]
        request_frame = int(request_text)
        record = records.get(request_frame)
        if record is None:
            continue

        frame_number = int(frame_text)
        endpoint = endpoint_text.lower()
        data_len = int(data_len_text) if data_len_text else 0
        status = parse_field_int(status_text)

        if endpoint == "0x82" and data_len == 13 and status is not None:
            record.status_frame = frame_number
            record.status = status
            continue

        data_frame: dict[str, int] = {
            "frame": frame_number,
            "endpoint": int(endpoint, 16),
            "data_len": data_len,
        }
        record.data_frames.append(data_frame)

        sense_key = parse_field_int(sense_key_text)
        asc = parse_field_int(asc_text)
        ascq = parse_field_int(ascq_text)
        if sense_key is not None or asc is not None or ascq is not None:
            record.sense_key = sense_key
            record.sense_asc = asc
            record.sense_ascq = ascq

    return [records[request_frame] for request_frame in sorted(records)]


def collect_write_requests(pcap: Path) -> dict[int, WriteRequest]:
    rows = run_tshark_fields(
        pcap,
        "scsi_sbc.opcode == 0x2a && scsi_sbc.rdwr10.lba",
        [
            "frame.number",
            "scsi_sbc.rdwr10.lba",
            "scsi_sbc.rdwr10.xferlen",
            "usbms.dCBWDataTransferLength",
        ],
    )

    requests: dict[int, WriteRequest] = {}
    for frame_text, lba_text, sectors_text, transfer_bytes_text in rows:
        request = WriteRequest(
            request_frame=int(frame_text),
            lba=int(lba_text),
            sectors=int(sectors_text),
            transfer_bytes=int(transfer_bytes_text),
        )
        requests[request.request_frame] = request
    return requests


def collect_response_frames(pcap: Path) -> tuple[dict[int, int], dict[int, int]]:
    rows = run_tshark_fields(
        pcap,
        "scsi.request_frame",
        [
            "frame.number",
            "scsi.request_frame",
            "usb.endpoint_address",
            "usb.data_len",
        ],
    )

    data_frames: dict[int, int] = {}
    status_frames: dict[int, int] = {}
    for frame_text, request_text, endpoint_text, data_len_text in rows:
        frame_number = int(frame_text)
        request_frame = int(request_text)
        endpoint = endpoint_text.lower()
        data_len = int(data_len_text) if data_len_text else 0

        if endpoint == "0x03" and data_len > 0:
            data_frames[request_frame] = frame_number
        elif endpoint == "0x82":
            status_frames[request_frame] = frame_number

    return data_frames, status_frames


def collect_payloads(pcap: Path, frames: list[int]) -> dict[int, bytes]:
    if not frames:
        return {}

    sorted_frames = sorted(frames)
    display_filter = " || ".join(f"frame.number == {frame}" for frame in sorted_frames)
    frame_rows = run_tshark_fields(pcap, display_filter, ["frame.number"])
    packets = run_tshark_jsonraw(pcap, display_filter)
    if len(frame_rows) != len(packets):
        raise RuntimeError(
            "tshark frame-number list did not line up with jsonraw packets.\n"
            f"frame_rows={len(frame_rows)} json_packets={len(packets)}"
        )

    payloads: dict[int, bytes] = {}
    for row, packet in zip(frame_rows, packets, strict=True):
        frame_number = int(row[0])
        layers = packet["_source"]["layers"]
        frame_hex = layers["frame_raw"][0]
        header_len_hex = layers["usb"]["usb.usbpcap_header_len_raw"][0]
        header_len = int.from_bytes(bytes.fromhex(header_len_hex), "little")
        payloads[frame_number] = bytes.fromhex(frame_hex[header_len * 2 :])

    return payloads


def build_records(pcap: Path) -> list[WriteRecord]:
    requests = collect_write_requests(pcap)
    data_frames, status_frames = collect_response_frames(pcap)
    payloads = collect_payloads(pcap, list(data_frames.values()))

    records: list[WriteRecord] = []
    for request_frame in sorted(requests):
        request = requests[request_frame]
        data_frame = data_frames.get(request_frame)
        if data_frame is None:
            raise RuntimeError(f"missing data frame for WRITE(10) request frame {request_frame}")
        payload = payloads[data_frame]
        if len(payload) != request.transfer_bytes:
            raise RuntimeError(
                "payload length mismatch.\n"
                f"request_frame={request_frame}\n"
                f"expected={request.transfer_bytes}\n"
                f"actual={len(payload)}"
            )

        records.append(
            WriteRecord(
                request_frame=request_frame,
                data_frame=data_frame,
                status_frame=status_frames.get(request_frame),
                lba=request.lba,
                sectors=request.sectors,
                transfer_bytes=request.transfer_bytes,
                payload=payload,
            )
        )
    return records


def parse_boot_sector(sector0: bytes) -> dict[str, int | str] | None:
    if len(sector0) < 512 or sector0[510:512] != b"\x55\xaa":
        return None

    total_sectors_16 = int.from_bytes(sector0[19:21], "little")
    total_sectors_32 = int.from_bytes(sector0[32:36], "little")
    total_sectors = total_sectors_16 or total_sectors_32
    bytes_per_sector = int.from_bytes(sector0[11:13], "little")
    sectors_per_cluster = sector0[13]
    reserved_sectors = int.from_bytes(sector0[14:16], "little")
    fat_count = sector0[16]
    root_entries = int.from_bytes(sector0[17:19], "little")
    sectors_per_fat = int.from_bytes(sector0[22:24], "little")
    root_dir_sectors = math.ceil(root_entries * 32 / bytes_per_sector)
    fat_start_lba = reserved_sectors
    root_dir_start_lba = fat_start_lba + fat_count * sectors_per_fat
    data_start_lba = root_dir_start_lba + root_dir_sectors

    return {
        "oem_name": sector0[3:11].decode("ascii", errors="replace").rstrip(),
        "bytes_per_sector": bytes_per_sector,
        "sectors_per_cluster": sectors_per_cluster,
        "reserved_sectors": reserved_sectors,
        "fat_count": fat_count,
        "root_entries": root_entries,
        "sectors_per_fat": sectors_per_fat,
        "root_dir_sectors": root_dir_sectors,
        "fat_start_lba": fat_start_lba,
        "root_dir_start_lba": root_dir_start_lba,
        "data_start_lba": data_start_lba,
        "total_sectors": total_sectors,
        "volume_label": sector0[43:54].decode("ascii", errors="replace").rstrip(),
        "filesystem_type": sector0[54:62].decode("ascii", errors="replace").rstrip(),
    }


def make_sector_map(records: list[WriteRecord], sector_size: int) -> dict[int, bytes]:
    sectors: dict[int, bytes] = {}
    for record in records:
        for index in range(record.sectors):
            start = index * sector_size
            end = start + sector_size
            sectors[record.lba + index] = record.payload[start:end]
    return sectors


def read_lba_range(sectors: dict[int, bytes], start_lba: int, count: int, sector_size: int) -> bytes:
    return b"".join(sectors.get(start_lba + index, b"\x00" * sector_size) for index in range(count))


def decode_lfn_text(entry: bytes) -> str:
    fields = [
        entry[1:11],
        entry[14:26],
        entry[28:32],
    ]
    raw = b"".join(fields)
    chars: list[str] = []
    for offset in range(0, len(raw), 2):
        code_unit = int.from_bytes(raw[offset : offset + 2], "little")
        if code_unit in (0x0000, 0xFFFF):
            break
        chars.append(chr(code_unit))
    return "".join(chars)


def parse_root_directory(
    sectors: dict[int, bytes],
    boot_sector: dict[str, int | str],
) -> list[dict[str, int | str | list[int]]]:
    sector_size = int(boot_sector["bytes_per_sector"])
    root_dir_bytes = read_lba_range(
        sectors,
        int(boot_sector["root_dir_start_lba"]),
        int(boot_sector["root_dir_sectors"]),
        sector_size,
    )

    entries: list[dict[str, int | str | list[int]]] = []
    pending_lfn: list[str] = []
    for offset in range(0, len(root_dir_bytes), 32):
        entry = root_dir_bytes[offset : offset + 32]
        first_byte = entry[0]
        if first_byte == 0x00:
            break
        if first_byte == 0xE5:
            pending_lfn.clear()
            continue

        attributes = entry[11]
        if attributes == 0x0F:
            pending_lfn.append(decode_lfn_text(entry))
            continue

        short_base = entry[0:8].decode("ascii", errors="replace").rstrip()
        short_ext = entry[8:11].decode("ascii", errors="replace").rstrip()
        short_name = short_base if not short_ext else f"{short_base}.{short_ext}"
        name = "".join(reversed(pending_lfn)) or short_name
        pending_lfn.clear()

        entries.append(
            {
                "name": name,
                "short_name": short_name,
                "attributes": attributes,
                "start_cluster": int.from_bytes(entry[26:28], "little"),
                "size": int.from_bytes(entry[28:32], "little"),
            }
        )
    return entries


def extract_fat_chain(
    sectors: dict[int, bytes],
    boot_sector: dict[str, int | str],
    start_cluster: int,
) -> list[int]:
    if start_cluster < 2:
        return []

    sector_size = int(boot_sector["bytes_per_sector"])
    fat_bytes = read_lba_range(
        sectors,
        int(boot_sector["fat_start_lba"]),
        int(boot_sector["sectors_per_fat"]),
        sector_size,
    )

    chain: list[int] = []
    current = start_cluster
    seen: set[int] = set()
    while current >= 2 and current not in seen:
        seen.add(current)
        chain.append(current)
        next_cluster = int.from_bytes(fat_bytes[current * 2 : current * 2 + 2], "little")
        if next_cluster >= 0xFFF8:
            break
        if next_cluster in (0x0000, 0xFFF7):
            break
        current = next_cluster
    return chain


def read_file_from_chain(
    sectors: dict[int, bytes],
    boot_sector: dict[str, int | str],
    clusters: list[int],
    size: int,
) -> bytes:
    if not clusters or size <= 0:
        return b""

    sector_size = int(boot_sector["bytes_per_sector"])
    sectors_per_cluster = int(boot_sector["sectors_per_cluster"])
    data_start_lba = int(boot_sector["data_start_lba"])

    chunks: list[bytes] = []
    for cluster in clusters:
        lba = data_start_lba + (cluster - 2) * sectors_per_cluster
        chunks.append(read_lba_range(sectors, lba, sectors_per_cluster, sector_size))
    return b"".join(chunks)[:size]


def compare_match_file(records: list[WriteRecord], fat_files: list[dict], match_file: Path) -> dict[str, object]:
    needle = match_file.read_bytes()
    needle_sha256 = hashlib.sha256(needle).hexdigest()
    result: dict[str, object] = {
        "path": str(match_file),
        "sha256": needle_sha256,
        "matching_write_requests": [],
        "matching_fat_entries": [],
    }

    for record in records:
        if record.payload[: len(needle)] == needle:
            result["matching_write_requests"].append(
                {
                    "request_frame": record.request_frame,
                    "data_frame": record.data_frame,
                    "lba": record.lba,
                    "sectors": record.sectors,
                    "trailing_zero_padding": len(record.payload) - len(needle),
                }
            )

    for fat_file in fat_files:
        if fat_file.get("sha256") == needle_sha256:
            result["matching_fat_entries"].append(
                {
                    "name": fat_file["name"],
                    "short_name": fat_file["short_name"],
                    "size": fat_file["size"],
                    "start_cluster": fat_file["start_cluster"],
                    "cluster_chain": fat_file["cluster_chain"],
                }
            )
    return result


def reconstruct_image(path: Path, sectors: dict[int, bytes], image_size: int, sector_size: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        if image_size > 0:
            handle.seek(image_size - 1)
            handle.write(b"\x00")
        for lba in sorted(sectors):
            handle.seek(lba * sector_size)
            handle.write(sectors[lba])


def summarize(records: list[WriteRecord], match_file: Path | None, pcap: Path) -> dict[str, object]:
    return summarize_capture(pcap, records, match_file)


def summarize_capture(pcap: Path, records: list[WriteRecord], match_file: Path | None) -> dict[str, object]:
    commands = collect_command_records(pcap)
    sector_size = 512
    sector0 = next((record.payload for record in records if record.lba == 0 and record.sectors == 1), None)
    boot_sector = parse_boot_sector(sector0) if sector0 else None
    if boot_sector:
        sector_size = int(boot_sector["bytes_per_sector"])

    sectors = make_sector_map(records, sector_size)
    if not boot_sector and 0 in sectors:
        boot_sector = parse_boot_sector(sectors[0])
    fat_files: list[dict[str, object]] = []
    if boot_sector:
        for entry in parse_root_directory(sectors, boot_sector):
            chain = extract_fat_chain(sectors, boot_sector, int(entry["start_cluster"]))
            file_bytes = read_file_from_chain(sectors, boot_sector, chain, int(entry["size"]))
            entry["cluster_chain"] = chain
            entry["sha256"] = hashlib.sha256(file_bytes).hexdigest() if file_bytes else None
            fat_files.append(entry)

    writes = [
        {
            "request_frame": record.request_frame,
            "data_frame": record.data_frame,
            "status_frame": record.status_frame,
            "lba": record.lba,
            "sectors": record.sectors,
            "transfer_bytes": record.transfer_bytes,
            "payload_sha256": record.payload_sha256,
        }
        for record in records
    ]

    command_sequence = [
        {
            "request_frame": command.request_frame,
            "tag": command.tag,
            "opcode": command.opcode,
            "command_name": command.command_name,
            "cdb_length": command.cdb_length,
            "transfer_bytes": command.transfer_bytes,
            "lba": command.lba,
            "sectors": command.sectors,
            "prevent": command.prevent,
            "data_frames": command.data_frames,
            "status_frame": command.status_frame,
            "status": command.status,
            "status_name": scsi_status_name(command.status),
            "sense_key": command.sense_key,
            "sense_key_name": sense_key_name(command.sense_key),
            "sense_asc": command.sense_asc,
            "sense_ascq": command.sense_ascq,
            "sense_asc_ascq_name": sense_asc_ascq_name(command.sense_asc, command.sense_ascq),
        }
        for command in commands
    ]

    command_counts: dict[str, int] = {}
    for command in commands:
        command_counts[command.command_name] = command_counts.get(command.command_name, 0) + 1

    summary: dict[str, object] = {
        "command_count": len(commands),
        "command_counts": command_counts,
        "command_sequence": command_sequence,
        "write_count": len(records),
        "writes": writes,
        "boot_sector": boot_sector,
        "root_directory": fat_files,
        "image_size_bytes": (
            int(boot_sector["total_sectors"]) * sector_size
            if boot_sector and int(boot_sector["total_sectors"]) > 0
            else max((record.lba + record.sectors) * sector_size for record in records)
        ),
        "sector_size": sector_size,
    }

    if match_file is not None:
        summary["match_file"] = compare_match_file(records, fat_files, match_file)

    return summary


def print_summary(summary: dict[str, object]) -> None:
    print(f"command_count={summary['command_count']}")
    print(f"write_count={summary['write_count']}")
    print(f"sector_size={summary['sector_size']}")
    print(f"image_size_bytes={summary['image_size_bytes']}")

    command_counts = summary.get("command_counts") or {}
    if command_counts:
        print("command_counts:")
        for command_name_text in sorted(command_counts):
            print(f"  {command_name_text}={command_counts[command_name_text]}")

    command_sequence = summary.get("command_sequence") or []
    if command_sequence:
        print("command_sequence:")
        for command in command_sequence:
            line = (
                "  "
                f"request={command['request_frame']} "
                f"name={command['command_name']!r} "
                f"opcode={command['opcode']} "
                f"transfer_bytes={command['transfer_bytes']} "
                f"status_frame={command['status_frame']} "
                f"status={command['status_name']!r}"
            )
            if command.get("lba") is not None:
                line += f" lba={command['lba']}"
            if command.get("sectors") is not None:
                line += f" sectors={command['sectors']}"
            if command.get("prevent") is not None:
                line += f" prevent={command['prevent']}"
            if command.get("sense_key_name") is not None:
                line += (
                    f" sense_key={command['sense_key_name']!r}"
                    f" sense={command['sense_asc_ascq_name']!r}"
                )
            if command.get("data_frames"):
                line += f" data_frames={command['data_frames']}"
            print(line)

    boot_sector = summary.get("boot_sector")
    if boot_sector:
        print("boot_sector:")
        for key in [
            "oem_name",
            "bytes_per_sector",
            "sectors_per_cluster",
            "reserved_sectors",
            "fat_count",
            "sectors_per_fat",
            "root_dir_start_lba",
            "data_start_lba",
            "total_sectors",
            "volume_label",
            "filesystem_type",
        ]:
            print(f"  {key}={boot_sector[key]}")

    print("writes:")
    for write in summary["writes"]:
        print(
            "  "
            f"request={write['request_frame']} "
            f"data={write['data_frame']} "
            f"status={write['status_frame']} "
            f"lba={write['lba']} "
            f"sectors={write['sectors']} "
            f"bytes={write['transfer_bytes']} "
            f"sha256={write['payload_sha256']}"
        )

    root_directory = summary.get("root_directory") or []
    if root_directory:
        print("root_directory:")
        for entry in root_directory:
            print(
                "  "
                f"name={entry['name']!r} "
                f"short_name={entry['short_name']!r} "
                f"attr=0x{int(entry['attributes']):02x} "
                f"cluster={entry['start_cluster']} "
                f"size={entry['size']} "
                f"chain={entry['cluster_chain']}"
            )

    match_file = summary.get("match_file")
    if match_file:
        print("match_file:")
        print(f"  path={match_file['path']}")
        print(f"  sha256={match_file['sha256']}")
        if match_file["matching_write_requests"]:
            for match in match_file["matching_write_requests"]:
                print(
                    "  "
                    f"write_match=request={match['request_frame']} "
                    f"data={match['data_frame']} "
                    f"lba={match['lba']} "
                    f"sectors={match['sectors']} "
                    f"trailing_zero_padding={match['trailing_zero_padding']}"
                )
        if match_file["matching_fat_entries"]:
            for match in match_file["matching_fat_entries"]:
                print(
                    "  "
                    f"fat_match=name={match['name']!r} "
                    f"short_name={match['short_name']!r} "
                    f"size={match['size']} "
                    f"cluster={match['start_cluster']} "
                    f"chain={match['cluster_chain']}"
                )


def main() -> int:
    args = parse_args()
    records = build_records(args.pcap)
    summary = summarize(records, args.match_file, args.pcap)

    if args.dump_dir:
        args.dump_dir.mkdir(parents=True, exist_ok=True)
        for record in records:
            output = (
                args.dump_dir
                / f"write-{record.request_frame:04d}-lba-{record.lba:06d}-sectors-{record.sectors:03d}.bin"
            )
            output.write_bytes(record.payload)

    if args.reconstruct_image:
        sector_size = int(summary["sector_size"])
        sectors = make_sector_map(records, sector_size)
        reconstruct_image(
            args.reconstruct_image,
            sectors,
            int(summary["image_size_bytes"]),
            sector_size,
        )

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print_summary(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
