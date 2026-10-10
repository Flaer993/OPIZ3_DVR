from __future__ import annotations

import time
from typing import Callable

from PIL import Image


class SimulatorDisplay:
    def __init__(self, width: int, height: int, on_next: Callable[[], None], on_previous: Callable[[], None]) -> None:
        import tkinter as tk
        from PIL import ImageTk
        self.ImageTk = ImageTk
        self.tk = tk
        self.root = tk.Tk()
        self.root.title("OPiZ3 Dashboard — Space/→ next, ← previous, Esc quit")
        self.root.configure(bg="#05070a")
        self.label = tk.Label(self.root, bd=0, bg="#05070a")
        self.label.pack(padx=18, pady=18)
        self.root.bind("<space>", lambda _event: on_next())
        self.root.bind("<Right>", lambda _event: on_next())
        self.root.bind("<Left>", lambda _event: on_previous())
        self.root.bind("<Escape>", lambda _event: self.close())
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.closed = False
        self.photo = None

    def show(self, image: Image.Image) -> None:
        if self.closed:
            raise KeyboardInterrupt
        preview = image.resize((image.width * 2, image.height * 2), Image.Resampling.NEAREST)
        self.photo = self.ImageTk.PhotoImage(preview)
        self.label.configure(image=self.photo)
        self.root.update_idletasks()
        self.root.update()

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            self.root.destroy()


class ST77xxDisplay:
    """Dependency-light SPI backend for ST7735/ST7789 RGB565 panels."""

    def __init__(self, settings: dict) -> None:
        import spidev
        from periphery import GPIO
        self.settings = settings
        self.width, self.height = int(settings["width"]), int(settings["height"])
        self.spi = spidev.SpiDev()
        self.spi.open(int(settings["spi_bus"]), int(settings["spi_device"]))
        self.spi.max_speed_hz = int(settings.get("spi_hz", 32_000_000))
        self.spi.mode = 0
        chip = settings["gpio_chip"]
        self.dc = GPIO(chip, int(settings["dc_line"]), "out")
        self.reset = GPIO(chip, int(settings["reset_line"]), "out")
        backlight = settings.get("backlight_line")
        self.backlight = GPIO(chip, int(backlight), "out") if backlight is not None else None
        self._reset_panel()
        self._init_panel()

    def _command(self, command: int, data: bytes = b"") -> None:
        self.dc.write(False)
        self.spi.writebytes([command])
        if data:
            self.dc.write(True)
            self.spi.writebytes(list(data))

    def _reset_panel(self) -> None:
        self.reset.write(True); time.sleep(0.05)
        self.reset.write(False); time.sleep(0.05)
        self.reset.write(True); time.sleep(0.12)

    def _init_panel(self) -> None:
        self._command(0x01); time.sleep(0.15)
        self._command(0x11); time.sleep(0.12)
        self._command(0x3A, b"\x55")
        rotation = int(self.settings.get("rotation", 0)) % 360
        madctl = {0: 0x00, 90: 0x60, 180: 0xC0, 270: 0xA0}.get(rotation, 0x00)
        if self.settings.get("bgr", True):
            madctl |= 0x08
        self._command(0x36, bytes([madctl]))
        if self.settings.get("invert", True):
            self._command(0x21)
        self._command(0x13)
        self._command(0x29); time.sleep(0.05)
        if self.backlight:
            self.backlight.write(True)

    @staticmethod
    def _rgb565(image: Image.Image) -> bytes:
        source = image.convert("RGB").tobytes()
        out = bytearray(len(source) // 3 * 2)
        target = 0
        for index in range(0, len(source), 3):
            value = ((source[index] & 0xF8) << 8) | ((source[index + 1] & 0xFC) << 3) | (source[index + 2] >> 3)
            out[target] = value >> 8
            out[target + 1] = value & 0xFF
            target += 2
        return bytes(out)

    def show(self, image: Image.Image) -> None:
        x0, y0 = int(self.settings.get("x_offset", 0)), int(self.settings.get("y_offset", 0))
        x1, y1 = x0 + self.width - 1, y0 + self.height - 1
        self._command(0x2A, bytes([x0 >> 8, x0 & 255, x1 >> 8, x1 & 255]))
        self._command(0x2B, bytes([y0 >> 8, y0 & 255, y1 >> 8, y1 & 255]))
        self._command(0x2C)
        self.dc.write(True)
        payload = self._rgb565(image.resize((self.width, self.height)))
        for index in range(0, len(payload), 4096):
            self.spi.writebytes(list(payload[index:index + 4096]))

    def close(self) -> None:
        if self.backlight:
            self.backlight.write(False)
            self.backlight.close()
        self.dc.close(); self.reset.close(); self.spi.close()


class GPIOButton:
    def __init__(self, settings: dict, on_short: Callable[[], None], on_long: Callable[[], None]) -> None:
        from periphery import GPIO
        self.gpio = GPIO(settings["gpio_chip"], int(settings["line"]), "in")
        self.active_low = bool(settings.get("active_low", True))
        self.debounce = float(settings.get("debounce_ms", 80)) / 1000
        self.long_press = float(settings.get("long_press_ms", 800)) / 1000
        self.on_short, self.on_long = on_short, on_long
        self.was_pressed = False
        self.pressed_at = 0.0
        self.last_event = 0.0

    def poll(self) -> None:
        now = time.monotonic()
        pressed = bool(self.gpio.read()) != self.active_low
        if pressed and not self.was_pressed and now - self.last_event >= self.debounce:
            self.pressed_at = now
        elif not pressed and self.was_pressed and now - self.last_event >= self.debounce:
            (self.on_long if now - self.pressed_at >= self.long_press else self.on_short)()
            self.last_event = now
        self.was_pressed = pressed

    def close(self) -> None:
        self.gpio.close()
