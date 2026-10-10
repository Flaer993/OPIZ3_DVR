from __future__ import annotations

import math
import time
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageSequence


BG = "#090c10"
CARD = "#11161d"
BORDER = "#252c35"
TEXT = "#f1f3f5"
MUTED = "#87909d"
ORANGE = "#ff7900"
GREEN = "#16d97b"
RED = "#ff4d4f"
YELLOW = "#ffc247"


class DashboardRenderer:
    def __init__(self, width: int, height: int, media_path: Path | None = None, media_frame_ms: int = 80) -> None:
        self.width, self.height = width, height
        self.compact = width <= 160 or height <= 160
        self.media_frame_ms = media_frame_ms
        self.fonts = self._load_fonts()
        self.media_frames: list[Image.Image] = []
        self.media_durations: list[int] = []
        if media_path and media_path.exists():
            self._load_media(media_path)

    @staticmethod
    def _font_path(bold: bool = False) -> str | None:
        choices = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        ]
        return next((value for value in choices if Path(value).exists()), None)

    def _load_fonts(self) -> dict[str, ImageFont.FreeTypeFont | ImageFont.ImageFont]:
        regular, bold = self._font_path(), self._font_path(True)
        def font(size: int, strong: bool = False):
            path = bold if strong else regular
            return ImageFont.truetype(path, size) if path else ImageFont.load_default()
        if self.compact:
            return {"xs": font(7), "sm": font(8), "md": font(10, True), "lg": font(15, True), "xl": font(22, True)}
        return {"xs": font(9), "sm": font(11), "md": font(14, True), "lg": font(21, True), "xl": font(31, True)}

    def _load_media(self, path: Path) -> None:
        try:
            with Image.open(path) as source:
                for frame in ImageSequence.Iterator(source):
                    rendered = ImageOps.fit(frame.convert("RGB"), (self.width, self.height), Image.Resampling.LANCZOS)
                    self.media_frames.append(rendered.copy())
                    self.media_durations.append(int(frame.info.get("duration", self.media_frame_ms)))
        except (OSError, ValueError):
            self.media_frames = []

    @staticmethod
    def _bytes(value: float) -> str:
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if abs(value) < 1024 or unit == "TB":
                return f"{value:.0f}{unit}" if unit in {"B", "KB", "MB"} else f"{value:.1f}{unit}"
            value /= 1024
        return "—"

    def _canvas(self) -> tuple[Image.Image, ImageDraw.ImageDraw]:
        image = Image.new("RGB", (self.width, self.height), BG)
        return image, ImageDraw.Draw(image)

    def _header(self, draw: ImageDraw.ImageDraw, title: str, page: int, status: str = "") -> None:
        if self.compact:
            draw.text((5, 4), title, font=self.fonts["lg"], fill=TEXT)
            if status:
                bbox = draw.textbbox((0, 0), status, font=self.fonts["xs"])
                draw.text((self.width - 5 - (bbox[2] - bbox[0]), 7), status, font=self.fonts["xs"], fill=MUTED)
            cy = self.height - 4
            start = (self.width - 36) // 2
            for index in range(5):
                x = start + index * 9
                draw.ellipse((x - 2, cy - 2, x + 2, cy + 2), fill=ORANGE if index == page else "#39414c")
            return
        draw.text((12, 10), title, font=self.fonts["lg"], fill=TEXT)
        if status:
            bbox = draw.textbbox((0, 0), status, font=self.fonts["xs"])
            draw.text((self.width - 12 - (bbox[2] - bbox[0]), 15), status, font=self.fonts["xs"], fill=MUTED)
        cy = self.height - 8
        total = 5 * 10
        start = (self.width - total) // 2 + 4
        for index in range(5):
            draw.ellipse((start + index * 10 - 3, cy - 3, start + index * 10 + 3, cy + 3), fill=ORANGE if index == page else "#39414c")

    @staticmethod
    def _card(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], radius: int = 9) -> None:
        draw.rounded_rectangle(box, radius=radius, fill=CARD, outline=BORDER, width=1)

    def _bar(self, draw: ImageDraw.ImageDraw, xy: tuple[int, int], width: int, value: float | None, color: str = ORANGE) -> None:
        x, y = xy
        draw.rounded_rectangle((x, y, x + width, y + 5), radius=3, fill="#252b33")
        if value is not None:
            filled = max(3, round(width * max(0, min(100, value)) / 100))
            draw.rounded_rectangle((x, y, x + filled, y + 5), radius=3, fill=color)

    def _system(self, data: dict[str, Any]) -> Image.Image:
        if self.compact:
            return self._system_compact(data)
        image, draw = self._canvas()
        uptime = data.get("uptime", 0)
        self._header(draw, "SYSTEM", 0, f"UP {uptime // 86400}d {(uptime % 86400)//3600}h")
        cards = [(10, 42, 115, 123), (125, 42, 230, 123), (10, 130, 115, 220), (125, 130, 230, 220)]
        labels = ["CPU", "RAM", "SD / ROM", "NETWORK"]
        for box, label in zip(cards, labels):
            self._card(draw, box)
            draw.text((box[0] + 9, box[1] + 7), label, font=self.fonts["sm"], fill=TEXT)
        cpu, ram, disk = data.get("cpu", 0), data.get("ram", 0), data.get("disk", 0)
        for box, value in zip(cards[:3], (cpu, ram, disk)):
            draw.text((box[0] + 9, box[1] + 26), f"{value:.0f}%", font=self.fonts["xl"], fill=ORANGE)
            self._bar(draw, (box[0] + 9, box[3] - 13), box[2] - box[0] - 18, value)
        draw.text((19, 190), f"{self._bytes(data.get('disk_used', 0))} / {self._bytes(data.get('disk_total', 0))}", font=self.fonts["xs"], fill=MUTED)
        net = cards[3]
        draw.text((net[0] + 9, net[1] + 31), f"↑ {self._bytes(data.get('up_bps', 0))}/s", font=self.fonts["md"], fill=ORANGE)
        draw.text((net[0] + 9, net[1] + 55), f"↓ {self._bytes(data.get('down_bps', 0))}/s", font=self.fonts["md"], fill=TEXT)
        return image

    def _server(self, data: dict[str, Any]) -> Image.Image:
        if self.compact:
            return self._server_compact(data)
        image, draw = self._canvas()
        online = data.get("online", False)
        self._header(draw, "SERVER", 1, "● ONLINE" if online else "● OFFLINE")
        self._card(draw, (10, 43, 230, 103))
        color = GREEN if online else RED
        draw.ellipse((22, 60, 38, 76), fill=color)
        draw.text((49, 54), "CONNECTED" if online else "NO CONNECTION", font=self.fonts["md"], fill=TEXT)
        draw.text((49, 76), f"IP {data.get('ip_address', '—')}", font=self.fonts["xs"], fill=MUTED)
        latency = f"{data.get('latency_ms', 0)} ms"
        latency_box = draw.textbbox((0, 0), latency, font=self.fonts["xs"])
        draw.text((220 - (latency_box[2] - latency_box[0]), 76), latency, font=self.fonts["xs"], fill=MUTED)
        rows = [
            ("SENT", f"{data.get('sent_packets', 0):,}"),
            ("LAST SYNC", str(data.get("last_sync", "—"))),
            ("QUEUE", str(data.get("queue", 0))),
            ("ERRORS", str(data.get("errors", 0))),
        ]
        y = 112
        for label, value in rows:
            draw.line((14, y + 22, 226, y + 22), fill=BORDER)
            draw.text((15, y), label, font=self.fonts["sm"], fill=MUTED)
            bbox = draw.textbbox((0, 0), value, font=self.fonts["md"])
            draw.text((225 - (bbox[2] - bbox[0]), y - 1), value, font=self.fonts["md"], fill=GREEN if label == "ERRORS" and value == "0" else TEXT)
            y += 26
        return image

    def _storage(self, data: dict[str, Any]) -> Image.Image:
        if self.compact:
            return self._storage_compact(data)
        image, draw = self._canvas()
        raid = data.get("raid_type", "UNKNOWN")
        self._header(draw, "STORAGE", 2, raid)
        for index, disk in enumerate(data.get("disks", [])[:2]):
            top = 43 + index * 80
            self._card(draw, (10, top, 230, top + 70))
            health = disk.get("healthy")
            color = GREEN if health is True else RED if health is False else YELLOW
            state = "HEALTHY" if health is True else "FAILED" if health is False else "UNKNOWN"
            draw.text((20, top + 8), str(disk.get("name", "HDD")), font=self.fonts["md"], fill=TEXT)
            draw.ellipse((83, top + 11, 91, top + 19), fill=color)
            draw.text((96, top + 7), state, font=self.fonts["xs"], fill=color)
            temp = disk.get("temperature")
            draw.text((186, top + 8), f"{temp}°C" if temp is not None else "—°C", font=self.fonts["sm"], fill=MUTED)
            used = disk.get("used_percent")
            draw.text((20, top + 29), f"{used}%" if used is not None else "—%", font=self.fonts["lg"], fill=TEXT)
            detail = f"{self._bytes(disk.get('used', 0))}/{self._bytes(disk.get('total', 0))}" if disk.get("total") else disk.get("error", "")
            draw.text((78, top + 33), str(detail)[:22], font=self.fonts["xs"], fill=MUTED)
            self._bar(draw, (20, top + 57), 200, used, ORANGE if used is None or used < 85 else RED)
        self._card(draw, (10, 205, 230, 220), radius=6)
        raid_color = RED if data.get("raid_healthy") is False else GREEN if data.get("raid_healthy") is True else MUTED
        draw.ellipse((18, 209, 26, 217), fill=raid_color)
        draw.text((32, 207), f"ARRAY  {raid}", font=self.fonts["xs"], fill=TEXT)
        return image

    def _cameras(self, data: list[dict[str, Any]]) -> Image.Image:
        if self.compact:
            return self._cameras_compact(data)
        image, draw = self._canvas()
        online_count = sum(1 for camera in data if camera.get("online"))
        self._header(draw, "CAMERAS", 3, f"{online_count}/{len(data)} ONLINE")
        boxes = [(10, 43, 115, 124), (125, 43, 230, 124), (10, 133, 115, 214), (125, 133, 230, 214)]
        for camera, box in zip(data, boxes):
            self._card(draw, box)
            online = camera.get("online", False)
            transfer = camera.get("transferring", False)
            draw.ellipse((box[0] + 9, box[1] + 10, box[0] + 19, box[1] + 20), fill=GREEN if online else RED)
            draw.text((box[0] + 25, box[1] + 7), camera.get("name", "CAM"), font=self.fonts["md"], fill=TEXT)
            # Minimal camera glyph.
            draw.rounded_rectangle((box[0] + 29, box[1] + 32, box[0] + 69, box[1] + 56), radius=4, outline=MUTED, width=2)
            draw.polygon([(box[0] + 69, box[1] + 38), (box[0] + 83, box[1] + 33), (box[0] + 83, box[1] + 55), (box[0] + 69, box[1] + 50)], outline=MUTED)
            label = "● REC" if online and transfer else "LIVE" if online else "OFFLINE"
            draw.text((box[0] + 10, box[1] + 62), label, font=self.fonts["xs"], fill=RED if "REC" in label else GREEN if online else MUTED)
            bbox = draw.textbbox((0, 0), camera.get("resolution", "—"), font=self.fonts["xs"])
            draw.text((box[2] - 9 - (bbox[2] - bbox[0]), box[1] + 62), camera.get("resolution", "—"), font=self.fonts["xs"], fill=MUTED)
        return image

    def _visual(self, elapsed_ms: int) -> Image.Image:
        if self.media_frames:
            total = sum(self.media_durations) or 1
            position = elapsed_ms % total
            for frame, duration in zip(self.media_frames, self.media_durations):
                if position < duration:
                    image = frame.copy()
                    break
                position -= duration
            else:
                image = self.media_frames[-1].copy()
            draw = ImageDraw.Draw(image)
            if self.compact:
                draw.rounded_rectangle((3, 3, 56, 22), radius=5, fill=(9, 12, 16))
                draw.text((8, 7), "VISUAL", font=self.fonts["md"], fill=TEXT)
            else:
                draw.rounded_rectangle((7, 7, 79, 31), radius=7, fill=(9, 12, 16))
                draw.text((14, 12), "VISUAL", font=self.fonts["md"], fill=TEXT)
            self._header(draw, "", 4)
            return image
        image, draw = self._canvas()
        self._header(draw, "VISUAL", 4, time.strftime("%H:%M"))
        phase = elapsed_ms / 550.0
        center = (157, 104)
        for radius in (22, 42, 62, 82):
            draw.ellipse((center[0]-radius, center[1]-radius, center[0]+radius, center[1]+radius), outline="#733400")
        angle = phase % (2 * math.pi)
        draw.line((center[0], center[1], center[0] + 82 * math.cos(angle), center[1] + 82 * math.sin(angle)), fill=ORANGE, width=2)
        for x in range(0, self.width, 4):
            y = 174 + 18 * math.sin(x / 25 + phase)
            draw.ellipse((x, y, x + 2, y + 2), fill=ORANGE)
        return image

    def _system_compact(self, data: dict[str, Any]) -> Image.Image:
        image, draw = self._canvas()
        uptime = data.get("uptime", 0)
        self._header(draw, "SYSTEM", 0, f"{uptime // 86400}d {(uptime % 86400)//3600}h")
        cards = [(4, 26, 62, 83), (66, 26, 124, 83), (4, 87, 62, 148), (66, 87, 124, 148)]
        labels = ("CPU", "RAM", "SD", "NET")
        for box, label in zip(cards, labels):
            self._card(draw, box, radius=6)
            draw.text((box[0] + 5, box[1] + 5), label, font=self.fonts["sm"], fill=MUTED)
        values = (data.get("cpu", 0), data.get("ram", 0), data.get("disk", 0))
        for box, value in zip(cards[:3], values):
            draw.text((box[0] + 5, box[1] + 19), f"{value:.0f}%", font=self.fonts["xl"], fill=ORANGE)
            self._bar(draw, (box[0] + 5, box[3] - 9), box[2] - box[0] - 10, value)
        net = cards[3]
        draw.text((net[0] + 5, net[1] + 20), f"↑{self._bytes(data.get('up_bps', 0))}/s", font=self.fonts["md"], fill=ORANGE)
        draw.text((net[0] + 5, net[1] + 38), f"↓{self._bytes(data.get('down_bps', 0))}/s", font=self.fonts["md"], fill=TEXT)
        return image

    def _server_compact(self, data: dict[str, Any]) -> Image.Image:
        image, draw = self._canvas()
        online = data.get("online", False)
        self._header(draw, "SERVER", 1, "● ON" if online else "● OFF")
        self._card(draw, (4, 26, 124, 68), radius=6)
        color = GREEN if online else RED
        draw.ellipse((11, 36, 21, 46), fill=color)
        draw.text((27, 31), "CONNECTED" if online else "OFFLINE", font=self.fonts["md"], fill=TEXT)
        draw.text((27, 47), f"IP {data.get('ip_address', '—')}", font=self.fonts["xs"], fill=MUTED)
        latency = f"{data.get('latency_ms', 0)}ms"
        latency_box = draw.textbbox((0, 0), latency, font=self.fonts["xs"])
        draw.text((119 - (latency_box[2] - latency_box[0]), 47), latency, font=self.fonts["xs"], fill=MUTED)
        rows = (("SENT", f"{data.get('sent_packets', 0):,}"), ("SYNC", str(data.get("last_sync", "—"))),
                ("QUEUE", str(data.get("queue", 0))), ("ERRORS", str(data.get("errors", 0))))
        y = 74
        for label, value in rows:
            draw.text((6, y), label, font=self.fonts["sm"], fill=MUTED)
            bbox = draw.textbbox((0, 0), value, font=self.fonts["md"])
            draw.text((122 - (bbox[2] - bbox[0]), y - 1), value, font=self.fonts["md"], fill=GREEN if label == "ERRORS" and value == "0" else TEXT)
            draw.line((5, y + 15, 123, y + 15), fill=BORDER)
            y += 18
        return image

    def _storage_compact(self, data: dict[str, Any]) -> Image.Image:
        image, draw = self._canvas()
        raid = data.get("raid_type", "UNKNOWN")
        self._header(draw, "STORAGE", 2, raid)
        for index, disk in enumerate(data.get("disks", [])[:2]):
            top = 26 + index * 54
            self._card(draw, (4, top, 124, top + 50), radius=6)
            health = disk.get("healthy")
            color = GREEN if health is True else RED if health is False else YELLOW
            state = "OK" if health is True else "FAIL" if health is False else "?"
            draw.text((10, top + 5), str(disk.get("name", "HDD")), font=self.fonts["md"], fill=TEXT)
            draw.ellipse((47, top + 8, 53, top + 14), fill=color)
            draw.text((57, top + 5), state, font=self.fonts["xs"], fill=color)
            temperature = disk.get("temperature")
            temp = f"{temperature}°" if temperature is not None else "—°"
            temp_box = draw.textbbox((0, 0), temp, font=self.fonts["sm"])
            draw.text((118 - (temp_box[2] - temp_box[0]), top + 5), temp, font=self.fonts["sm"], fill=MUTED)
            used = disk.get("used_percent")
            draw.text((10, top + 20), f"{used}%" if used is not None else "—%", font=self.fonts["lg"], fill=TEXT)
            detail = f"{self._bytes(disk.get('used', 0))}/{self._bytes(disk.get('total', 0))}" if disk.get("total") else disk.get("error", "")
            draw.text((47, top + 23), str(detail)[:14], font=self.fonts["xs"], fill=MUTED)
            self._bar(draw, (10, top + 40), 108, used, ORANGE if used is None or used < 85 else RED)
        raid_color = RED if data.get("raid_healthy") is False else GREEN if data.get("raid_healthy") is True else MUTED
        draw.ellipse((7, 137, 13, 143), fill=raid_color)
        draw.text((18, 135), f"ARRAY  {raid}", font=self.fonts["xs"], fill=TEXT)
        return image

    def _cameras_compact(self, data: list[dict[str, Any]]) -> Image.Image:
        image, draw = self._canvas()
        online_count = sum(1 for camera in data if camera.get("online"))
        self._header(draw, "CAMERAS", 3, f"{online_count}/{len(data)} ON")
        for index, camera in enumerate(data[:4]):
            top = 27 + index * 29
            self._card(draw, (4, top, 124, top + 25), radius=5)
            online = camera.get("online", False)
            transfer = camera.get("transferring", False)
            draw.ellipse((10, top + 8, 18, top + 16), fill=GREEN if online else RED)
            draw.text((23, top + 5), camera.get("name", "CAM"), font=self.fonts["md"], fill=TEXT)
            state = "REC" if online and transfer else "LIVE" if online else "OFF"
            state_color = RED if state == "REC" else GREEN if online else MUTED
            draw.text((66, top + 6), state, font=self.fonts["sm"], fill=state_color)
            resolution = str(camera.get("resolution", "—"))
            bbox = draw.textbbox((0, 0), resolution, font=self.fonts["xs"])
            draw.text((118 - (bbox[2] - bbox[0]), top + 7), resolution, font=self.fonts["xs"], fill=MUTED)
        return image

    def render(self, page: int, metrics: dict[str, Any], elapsed_ms: int = 0) -> Image.Image:
        if page == 0:
            return self._system(metrics.get("system", {}))
        if page == 1:
            return self._server(metrics.get("server", {}))
        if page == 2:
            return self._storage(metrics.get("storage", {}))
        if page == 3:
            return self._cameras(metrics.get("cameras", []))
        return self._visual(elapsed_ms)
