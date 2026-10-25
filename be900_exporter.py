#!/usr/bin/env python3
"""Read-only Prometheus exporter for TP-Link Archer BE900 (no dependencies).

Probes only a configured LAN router. Does not log in, alter settings,
create port mappings, or expose MAC addresses/external IPs in metrics.
"""
from __future__ import annotations

import argparse
import http.server
import ipaddress
import logging
import os
import socket
import threading
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

LOG = logging.getLogger("be900_exporter")
WAN_COMMON = "urn:schemas-upnp-org:service:WANCommonInterfaceConfig:1"
WAN_IP = "urn:schemas-upnp-org:service:WANIPConnection:1"
ACTIONS = {
    WAN_COMMON: (
        "GetCommonLinkProperties", "GetTotalBytesSent", "GetTotalBytesReceived",
        "GetTotalPacketsSent", "GetTotalPacketsReceived",
    ),
    WAN_IP: (
        "GetConnectionTypeInfo", "GetStatusInfo", "GetNATRSIPStatus",
    ),
}
HELP = {
    "be900_upnp_up": "Whether UPnP reads succeeded in the last collection.",
    "be900_tdp_up": "Whether TDP device discovery succeeded in the last collection.",
    "be900_wan_connected": "Whether UPnP reports a connected WAN.",
    "be900_wan_physical_link_up": "Whether the WAN physical link is up.",
    "be900_nat_enabled": "Whether WAN IP Connection NAT is enabled.",
    "be900_wan_uptime_seconds": "WAN connection uptime reported by UPnP.",
    "be900_wan_bytes_sent_raw": "Raw UPnP WAN sent byte counter (may wrap or reset).",
    "be900_wan_bytes_received_raw": "Raw UPnP WAN received byte counter (may wrap or reset).",
    "be900_wan_packets_sent_raw": "Raw UPnP WAN sent packet counter (may wrap or reset).",
    "be900_wan_packets_received_raw": "Raw UPnP WAN received packet counter (may wrap or reset).",
    "be900_wan_upstream_max_bps_reported": "UPnP-reported maximum upstream rate (may be inaccurate).",
    "be900_wan_downstream_max_bps_reported": "UPnP-reported maximum downstream rate (may be inaccurate).",
    "be900_upnp_port_mappings": "Number of port mappings successfully enumerated in the last full scan.",
    "be900_upnp_permanent_port_mappings": "Number of port mappings with unlimited lease in last scan.",
    "be900_upnp_port_mappings_last_success_timestamp_seconds": "Unix time of last successful complete mapping enumeration.",
    "be900_scrape_duration_seconds": "Time spent on the latest BE900 collection.",
    "be900_info": "Router metadata from TDP, excluding MAC, serial and addresses.",
}
TYPE = {k: "gauge" for k in HELP}

def _suffix(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]

def _read_request(request: urllib.request.Request, timeout: float) -> bytes:
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        return resp.read(65536)

def soap_read(ip: str, service: str, action: str, *, timeout: float = 3,
              params: dict[str, str | int] | None = None) -> dict[str, str]:
    path = "/btjhs/ctl/CmnIfCfg" if service == WAN_COMMON else "/btjhs/ctl/IPConn"
    inputs = "".join("<%s>%s</%s>" % (key, value, key)
                     for key, value in (params or {}).items())
    body = (
        '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
        's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
        '<s:Body><u:%s xmlns:u="%s">%s</u:%s></s:Body></s:Envelope>'
        % (action, service, inputs, action)
    ).encode("utf-8")
    request = urllib.request.Request(
        f"http://{ip}:1900{path}", data=body, method="POST",
        headers={"SOAPAction": f'"{service}#{action}"',
                 "Content-Type": 'text/xml; charset="utf-8"'},
    )
    root = ET.fromstring(_read_request(request, timeout))
    if any(_suffix(e.tag) == "Fault" for e in root.iter()):
        raise ValueError("UPnP SOAP Fault")
    return {_suffix(e.tag): e.text or "" for e in root.iter()
            if _suffix(e.tag).startswith("New")}

