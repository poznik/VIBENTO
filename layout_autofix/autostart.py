from __future__ import annotations

import logging
import os
import plistlib
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


DEFAULT_LAUNCH_AGENT_LABEL = "io.vibento.layout-autofix"


@dataclass
class LaunchAgentAutostart:
    label: str = DEFAULT_LAUNCH_AGENT_LABEL
    module_name: str = "layout_autofix.macos_app"
    executable_path: str | None = None
    launch_agents_dir: Path | None = None

    def __post_init__(self) -> None:
        if self.launch_agents_dir is None:
            self.launch_agents_dir = Path.home() / "Library" / "LaunchAgents"
        self._logger = logging.getLogger(__name__)

    @property
    def plist_path(self) -> Path:
        assert self.launch_agents_dir is not None
        return self.launch_agents_dir / f"{self.label}.plist"

    def is_enabled(self) -> bool:
        return self.plist_path.exists()

    def enable(self) -> None:
        was_enabled = self.is_enabled()
        self.plist_path.parent.mkdir(parents=True, exist_ok=True)
        with self.plist_path.open("wb") as plist_file:
            plistlib.dump(self._plist_payload(), plist_file)

        if was_enabled:
            self._run_launchctl(["bootout", self._launch_domain(), str(self.plist_path)])
        self._run_launchctl(["bootstrap", self._launch_domain(), str(self.plist_path)])

    def disable(self) -> None:
        if self.plist_path.exists():
            self._run_launchctl(["bootout", self._launch_domain(), str(self.plist_path)])
        try:
            self.plist_path.unlink()
        except FileNotFoundError:
            pass

    def _plist_payload(self) -> dict[str, object]:
        return {
            "Label": self.label,
            "ProgramArguments": self._program_arguments(),
            "RunAtLoad": True,
            "KeepAlive": False,
            "ProcessType": "Interactive",
        }

    def _program_arguments(self) -> list[str]:
        if self.executable_path:
            return [self.executable_path]

        if getattr(sys, "frozen", False):
            return [str(Path(sys.executable).resolve())]

        return [str(Path(sys.executable).resolve()), "-m", self.module_name]

    @staticmethod
    def _launch_domain() -> str:
        return f"gui/{os.getuid()}"

    def _run_launchctl(self, arguments: list[str]) -> None:
        try:
            result = subprocess.run(
                ["launchctl", *arguments],
                check=False,
                capture_output=True,
                text=True,
            )
        except Exception:
            return

        if result.returncode != 0:
            self._logger.warning(
                "event=launchctl_failed args=%s returncode=%s stderr=%r",
                arguments,
                result.returncode,
                result.stderr.strip(),
            )
