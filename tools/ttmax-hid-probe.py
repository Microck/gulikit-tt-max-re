from __future__ import annotations

import argparse
import json
import sys
from typing import Any

DEFAULT_VENDOR_ID = 0x3554
DEFAULT_PRODUCT_ID = 0xF508


def parse_int(value: str) -> int:
    return int(value, 0)


def parse_hex_bytes(value: str) -> bytes:
    cleaned = value.replace(" ", "").replace(":", "").replace("-", "")
    if len(cleaned) % 2:
        raise argparse.ArgumentTypeError("hex payload must contain an even number of nybbles")
    try:
        return bytes.fromhex(cleaned)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def normalize_path(path_value: Any) -> tuple[str, str]:
    if isinstance(path_value, (bytes, bytearray)):
        raw = bytes(path_value)
        text = raw.decode("utf-8", errors="backslashreplace")
        return text, raw.hex()
    text = str(path_value)
    return text, text.encode("utf-8", errors="backslashreplace").hex()


def json_safe(value: Any) -> Any:
    if isinstance(value, (bytes, bytearray)):
        return {"hex": bytes(value).hex()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    return value


def load_hid() -> Any:
    try:
        import hid
    except ImportError as exc:
        raise SystemExit(
            "hidapi is required for live probing. Install the project dependencies or "
            "run this tool on the Windows host where hidapi is already installed."
        ) from exc
    return hid


def load_winreg() -> Any:
    if sys.platform != "win32":
        raise SystemExit("registry cache inspection only works on Windows")
    import winreg

    return winreg


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect TT MAX HID collections and safely probe live vendor-defined interfaces. "
            "Read-only actions are the default."
        )
    )
    parser.add_argument("--vendor-id", type=parse_int, default=DEFAULT_VENDOR_ID)
    parser.add_argument("--product-id", type=parse_int, default=DEFAULT_PRODUCT_ID)

    subparsers = parser.add_subparsers(dest="command", required=True)

    enumerate_parser = subparsers.add_parser(
        "enumerate",
        help="List matching HID interfaces visible to hidapi",
    )
    add_common_selection_args(enumerate_parser)
    enumerate_parser.add_argument("--json", action="store_true", help="Emit structured JSON")

    cache_parser = subparsers.add_parser(
        "cache",
        help="Inspect cached Windows registry metadata for the matching USB and HID nodes",
    )
    cache_parser.add_argument("--json", action="store_true", help="Emit structured JSON")

    get_feature_parser = subparsers.add_parser(
        "get-feature",
        help="Read a feature report from a selected HID collection",
    )
    add_common_selection_args(get_feature_parser)
    get_feature_parser.add_argument(
        "--report-id",
        type=parse_int,
        required=True,
        help="Feature report ID, for example 0x01",
    )
    get_feature_parser.add_argument(
        "--length",
        type=parse_int,
        required=True,
        help="Total report length to request, including the report ID byte",
    )

    read_parser = subparsers.add_parser(
        "read",
        help="Read one or more input reports from a selected HID collection",
    )
    add_common_selection_args(read_parser)
    read_parser.add_argument("--count", type=parse_int, default=1, help="How many reports to read")
    read_parser.add_argument(
        "--length",
        type=parse_int,
        default=64,
        help="Maximum report length to read each time",
    )
    read_parser.add_argument(
        "--timeout-ms",
        type=parse_int,
        default=1000,
        help="Per-read timeout in milliseconds",
    )

    send_feature_parser = subparsers.add_parser(
        "send-feature",
        help="Send an explicit feature report payload to a selected HID collection",
    )
    add_common_selection_args(send_feature_parser)
    send_feature_parser.add_argument("payload", type=parse_hex_bytes, help="Feature report payload bytes")

    send_output_parser = subparsers.add_parser(
        "send-output",
        help="Send an explicit output report payload to a selected HID collection",
    )
    add_common_selection_args(send_output_parser)
    send_output_parser.add_argument("payload", type=parse_hex_bytes, help="Output report payload bytes")

    return parser.parse_args()


