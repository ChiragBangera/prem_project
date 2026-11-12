"""The Apple-silicon driver for the event fetcher: the parts that can be checked without a browser, a Mac or SeleniumBase."""

from __future__ import annotations

from pathlib import Path

from app.events import nativedriver as N


def test_the_chromium_version_is_read_from_what_a_browser_or_driver_prints():
    assert N.major("Brave Browser 157.1.99.56 ") == "157"
    assert N.major("ChromeDriver 157.0.8103.50 (049750111b1e-refs/branch-heads/8103_38@{#8})") == "157"
    assert N.major("Google Chrome 99.0.4844.51") == "99"
    assert N.major("") is None and N.major("no version here") is None


def test_an_apple_silicon_program_is_told_from_an_intel_one_by_its_first_bytes(tmp_path: Path):
    arm, intel, text = tmp_path / "arm", tmp_path / "intel", tmp_path / "text"
    arm.write_bytes(bytes.fromhex("cffaedfe0c000001") + b"\0" * 32)
    intel.write_bytes(bytes.fromhex("cffaedfe07000001") + b"\0" * 32)
    text.write_text("#!/bin/sh\n")
    assert N.is_arm64_binary(arm) and not N.is_arm64_binary(intel) and not N.is_arm64_binary(text)
    assert not N.is_arm64_binary(tmp_path / "missing")


def test_nothing_is_touched_on_a_computer_that_is_not_an_apple_silicon_mac(monkeypatch):
    monkeypatch.setattr(N.sys, "platform", "win32")
    assert N.needs_native_driver() is False
    monkeypatch.setattr(N.sys, "platform", "darwin")
    monkeypatch.setattr(N.platform, "machine", lambda: "x86_64")
    assert N.needs_native_driver() is False
    monkeypatch.setattr(N.platform, "machine", lambda: "arm64")
    monkeypatch.setattr(N, "_says", lambda cmd: "")                # an Intel program starts: Rosetta is there
    assert N.needs_native_driver() is False
    monkeypatch.setattr(N, "_says", lambda cmd: None)              # it does not
    assert N.needs_native_driver() is True


def test_a_failed_step_leaves_the_folder_as_it_was_and_says_why(tmp_path: Path, monkeypatch):
    intel = tmp_path / "uc_driver"
    intel.write_bytes(bytes.fromhex("cffaedfe07000001") + b"intel")
    (tmp_path / "chromedriver").write_bytes(bytes.fromhex("cffaedfe0c000001") + b"arm")
    monkeypatch.setattr(N, "_says", lambda cmd: "Brave Browser 157.1.99.56" if cmd[0] == "browser" else "ChromeDriver 140.0.1.2" if cmd[-1] == "--version" else None)
    monkeypatch.setattr(N, "_download", lambda want: None)          # the download brings nothing newer
    ready, why = N.prepare("browser", folder=tmp_path)
    assert not ready and "not for this browser" in why
    assert intel.read_bytes().endswith(b"intel") and sorted(p.name for p in tmp_path.iterdir()) == ["chromedriver", "uc_driver"]


ARM, INTEL = bytes.fromhex("cffaedfe0c000001"), bytes.fromhex("cffaedfe07000001")


def _pretend(monkeypatch, browser_version: str, downloads: list):
    """A browser of a given version, drivers that print the version written in them, and a download that brings the matching driver."""
    def says(cmd):
        if cmd[0] == "browser":
            return f"Brave Browser {browser_version}.1.99.56"
        if cmd[-1] == "--version":
            return f"ChromeDriver {Path(cmd[0]).read_bytes()[8:11].decode()}.0.1.2"
        return None

    monkeypatch.setattr(N, "_says", says)
    monkeypatch.setattr(N, "_patch", lambda path: path.write_bytes(path.read_bytes() + b" edited"))
    monkeypatch.setattr(N, "_download", lambda want: downloads.append(want))


def test_a_browser_that_updated_itself_gets_a_driver_of_its_new_version(tmp_path: Path, monkeypatch):
    """After an update the driver in place is for the old version. SeleniumBase alone would fetch the Intel build again."""
    folder = tmp_path / "drivers" / "brave_drivers"
    folder.mkdir(parents=True)
    (folder / "uc_driver").write_bytes(ARM + b"156 edited")
    (folder / "chromedriver").write_bytes(ARM + b"156")
    downloads: list = []
    _pretend(monkeypatch, "157", downloads)
    monkeypatch.setattr(N, "_download", lambda want: (downloads.append(want), (folder.parent / "chromedriver").write_bytes(ARM + b"157")))
    ready, what = N.prepare("browser", folder=folder, sign=False)
    assert ready and "157" in what and downloads == ["157"]
    assert (folder / "uc_driver").read_bytes() == ARM + b"157 edited"
    ready, what = N.prepare("browser", folder=folder, sign=False)     # the next run finds it in place and downloads nothing
    assert ready and "already in place" in what and downloads == ["157"]


def test_an_intel_driver_seleniumbase_fetched_again_is_set_aside(tmp_path: Path, monkeypatch):
    (tmp_path / "uc_driver").write_bytes(INTEL + b"157")
    (tmp_path / "chromedriver").write_bytes(ARM + b"157")
    downloads: list = []
    _pretend(monkeypatch, "157", downloads)
    ready, _what = N.prepare("browser", folder=tmp_path, sign=False)
    assert ready and downloads == []
    assert (tmp_path / "uc_driver").read_bytes() == ARM + b"157 edited" and (tmp_path / "uc_driver.intel").read_bytes() == INTEL + b"157"


def test_the_problem_is_known_before_a_run(monkeypatch):
    monkeypatch.setattr(N, "needs_native_driver", lambda: False)
    assert N.problem("browser") is None
    monkeypatch.setattr(N, "needs_native_driver", lambda: True)
    monkeypatch.setattr(N, "prepare", lambda browser: (False, "the edited driver does not start on this Mac"))
    assert N.problem("browser") == "the edited driver does not start on this Mac"
    monkeypatch.setattr(N, "prepare", lambda browser: (True, "the Apple-silicon driver is already in place"))
    assert N.problem("browser") is None
