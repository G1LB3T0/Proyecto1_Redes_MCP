"""Extract only packet metadata and JSON-RPC bodies, excluding HTTP credentials.

Requires Wireshark/TShark and a real pcapng plus its MCP-only TLS key log.
Run: python -m scripts.analyze_capture
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess

from src.mcp.logging import sanitize_for_log


FIELDS = (
    "frame.number", "frame.time_relative", "frame.time_epoch", "frame.len",
    "frame.protocols", "eth.type", "ip.src", "ip.dst", "ip.ttl", "ip.flags.df",
    "tcp.stream", "tcp.srcport", "tcp.dstport", "tcp.flags", "tcp.seq", "tcp.ack", "tcp.len",
    "tcp.analysis.retransmission", "tcp.analysis.fast_retransmission",
    "http.request.method", "http.request.uri", "http.response.code",
    "http.request_in", "http.response_in", "http.file_data",
    "tls.handshake.type", "tls.handshake.extensions.supported_version", "tls.handshake.ciphersuite",
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, default=Path("logs/captures/pharmacy-remote.pcapng"))
    parser.add_argument("--keys", type=Path, default=Path("logs/captures/mcp-tls.keys"))
    parser.add_argument("--output", type=Path, default=Path("docs/evidence"))
    parser.add_argument("--tshark", default=shutil.which("tshark") or r"C:\Program Files\Wireshark\tshark.exe")
    args = parser.parse_args()
    if not args.capture.is_file() or not args.keys.is_file():
        parser.error("A real capture and its TLS key log are required.")
    command = [args.tshark, "-2", "-r", str(args.capture), "-o", f"tls.keylog_file:{args.keys.resolve()}",
               "-T", "fields", "-E", "header=y", "-E", "quote=d", "-E", "occurrence=f"]
    for field in FIELDS:
        command.extend(("-e", field))
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", check=True)
    packets = list(csv.DictReader(io.StringIO(result.stdout), delimiter="\t"))
    events = []
    methods = {}
    for packet in packets:
        raw = packet.pop("http.file_data")
        if not (packet["http.request.method"] or packet["http.response.code"]):
            continue
        event = {"frame": int(packet["frame.number"]), "time_seconds": float(packet["frame.time_relative"]),
                 "stream": int(packet["tcp.stream"]), "http_method": packet["http.request.method"] or None,
                 "http_status": int(packet["http.response.code"]) if packet["http.response.code"] else None,
                 "request_frame": int(packet["http.request_in"]) if packet["http.request_in"] else None,
                 "response_frame": int(packet["http.response_in"]) if packet["http.response_in"] else None}
        message = json.loads(bytes.fromhex(raw.replace(":", "")).decode("utf-8")) if raw else None
        event["message"] = sanitize_for_log(message)
        if isinstance(message, dict) and "method" in message:
            method = message["method"]
            if "id" in message:
                methods[message["id"]] = method
            event["category"] = "synchronization" if method in {"initialize", "notifications/initialized"} else "request"
        elif isinstance(message, dict) and "id" in message:
            event["category"] = "response"
            event["responds_to"] = methods.get(message["id"])
        else:
            event["category"] = "http_session_close" if event["http_method"] == "DELETE" or event["http_status"] == 204 else "http_acknowledgment"
        events.append(event)
    if not any(event["message"] and event["message"].get("method") == "initialize" for event in events):
        raise RuntimeError("No decrypted MCP initialization found; check interface, capture window and TLS keys.")
    summary = {
        "capture_file": args.capture.name,
        "sha256": hashlib.sha256(args.capture.read_bytes()).hexdigest(),
        "frame_count": len(packets),
        "capture_start_epoch": packets[0]["frame.time_epoch"],
        "last_packet_seconds": float(packets[-1]["frame.time_relative"]),
        "tcp_streams": len({p["tcp.stream"] for p in packets if p["tcp.stream"]}),
        "retransmission_frames": [int(p["frame.number"]) for p in packets if p["tcp.analysis.retransmission"] or p["tcp.analysis.fast_retransmission"]],
        "http": events,
        "tls_server_hello": [{"frame": int(p["frame.number"]), "version": p["tls.handshake.extensions.supported_version"],
                               "cipher": p["tls.handshake.ciphersuite"]} for p in packets if p["tls.handshake.type"] == "2"],
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "network-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # The selected fields contain no Authorization, cookies, session IDs or TLS secrets.
    with (args.output / "packets.csv").open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=[field for field in FIELDS if field != "http.file_data"])
        writer.writeheader()
        writer.writerows(packets)
    print(json.dumps({"frames": summary["frame_count"], "tcp_streams": summary["tcp_streams"],
                      "http_events": len(events), "retransmissions": len(summary["retransmission_frames"])}, indent=2))


if __name__ == "__main__":
    main()