def add_common_selection_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--index",
        type=parse_int,
        help="Select the Nth matching interface after filtering and sorting",
    )
    parser.add_argument("--usage-page", type=parse_int, help="Match an exact HID usage page")
    parser.add_argument("--usage", type=parse_int, help="Match an exact HID usage")
    parser.add_argument("--interface-number", type=parse_int, help="Match an exact USB interface number")
    parser.add_argument(
        "--path-contains",
        help="Select a device whose hidapi path contains this substring",
    )


def enumerate_devices(vendor_id: int, product_id: int) -> list[dict[str, Any]]:
    hid = load_hid()
    devices = []
    for entry in hid.enumerate(vendor_id, product_id):
        path_text, path_hex = normalize_path(entry.get("path"))
        devices.append(
            {
                "vendor_id": entry.get("vendor_id"),
                "product_id": entry.get("product_id"),
                "release_number": entry.get("release_number"),
                "manufacturer_string": entry.get("manufacturer_string"),
                "product_string": entry.get("product_string"),
                "serial_number": entry.get("serial_number"),
                "usage_page": entry.get("usage_page"),
                "usage": entry.get("usage"),
                "interface_number": entry.get("interface_number"),
                "path_text": path_text,
                "path_hex": path_hex,
            }
        )
    devices.sort(
        key=lambda item: (
            item.get("interface_number") if item.get("interface_number") is not None else 9999,
            item.get("usage_page") if item.get("usage_page") is not None else 9999,
            item.get("usage") if item.get("usage") is not None else 9999,
            item["path_text"],
        )
    )
    return devices


def select_devices(devices: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    selected = devices
    if args.usage_page is not None:
        selected = [device for device in selected if device.get("usage_page") == args.usage_page]
    if args.usage is not None:
        selected = [device for device in selected if device.get("usage") == args.usage]
    if args.interface_number is not None:
        selected = [device for device in selected if device.get("interface_number") == args.interface_number]
    if args.path_contains:
        needle = args.path_contains.lower()
        selected = [device for device in selected if needle in device["path_text"].lower()]
    if args.index is not None:
        if args.index < 0 or args.index >= len(selected):
            raise SystemExit(f"--index {args.index} is out of range for {len(selected)} matching devices")
        return [selected[args.index]]
    return selected


def open_selected_device(args: argparse.Namespace) -> tuple[Any, dict[str, Any]]:
    devices = select_devices(enumerate_devices(args.vendor_id, args.product_id), args)
    if not devices:
        raise SystemExit("no matching HID device found")
    if len(devices) != 1:
        raise SystemExit(
            f"{len(devices)} HID devices match the current filter. Narrow the selection with "
            "--index, --usage-page, --usage, --interface-number, or --path-contains."
        )

    hid = load_hid()
    device = hid.device()
    device.open_path(bytes.fromhex(devices[0]["path_hex"]))
    return device, devices[0]


def format_usage(value: Any) -> str:
    if value is None:
        return "?"
    return f"0x{value:04x}"


def print_device_list(devices: list[dict[str, Any]]) -> None:
    if not devices:
        print("No matching HID devices found.")
        return

    for index, device in enumerate(devices):
        interface_number = device.get("interface_number")
        print(
            f"[{index}] interface={interface_number} "
            f"usage_page={format_usage(device.get('usage_page'))} "
            f"usage={format_usage(device.get('usage'))}"
        )
        print(f"  product={device.get('product_string')!r} manufacturer={device.get('manufacturer_string')!r}")
        print(f"  path={device['path_text']}")


def load_registry_cache(vendor_id: int, product_id: int) -> dict[str, Any]:
    winreg = load_winreg()
    vid = f"{vendor_id:04X}"
    pid = f"{product_id:04X}"
    hid_prefix = f"VID_{vid}&PID_{pid}"
    usb_prefix = f"VID_{vid}&PID_{pid}"

    def read_values(handle: Any) -> dict[str, Any]:
        values = {}
        for index in range(winreg.QueryInfoKey(handle)[1]):
            name, value, _value_type = winreg.EnumValue(handle, index)
            values[name] = value
        return values

    def collect_subtree(root_path: str, prefix: str) -> list[dict[str, Any]]:
        root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, root_path)
        matches = []
        for index in range(winreg.QueryInfoKey(root)[0]):
            key_name = winreg.EnumKey(root, index)
            if not key_name.startswith(prefix):
                continue
            top_key = winreg.OpenKey(root, key_name)
            entry = {"key": key_name, "instances": []}
            for sub_index in range(winreg.QueryInfoKey(top_key)[0]):
                instance_name = winreg.EnumKey(top_key, sub_index)
                instance_key = winreg.OpenKey(top_key, instance_name)
                instance_entry = {
                    "instance": instance_name,
                    "values": read_values(instance_key),
                    "device_parameters": {},
                }
                try:
                    device_parameters = winreg.OpenKey(instance_key, "Device Parameters")
                except FileNotFoundError:
                    device_parameters = None
                if device_parameters is not None:
                    instance_entry["device_parameters"] = read_values(device_parameters)
                entry["instances"].append(instance_entry)
            matches.append(entry)
        return matches

    return {
        "vendor_id": vendor_id,
        "product_id": product_id,
        "hid": collect_subtree(r"SYSTEM\CurrentControlSet\Enum\HID", hid_prefix),
        "usb": collect_subtree(r"SYSTEM\CurrentControlSet\Enum\USB", usb_prefix),
    }


