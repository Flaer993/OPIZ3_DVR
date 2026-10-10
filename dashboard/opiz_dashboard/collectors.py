from __future__ import annotations

import json
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import psutil

from .config import resolve_path


def _read_json(path: Path | None) -> dict[str, Any]:
    if not path or not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _fmt_age(value: Any) -> str:
    if not value:
        return "—"
    try:
        if isinstance(value, (int, float)):
            stamp = float(value)
        else:
            stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
        seconds = max(0, int(time.time() - stamp))
        if seconds < 60:
            return f"{seconds}s ago"
        if seconds < 3600:
            return f"{seconds // 60}m ago"
        if seconds < 86400:
            return f"{seconds // 3600}h ago"
        return f"{seconds // 86400}d ago"
    except (ValueError, TypeError, OverflowError):
        return str(value)[:16]


class MetricsCollector:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self._last_net: tuple[float, int, int] | None = None

    def collect(self) -> dict[str, Any]:
        return {
            "system": self._system(),
            "server": self._server(),
            "storage": self._storage(),
            "cameras": self._cameras(),
            "sampled_at": time.time(),
        }

    def _network_counters(self) -> Any:
        interface = self.config.get("network_interface")
        per_nic = psutil.net_io_counters(pernic=True)
        if interface and interface in per_nic:
            return per_nic[interface]
        return psutil.net_io_counters()

    def _system(self) -> dict[str, Any]:
        now = time.monotonic()
        net = self._network_counters()
        up_bps = down_bps = 0.0
        if self._last_net:
            previous_time, previous_sent, previous_recv = self._last_net
            elapsed = max(0.001, now - previous_time)
            up_bps = max(0.0, (net.bytes_sent - previous_sent) / elapsed)
            down_bps = max(0.0, (net.bytes_recv - previous_recv) / elapsed)
        self._last_net = (now, net.bytes_sent, net.bytes_recv)
        root = Path("/") if Path("/").exists() else Path.cwd().anchor
        disk = psutil.disk_usage(str(root))
        return {
            "cpu": psutil.cpu_percent(interval=0.08),
            "ram": psutil.virtual_memory().percent,
            "disk": disk.percent,
            "disk_used": disk.used,
            "disk_total": disk.total,
            "up_bps": up_bps,
            "down_bps": down_bps,
            "tx_packets": getattr(net, "packets_sent", 0),
            "uptime": max(0, int(time.time() - psutil.boot_time())),
        }

    def _server(self) -> dict[str, Any]:
        settings = self.config["server"]
        status = _read_json(resolve_path(self.config, settings.get("status_file")))
        url = settings.get("url", "")
        host = urlparse(url).hostname or ""
        ip_address = str(settings.get("ip_address", "") or host or "—")
        if host and not settings.get("ip_address"):
            try:
                ip_address = socket.gethostbyname(host)
            except OSError:
                pass
        started = time.monotonic()
        online = False
        error = "not configured"
        if url:
            try:
                request = urllib.request.Request(url, method="GET", headers={"User-Agent": "opiz-dashboard/1.0"})
                with urllib.request.urlopen(request, timeout=float(settings.get("timeout_seconds", 0.7))) as response:
                    online = 200 <= response.status < 500
                    error = ""
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                error = str(exc.reason if isinstance(exc, urllib.error.URLError) else exc)[:40]
        latency_ms = int((time.monotonic() - started) * 1000) if url else 0
        return {
            "online": bool(status.get("online", online)),
            "ip_address": str(status.get("ip_address", ip_address)),
            "latency_ms": int(status.get("latency_ms", latency_ms)),
            "sent_packets": int(status.get("sent_packets", self._network_counters().packets_sent)),
            "last_sync": _fmt_age(status.get("last_sync")),
            "queue": int(status.get("queue", status.get("queued", 0))),
            "errors": int(status.get("errors", 0)),
            "message": str(status.get("message", error)),
        }

    def _smart(self, spec: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {
            "name": spec.get("name", Path(spec.get("device", "disk")).name.upper()),
            "device": spec.get("device", ""), "healthy": None, "temperature": None,
            "used_percent": None, "used": 0, "total": 0, "error": "",
        }
        mount = spec.get("mount")
        if mount:
            try:
                usage = shutil.disk_usage(mount)
                result.update(used_percent=round(usage.used * 100 / usage.total), used=usage.used, total=usage.total)
            except OSError as exc:
                result["error"] = str(exc)[:36]
        device = spec.get("device")
        if device:
            try:
                proc = subprocess.run(
                    ["smartctl", "-j", "-a", device], capture_output=True, text=True,
                    timeout=2.5, check=False,
                )
                data = json.loads(proc.stdout or "{}")
                result["healthy"] = data.get("smart_status", {}).get("passed")
                result["temperature"] = data.get("temperature", {}).get("current")
                if result["temperature"] is None:
                    result["temperature"] = data.get("nvme_smart_health_information_log", {}).get("temperature")
                messages = data.get("smartctl", {}).get("messages", [])
                if messages and result["healthy"] is None:
                    result["error"] = str(messages[0].get("string", "SMART unavailable"))[:36]
            except FileNotFoundError:
                result["error"] = "install smartmontools"
            except (subprocess.TimeoutExpired, ValueError, OSError) as exc:
                result["error"] = str(exc)[:36]
        return result

    @staticmethod
    def _raid_status(requested: str) -> tuple[str, bool | None]:
        if requested and requested.lower() != "auto":
            return requested.upper(), None
        try:
            text = Path("/proc/mdstat").read_text(encoding="utf-8")
            array_line = next((line for line in text.splitlines() if line.startswith("md")), "")
            if not array_line:
                return "NO RAID", None
            chunks = array_line.split()
            raid = next((part.upper() for part in chunks if part.startswith("raid")), "MD RAID")
            healthy = "_" not in text and "faulty" not in text.lower()
            return raid.replace("RAID", "RAID "), healthy
        except OSError:
            return "UNKNOWN", None

    def _storage(self) -> dict[str, Any]:
        settings = self.config["storage"]
        raid_type, raid_healthy = self._raid_status(str(settings.get("raid_type", "auto")))
        disks = [self._smart(item) for item in settings.get("devices", [])[:2]]
        while len(disks) < 2:
            disks.append({"name": f"HDD {len(disks)+1}", "healthy": None, "temperature": None,
                          "used_percent": None, "used": 0, "total": 0, "error": "not configured"})
        return {"raid_type": raid_type, "raid_healthy": raid_healthy, "disks": disks}

    def _camera(self, spec: dict[str, Any]) -> dict[str, Any]:
        status = _read_json(resolve_path(self.config, spec.get("status_file")))
        parsed = urlparse(spec.get("url", ""))
        host = spec.get("host") or parsed.hostname
        port = int(spec.get("port") or parsed.port or (554 if parsed.scheme == "rtsp" else 80))
        online = False
        latency_ms = 0
        if host:
            started = time.monotonic()
            try:
                with socket.create_connection((host, port), timeout=0.35):
                    online = True
            except OSError:
                online = False
            latency_ms = int((time.monotonic() - started) * 1000)
        online = bool(status.get("online", online))
        transferring = bool(status.get("transferring", status.get("recording", online)))
        return {
            "name": str(spec.get("name", "CAM"))[:8], "online": online,
            "transferring": transferring, "resolution": str(status.get("resolution", spec.get("resolution", "1080p"))),
            "fps": status.get("fps"), "latency_ms": int(status.get("latency_ms", latency_ms)),
        }

    def _cameras(self) -> list[dict[str, Any]]:
        cameras = [self._camera(item) for item in self.config.get("cameras", [])[:4]]
        while len(cameras) < 4:
            cameras.append({"name": f"CAM {len(cameras)+1}", "online": False, "transferring": False,
                            "resolution": "—", "fps": None, "latency_ms": 0})
        return cameras
