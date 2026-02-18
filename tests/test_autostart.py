import plistlib
import sys

from layout_autofix.autostart import LaunchAgentAutostart


def test_enable_writes_plist_and_calls_launchctl(tmp_path) -> None:
    manager = LaunchAgentAutostart(
        label="io.test.layout-autofix",
        executable_path="/Applications/LayoutAutofix",
        launch_agents_dir=tmp_path,
    )
    calls: list[list[str]] = []
    manager._run_launchctl = lambda args: calls.append(args)  # type: ignore[method-assign]

    manager.enable()

    assert manager.is_enabled() is True
    payload = plistlib.loads(manager.plist_path.read_bytes())
    assert payload["Label"] == "io.test.layout-autofix"
    assert payload["ProgramArguments"] == ["/Applications/LayoutAutofix"]
    assert payload["RunAtLoad"] is True
    assert calls == [["bootstrap", manager._launch_domain(), str(manager.plist_path)]]


def test_disable_unloads_and_deletes_plist(tmp_path) -> None:
    manager = LaunchAgentAutostart(
        label="io.test.layout-autofix",
        executable_path="/Applications/LayoutAutofix",
        launch_agents_dir=tmp_path,
    )
    calls: list[list[str]] = []
    manager._run_launchctl = lambda args: calls.append(args)  # type: ignore[method-assign]
    manager.enable()

    manager.disable()

    assert manager.is_enabled() is False
    assert calls[-1] == ["bootout", manager._launch_domain(), str(manager.plist_path)]


def test_enable_reloads_existing_launch_agent(tmp_path) -> None:
    manager = LaunchAgentAutostart(
        label="io.test.layout-autofix",
        executable_path="/Applications/LayoutAutofix",
        launch_agents_dir=tmp_path,
    )
    manager.plist_path.parent.mkdir(parents=True, exist_ok=True)
    manager.plist_path.write_text("existing", encoding="utf-8")
    calls: list[list[str]] = []
    manager._run_launchctl = lambda args: calls.append(args)  # type: ignore[method-assign]

    manager.enable()

    assert calls == [
        ["bootout", manager._launch_domain(), str(manager.plist_path)],
        ["bootstrap", manager._launch_domain(), str(manager.plist_path)],
    ]


def test_program_arguments_for_non_frozen_runtime(monkeypatch, tmp_path) -> None:
    manager = LaunchAgentAutostart(launch_agents_dir=tmp_path)
    monkeypatch.setattr(sys, "executable", "/usr/bin/python3")
    monkeypatch.delattr(sys, "frozen", raising=False)

    assert manager._program_arguments() == ["/usr/bin/python3", "-m", "layout_autofix.macos_app"]


def test_program_arguments_for_frozen_runtime(monkeypatch, tmp_path) -> None:
    manager = LaunchAgentAutostart(launch_agents_dir=tmp_path)
    monkeypatch.setattr(sys, "executable", "/Applications/LayoutAutofix")
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    assert manager._program_arguments() == ["/Applications/LayoutAutofix"]
