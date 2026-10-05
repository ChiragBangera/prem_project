"""Output on a platform whose default text encoding cannot hold every name (Windows, when output is piped or redirected)."""

from __future__ import annotations

import os
import subprocess
import sys


def test_a_name_that_the_default_encoding_cannot_hold_does_not_stop_a_command(tmp_path):
    code = "from app import cli; cli._utf8_output(); print('Luka Milović, Hägdahl, Ødegaard')"
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, timeout=60, env={**os.environ, "PREM_DATA_DIR": str(tmp_path), "PYTHONIOENCODING": "cp1252", "PYTHONUTF8": "0"})
    assert done.returncode == 0, done.stderr.decode(errors="replace")
    assert done.stdout.decode("utf-8").strip() == "Luka Milović, Hägdahl, Ødegaard"
