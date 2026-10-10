from __future__ import annotations

import argparse
import threading
import time
from pathlib import Path
from typing import Any

from .backends import GPIOButton, ST77xxDisplay, SimulatorDisplay
from .collectors import MetricsCollector
from .config import load_config, resolve_path
from .renderer import DashboardRenderer


class Sampler:
    def __init__(self, collector: MetricsCollector, interval: float) -> None:
        self.collector, self.interval = collector, interval
        self.value: dict[str, Any] = {}
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, name="metrics", daemon=True)

    def _run(self) -> None:
        while not self.stop_event.is_set():
            try:
                value = self.collector.collect()
                with self.lock:
                    self.value = value
            except Exception as exc:  # Keep the display alive if one collector fails.
                with self.lock:
                    self.value["collector_error"] = str(exc)
            self.stop_event.wait(self.interval)

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return dict(self.value)

    def start(self) -> None:
        self.thread.start()

    def close(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Five-page Orange Pi status dashboard")
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--simulator", action="store_true", help="override display backend and open a desktop preview")
    parser.add_argument("--page", type=int, default=1, choices=range(1, 6))
    parser.add_argument("--once", metavar="PNG", help="render one page to PNG and exit")
    args = parser.parse_args()

    config, _ = load_config(args.config)
    display_settings = config["display"]
    width, height = int(display_settings["width"]), int(display_settings["height"])
    renderer = DashboardRenderer(width, height, resolve_path(config, config["media"].get("path")), int(config["media"].get("frame_ms", 80)))
    collector = MetricsCollector(config)
    page = [args.page - 1]
    next_page = lambda: page.__setitem__(0, (page[0] + 1) % 5)
    previous_page = lambda: page.__setitem__(0, (page[0] - 1) % 5)

    if args.once:
        metrics = collector.collect()
        output = Path(args.once).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        renderer.render(page[0], metrics, 0).save(output)
        print(output)
        return

    backend = "simulator" if args.simulator else display_settings.get("backend", "simulator")
    display = SimulatorDisplay(width, height, next_page, previous_page) if backend == "simulator" else ST77xxDisplay(display_settings)
    button = None
    if backend != "simulator" and config["button"].get("enabled"):
        button = GPIOButton(config["button"], next_page, previous_page)
    sampler = Sampler(collector, max(0.25, float(config.get("refresh_seconds", 1.0))))
    sampler.start()
    started = time.monotonic()
    try:
        while True:
            if button:
                button.poll()
            frame = renderer.render(page[0], sampler.snapshot(), int((time.monotonic() - started) * 1000))
            display.show(frame)
            time.sleep(0.05 if page[0] == 4 else 0.12)
    except (KeyboardInterrupt, RuntimeError):
        pass
    finally:
        sampler.close()
        if button:
            button.close()
        display.close()


if __name__ == "__main__":
    main()
