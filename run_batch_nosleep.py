"""Windows sleep-prevention wrapper around run_with_training.py."""
from __future__ import annotations
import ctypes
import runpy
import sys

ES_CONTINUOUS       = 0x80000000
ES_SYSTEM_REQUIRED  = 0x00000001
ES_AWAYMODE_REQUIRED = 0x00000040


def _keep_awake(on: bool) -> None:
    if sys.platform != "win32":
        return
    flags = ES_CONTINUOUS
    if on:
        flags |= ES_SYSTEM_REQUIRED | ES_AWAYMODE_REQUIRED
    ctypes.windll.kernel32.SetThreadExecutionState(flags)


def main() -> int:
    _keep_awake(True)
    try:
        sys.argv = ["run_with_training.py"] + sys.argv[1:]
        runpy.run_path("run_with_training.py", run_name="__main__")
    finally:
        _keep_awake(False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
