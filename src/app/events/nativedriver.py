"""An Apple-silicon driver for the event fetcher, so it does not need Rosetta.

SeleniumBase's "undetected" mode (which soccerdata uses to read WhoScored) keeps its own copy of ChromeDriver, ``uc_driver``, and edits a
few bytes of it. On an Apple-silicon Mac it downloads the *Intel* build for that, on purpose: macOS refuses to run an Apple-silicon
program whose bytes changed after it was signed, and an Intel program has no such rule. The Intel build needs Rosetta. A Mac without
Rosetta (macOS 27 does not install it by itself) then fails with "Your Mac needs Rosetta 2 to use UC Mode!", which is how event data
stopped arriving in November 2026.

What this does instead, only on such a Mac: take the Apple-silicon ChromeDriver SeleniumBase already keeps beside it (same browser
version), make the same edit SeleniumBase would, and sign the result again on this computer (an "ad hoc" signature: no account, no
network). SeleniumBase finds a ``uc_driver`` of the right version that is already edited and uses it as it is.

Nothing here runs on Windows, Linux, an Intel Mac, or a Mac that has Rosetta. Every step that fails leaves things as they were and
returns the reason, so the fetcher's own error still says what to do.
"""

from __future__ import annotations

import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

ARM64_MAGIC = bytes.fromhex("cffaedfe0c000001")   # a 64-bit Mach-O file for arm64: magic number, then the CPU type


def is_arm64_binary(path: Path) -> bool:
    try:
        with open(path, "rb") as fh:
            return fh.read(8) == ARM64_MAGIC
    except OSError:
        return False


def major(version_text: str) -> str | None:
    """The Chromium major version in what a browser or driver prints: "Brave Browser 157.1.99.56" and "ChromeDriver 157.0.8103.50 (...)"
    both give "157"."""
    found = re.search(r"(\d{2,3})\.\d+\.\d+", version_text or "")
    return found.group(1) if found else None


def _says(cmd: list[str]) -> str | None:
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=20, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def needs_native_driver() -> bool:
    """An Apple-silicon Mac on which an Intel program cannot start."""
    if sys.platform != "darwin" or platform.machine() != "arm64":
        return False
    return _says(["/usr/bin/arch", "-x86_64", "/usr/bin/true"]) is None


def driver_dir(browser: str) -> Path | None:
    """The folder SeleniumBase keeps this browser's drivers in."""
    try:
        import seleniumbase
    except ImportError:
        return None
    base = Path(seleniumbase.__file__).parent / "drivers"
    name = browser.lower()
    for word, folder in (("brave", "brave_drivers"), ("chromium", "chromium_drivers")):
        if word in name:
            return base / folder
    return base


def _fits(path: Path, want: str | None) -> bool:
    """An Apple-silicon ChromeDriver, for this browser's version when that is known."""
    return is_arm64_binary(path) and (not want or major(_says([str(path), "--version"]) or "") == want)


def _download(want: str | None) -> None:
    """Have SeleniumBase fetch the Apple-silicon ChromeDriver for this browser version: the one download this needs, from the same place
    SeleniumBase itself uses."""
    from seleniumbase.console_scripts import sb_install

    argv = sys.argv
    try:
        sb_install.main(override=f"chromedriver {want or 'latest'}")
    finally:
        sys.argv = argv


def _patch(path: Path) -> None:
    """The edit SeleniumBase's undetected mode makes to its driver."""
    from seleniumbase.undetected.patcher import Patcher

    patcher = Patcher(executable_path=str(path))
    patcher.executable_path = str(path)
    if not patcher.is_binary_patched(str(path)):
        patcher.patch_exe()


def prepare(browser: str, *, folder: Path | None = None, sign: bool = True) -> tuple[bool, str]:
    """Make sure ``uc_driver`` in SeleniumBase's folder is an Apple-silicon one this Mac will run. Returns (ready, what happened).

    It is checked on every run, because a browser that updated itself needs a driver of its new version: the one in place is then
    replaced (SeleniumBase alone would fetch the Intel build again)."""
    folder = folder or driver_dir(browser)
    if folder is None:
        return False, "SeleniumBase is not installed"
    target = folder / "uc_driver"
    want = major(_says([browser, "--version"]) or "")
    if want and _fits(target, want):
        return True, "the Apple-silicon driver is already in place"
    places = (folder / "chromedriver", folder.parent / "chromedriver")
    source = next((p for p in places if _fits(p, want)), None)
    if source is None:
        try:
            _download(want)
        except (Exception, SystemExit) as exc:  # noqa: BLE001 - the installer raises many things (and exits); none may stop the fetcher from reporting
            return False, f"could not get an Apple-silicon ChromeDriver ({type(exc).__name__})"
        source = next((p for p in places if _fits(p, want)), None)
        if source is None:
            if any(is_arm64_binary(p) for p in places):
                return False, f"the ChromeDriver beside SeleniumBase is not for this browser (version {want})"
            return False, "no Apple-silicon ChromeDriver was found beside SeleniumBase"
    staged = target.with_name("uc_driver.arm64")
    try:
        shutil.copy2(source, staged)
        _patch(staged)
        if sign and _says(["/usr/bin/codesign", "--force", "--sign", "-", str(staged)]) is None:
            staged.unlink(missing_ok=True)
            return False, "the edited driver could not be signed again (codesign failed)"
        if sign and _says([str(staged), "--version"]) is None:
            staged.unlink(missing_ok=True)
            return False, "the edited driver does not start on this Mac"
        if target.exists() and not is_arm64_binary(target):
            shutil.move(target, target.with_name("uc_driver.intel"))   # kept, in case Rosetta is installed later and this folder is cleaned
        shutil.move(staged, target)
    except Exception as exc:  # noqa: BLE001 - whatever goes wrong, the folder is left as it was and the reason is returned
        staged.unlink(missing_ok=True)
        return False, f"could not prepare the driver ({type(exc).__name__}: {exc})"
    return True, f"prepared an Apple-silicon driver for browser version {want or 'unknown'} (this Mac has no Rosetta)"


def problem(browser: str) -> str | None:
    """Why the event fetcher cannot drive this browser on this Mac, known before any run; None when it can (or when it is not this
    module's business: any computer that is not an Apple-silicon Mac without Rosetta)."""
    if not needs_native_driver():
        return None
    ready, what = prepare(browser)
    return None if ready else what