def tdp_read(ip: str, timeout: float = 2) -> dict[str, str]:
    # Legacy TDP discovery request from public protocol analyses, no auth/write.
    request = bytes.fromhex("0100000200001101000003e56b89a97b")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        sock.sendto(request, (ip, 20002))
        packet, sender = sock.recvfrom(2048)
    if sender[0] != ip or len(packet) < 16 or packet[:4] != request[:4]:
        raise ValueError("Invalid TDP sender or header")
    fields: dict[int, bytes] = {}
    data = packet[16:]
    pos = 0
    while pos + 4 <= len(data):
        kind = int.from_bytes(data[pos:pos + 2], "big")
        size = int.from_bytes(data[pos + 2:pos + 4], "big")
        if kind == 0xff00 and size == 0:
            pos += 4
            continue
        if size > len(data) - pos - 4:
            raise ValueError("Invalid TDP field length")
        fields[kind] = data[pos + 4:pos + 4 + size]
        pos += 4 + size
        pad = (-pos) % 4
        if pad and data[pos:pos + pad] == bytes([255]) + bytes(pad - 1):
            pos += pad
    def string(key: int) -> str:
        return fields.get(key, b"").decode("utf-8", "replace")
    if string(5) != "Archer BE900":
        raise ValueError("Discovery reply is not from an Archer BE900")
    return {"manufacturer": string(3), "model": string(5),
            "device_type": string(9), "role": string(21)}

def _n(d: dict[str, str], key: str) -> int:
    return int(d[key])

def collect_mapping_count(ip: str, timeout: float, cap: int) -> tuple[int, int]:
    permanent = 0
    for i in range(cap):
        try:
            value = soap_read(ip, WAN_IP, "GetGenericPortMappingEntry",
                              timeout=timeout, params={"NewPortMappingIndex": i})
        except urllib.error.HTTPError as e:
            # Error 713 means end of mapping table; other HTTP 500 is failure.
            detail = e.read(2048)
            if e.code == 500 and b"<errorCode>713</errorCode>" in detail:
                return i, permanent
            raise
        if value.get("NewLeaseDuration") == "0":
            permanent += 1
    raise ValueError("Port mapping cap reached; enumeration incomplete")

