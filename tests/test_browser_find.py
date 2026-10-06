"""Finding the browser the event fetcher drives, on each system."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app.events import fetch
from app.sync import autosync

EDGE = "Microsoft/Edge/Application/msedge.exe"
CHROME = "Google/Chrome/Application/chrome.exe"
BRAVE = "BraveSoftware/Brave-Browser/Application/brave.exe"
CHROMIUM = "Chromium/Application/chrome.exe"


def put(root: Path, relative: str) -> str:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("")
    return str(path)


@pytest.fixture
def windows(monkeypatch, tmp_path):
    """A Windows with its three install roots empty, nothing registered and nothing on the PATH; returns the roots."""
    roots = {"PROGRAMFILES": tmp_path / "Program Files", "PROGRAMFILES(X86)": tmp_path / "Program Files (x86)", "LOCALAPPDATA": tmp_path / "AppData" / "Local"}
    for name, root in roots.items():
        root.mkdir(parents=True)
        monkeypatch.setenv(name, str(root))
    monkeypatch.delenv("PREM_BROWSER", raising=False)
    monkeypatch.setattr(fetch, "_app_path", lambda exe: None)
    monkeypatch.setattr(fetch.shutil, "which", lambda name: None)
    return roots


def test_chrome_is_found_where_windows_puts_it(windows):
    chrome = put(windows["PROGRAMFILES"], CHROME)
    assert fetch.find_browser("win32") == chrome


def test_a_chrome_installed_for_one_user_is_found(windows):
    chrome = put(windows["LOCALAPPDATA"], CHROME)
    assert fetch.find_browser("win32") == chrome


def test_a_32_bit_chrome_is_found(windows):
    chrome = put(windows["PROGRAMFILES(X86)"], CHROME)
    assert fetch.find_browser("win32") == chrome


def test_chrome_comes_before_brave_and_chromium(windows):
    put(windows["PROGRAMFILES"], BRAVE)
    put(windows["PROGRAMFILES"], CHROMIUM)
    chrome = put(windows["PROGRAMFILES(X86)"], CHROME)
    assert fetch.find_browser("win32") == chrome


def test_brave_and_chromium_are_found_without_chrome(windows):
    chromium = put(windows["LOCALAPPDATA"], CHROMIUM)
    brave = put(windows["PROGRAMFILES"], BRAVE)
    assert fetch.find_browser("win32") == brave
    Path(brave).unlink()
    assert fetch.find_browser("win32") == chromium


def test_a_browser_installed_somewhere_else_is_found_through_the_registry(windows, monkeypatch, tmp_path):
    elsewhere = put(tmp_path / "D", "Apps/Chrome/chrome.exe")
    monkeypatch.setattr(fetch, "_app_path", lambda exe: elsewhere if exe == "chrome.exe" else None)
    assert fetch.find_browser("win32") == elsewhere


def test_edge_alone_is_not_enough(windows, monkeypatch, tmp_path):
    # Edge comes with Windows 10 and 11, but the tool that reads WhoScored ignores it, so it must not be offered as the browser
    put(windows["PROGRAMFILES(X86)"], EDGE)
    edge = put(tmp_path / "E", "Edge/msedge.exe")
    monkeypatch.setattr(fetch, "_app_path", lambda exe: edge if exe == "msedge.exe" else None)
    monkeypatch.setattr(fetch.shutil, "which", lambda name: "C:/Windows/" + name + ".exe" if name == "msedge" else None)
    assert fetch.find_browser("win32") is None


def test_windows_with_no_browser_finds_none(windows):
    assert fetch.find_browser("win32") is None


def test_windows_does_not_look_in_the_mac_or_linux_places(windows, monkeypatch, tmp_path):
    mac = put(tmp_path, "Applications/Google Chrome")
    monkeypatch.setattr(fetch, "BROWSERS", (mac,))
    monkeypatch.setattr(fetch.shutil, "which", lambda name: "/usr/bin/" + name if name == "google-chrome" else None)
    assert fetch.find_browser("win32") is None


def test_prem_browser_wins_and_a_wrong_or_edge_one_is_ignored(windows, monkeypatch, tmp_path):
    chrome = put(windows["PROGRAMFILES"], CHROME)
    mine = put(tmp_path, "mine/brave.exe")
    monkeypatch.setenv("PREM_BROWSER", mine)
    assert fetch.find_browser("win32") == mine
    monkeypatch.setenv("PREM_BROWSER", str(tmp_path / "not-there.exe"))
    assert fetch.find_browser("win32") == chrome                     # a path that is not a file does not stop the search
    monkeypatch.setenv("PREM_BROWSER", put(tmp_path, "mine/msedge.exe"))
    assert fetch.find_browser("win32") == chrome                     # nor does an Edge, which cannot be used
    monkeypatch.setattr(fetch.shutil, "which", lambda name: "/opt/bin/" + name if name == "my-browser" else None)
    monkeypatch.setenv("PREM_BROWSER", "my-browser")                 # a command on the PATH is fine too
    assert fetch.find_browser("win32") == "/opt/bin/my-browser"


def test_linux_commands_include_the_stable_channel_and_leave_edge_out(monkeypatch):
    monkeypatch.delenv("PREM_BROWSER", raising=False)
    monkeypatch.setattr(fetch, "BROWSERS", ())
    wanted = {"microsoft-edge": "/usr/bin/microsoft-edge", "microsoft-edge-stable": "/usr/bin/microsoft-edge-stable"}
    monkeypatch.setattr(fetch.shutil, "which", lambda name: wanted.get(name))
    assert fetch.find_browser("linux") is None
    wanted["google-chrome-stable"] = "/usr/bin/google-chrome-stable"
    assert fetch.find_browser("linux") == "/usr/bin/google-chrome-stable"


def test_mac_apps_are_still_found_first_and_edge_is_not_among_them(monkeypatch, tmp_path):
    monkeypatch.delenv("PREM_BROWSER", raising=False)
    assert not any("Edge" in path for path in fetch.BROWSERS)
    chrome = put(tmp_path, "Applications/Google Chrome")
    monkeypatch.setattr(fetch, "BROWSERS", (str(tmp_path / "Applications" / "Missing"), chrome))
    monkeypatch.setattr(fetch.shutil, "which", lambda name: "/usr/bin/" + name)
    assert fetch.find_browser("darwin") == chrome


def test_an_edge_given_by_hand_is_refused_with_the_reason(tmp_path):
    edge = put(tmp_path, EDGE)
    with pytest.raises(fetch.FetchUnavailable, match="Edge cannot be used"):
        fetch.make_reader("EPL", 2025, data_dir=tmp_path, browser=edge)


def test_the_message_for_no_browser_says_which_ones_work(monkeypatch, tmp_path):
    monkeypatch.setattr(fetch, "find_browser", lambda platform=None: None)
    with pytest.raises(fetch.FetchUnavailable, match="Chrome, Chromium or Brave"):
        fetch.make_reader("EPL", 2025, data_dir=tmp_path)


@pytest.mark.skipif(sys.platform != "win32", reason="the real Windows places, on a real Windows")
def test_a_real_windows_with_chrome_finds_it():
    # the Windows build machine has Chrome installed, in Program Files, as it has Edge; Edge must not be what is found
    found = fetch.find_browser()
    assert found and found.lower().endswith("chrome.exe") and Path(found).is_file(), "no Chrome was found on this Windows"


def test_the_data_page_says_how_to_install_the_package(monkeypatch):
    monkeypatch.setattr(autosync.importlib.util, "find_spec", lambda name: None)
    capability = autosync.AutoSync.events_capability()
    assert capability["available"] is False and "uv sync --extra events" in capability["hint"]


def test_the_data_page_says_which_browsers_work_and_that_edge_does_not(monkeypatch):
    monkeypatch.setattr(autosync.importlib.util, "find_spec", lambda name: object())
    monkeypatch.setattr(autosync, "find_browser", lambda: None)
    capability = autosync.AutoSync.events_capability()
    assert capability["available"] is False
    assert "Chrome, Chromium or Brave" in capability["reason"] and "Edge does not work" in capability["hint"] and "PREM_BROWSER" in capability["hint"]


@pytest.mark.skipif(sys.platform != "win32", reason="the Windows registry")
def test_a_real_windows_registry_tells_where_chrome_is():
    # the "App Paths" entry is how a Chrome installed in an unusual folder is found; it must read back as a real file
    registered = fetch._app_path("chrome.exe")
    assert registered and Path(registered).is_file(), "no App Paths entry for chrome.exe on this Windows"
    assert fetch._app_path("no-such-program.exe") is None