def print_registry_cache(cache: dict[str, Any]) -> None:
    print(f"VID=0x{cache['vendor_id']:04X} PID=0x{cache['product_id']:04X}")
    print("USB nodes:")
    for usb_entry in cache["usb"]:
        print(f"  {usb_entry['key']}")
        for instance in usb_entry["instances"]:
            print(f"    instance={instance['instance']}")
            symbolic_name = instance["device_parameters"].get("SymbolicName")
            location = instance["values"].get("LocationInformation")
            if location:
                print(f"      location={location}")
            if symbolic_name:
                print(f"      symbolic_name={symbolic_name}")

    print("HID nodes:")
    for hid_entry in cache["hid"]:
        print(f"  {hid_entry['key']}")
        for instance in hid_entry["instances"]:
            hardware_id = instance["values"].get("HardwareID")
            if isinstance(hardware_id, list):
                hardware_id_text = " | ".join(hardware_id)
            else:
                hardware_id_text = hardware_id
            print(f"    instance={instance['instance']}")
            if hardware_id_text:
                print(f"      hardware_id={hardware_id_text}")
            device_desc = instance["values"].get("DeviceDesc")
            if device_desc:
                print(f"      device_desc={device_desc}")


def main() -> int:
    args = parse_args()

    if args.command == "enumerate":
        devices = select_devices(enumerate_devices(args.vendor_id, args.product_id), args)
        if args.json:
            print(json.dumps(json_safe(devices), indent=2))
        else:
            print_device_list(devices)
        return 0

    if args.command == "cache":
        cache = load_registry_cache(args.vendor_id, args.product_id)
        if args.json:
            print(json.dumps(json_safe(cache), indent=2))
        else:
            print_registry_cache(cache)
        return 0

    device, selected = open_selected_device(args)
    print(f"Selected path: {selected['path_text']}")

    if args.command == "get-feature":
        response = bytes(device.get_feature_report(args.report_id, args.length))
        print(response.hex())
        return 0

    if args.command == "read":
        for _index in range(args.count):
            report = device.read(args.length, timeout_ms=args.timeout_ms)
            if report:
                print(bytes(report).hex())
            else:
                print("(timeout)")
        return 0

    if args.command == "send-feature":
        written = device.send_feature_report(args.payload)
        print(f"sent={written}")
        return 0

    if args.command == "send-output":
        written = device.write(args.payload)
        print(f"sent={written}")
        return 0

    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