class Collector:
    def __init__(self, ip: str, timeout: float = 3, ttl: float = 20,
                 mapping_interval: float = 900, max_mappings: int = 256):
        self.ip, self.timeout, self.ttl = ip, timeout, ttl
        self.mapping_interval = mapping_interval
        self.max_mappings = max_mappings
        self.lock = threading.Lock()
        self.last_poll = 0.0
        self.last_mapping_poll = 0.0
        self.mapping: dict[str, float] = {}
        self.values: dict[str, float] = {}
        self.info: dict[str, str] = {}

    def refresh(self) -> None:
        now = time.monotonic()
        with self.lock:
            if now - self.last_poll < self.ttl and self.last_poll:
                return
            began = time.monotonic()
            metrics: dict[str, float] = {"be900_upnp_up": 0, "be900_tdp_up": 0}
            try:
                data: dict[str, str] = {}
                for service, actions in ACTIONS.items():
                    for action in actions:
                        data.update(soap_read(self.ip, service, action,
                                              timeout=self.timeout))
                metrics.update({
                    "be900_wan_connected": float(data["NewConnectionStatus"] == "Connected"),
                    "be900_wan_physical_link_up": float(data["NewPhysicalLinkStatus"] == "Up"),
                    "be900_nat_enabled": float(_n(data, "NewNATEnabled")),
                    "be900_wan_uptime_seconds": float(_n(data, "NewUptime")),
                    "be900_wan_bytes_sent_raw": float(_n(data, "NewTotalBytesSent")),
                    "be900_wan_bytes_received_raw": float(_n(data, "NewTotalBytesReceived")),
                    "be900_wan_packets_sent_raw": float(_n(data, "NewTotalPacketsSent")),
                    "be900_wan_packets_received_raw": float(_n(data, "NewTotalPacketsReceived")),
                    "be900_wan_upstream_max_bps_reported": float(_n(data, "NewLayer1UpstreamMaxBitRate")),
                    "be900_wan_downstream_max_bps_reported": float(_n(data, "NewLayer1DownstreamMaxBitRate")),
                    "be900_upnp_up": 1.0,
                })
            except Exception as exc:
                LOG.warning("UPnP collection failed: %s", exc)
            try:
                self.info = tdp_read(self.ip, timeout=self.timeout)
                metrics["be900_tdp_up"] = 1.0
            except Exception as exc:
                LOG.warning("TDP collection failed: %s", exc)
                self.info = {}
            if now - self.last_mapping_poll >= self.mapping_interval or not self.last_mapping_poll:
                self.last_mapping_poll = now
                try:
                    count, permanent = collect_mapping_count(
                        self.ip, self.timeout, self.max_mappings)
                    self.mapping = {
                        "be900_upnp_port_mappings": float(count),
                        "be900_upnp_permanent_port_mappings": float(permanent),
                        "be900_upnp_port_mappings_last_success_timestamp_seconds": time.time(),
                    }
                except Exception as exc:
                    LOG.warning("UPnP mapping enumeration failed: %s", exc)
            metrics.update(self.mapping)
            metrics["be900_scrape_duration_seconds"] = time.monotonic() - began
            self.values = metrics
            self.last_poll = time.monotonic()

    def render(self) -> bytes:
        self.refresh()
        with self.lock:
            lines: list[str] = []
            for name, value in sorted(self.values.items()):
                lines += [f"# HELP {name} {HELP[name]}",
                          f"# TYPE {name} {TYPE[name]}",
                          f"{name} {value}"]
            if self.info:
                labels = ",".join(
                    f'{key}="{self.info.get(key, "").replace(chr(92), chr(92)+chr(92)).replace(chr(34), chr(92)+chr(34)).replace(chr(10), chr(92)+"n")}"'
                    for key in ("manufacturer", "model", "device_type", "role"))
                lines += [f"# HELP be900_info {HELP['be900_info']}",
                          "# TYPE be900_info gauge",
                          f"be900_info{{{labels}}} 1"]
            return ("\n".join(lines) + "\n").encode("utf-8")

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--router", default=os.environ.get("BE900_ROUTER_IP"),
                   help="LAN IPv4 of the BE900 (or set BE900_ROUTER_IP)")
    p.add_argument("--listen", default="0.0.0.0")
    p.add_argument("--port", type=int, default=9119)
    p.add_argument("--timeout", type=float, default=3)
    p.add_argument("--cache-seconds", type=float, default=20)
    p.add_argument("--mapping-interval", type=float, default=900)
    p.add_argument("--max-mappings", type=int, default=256)
    args = p.parse_args()
    if not args.router:
        p.error("--router or BE900_ROUTER_IP is required")
    try:
        ipaddress.IPv4Address(args.router)
    except ipaddress.AddressValueError as exc:
        p.error(str(exc))
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    collector = Collector(args.router, timeout=args.timeout,
                          ttl=args.cache_seconds,
                          mapping_interval=args.mapping_interval,
                          max_mappings=args.max_mappings)
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path not in ("/metrics", "/healthz"):
                self.send_error(404)
                return
            if self.path == "/healthz":
                body = b"ok\n"
            else:
                body = collector.render()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, format, *values):
            LOG.info("%s - %s", self.client_address[0], format % values)
    with http.server.ThreadingHTTPServer((args.listen, args.port), Handler) as server:
        LOG.info("Listening on %s:%d, router %s", args.listen, args.port, args.router)
        server.serve_forever()

if __name__ == "__main__":
    main()
