"""Small, allowlisted process/cgroup metrics; never request, invoice or environment values."""

import os
from pathlib import Path


def memory_snapshot(processes=(), *, cgroup=Path("/sys/fs/cgroup"), proc=Path("/proc")):
    values = {}
    for filename, key in [
        ("memory.current", "memory_bytes"),
        ("memory.peak", "memory_peak_bytes"),
        ("memory.max", "memory_limit_bytes"),
    ]:
        try:
            raw = (cgroup / filename).read_text().strip()
            if raw.isdecimal():
                values[key] = int(raw)
        except OSError:
            pass
    try:
        for line in (cgroup / "memory.events").read_text().splitlines():
            key, raw = line.split()
            if key in {"oom", "oom_kill", "max", "high"} and raw.isdecimal():
                values["memory_event_" + key] = int(raw)
    except (OSError, ValueError):
        pass
    for role, pid in [("supervisor", os.getpid()), *processes]:
        if role not in {"supervisor", "web", "worker"}:
            continue
        try:
            for line in (proc / str(pid) / "status").read_text().splitlines():
                if line.startswith("VmRSS:"):
                    raw = line.split()[1]
                    if raw.isdecimal():
                        values[role + "_rss_bytes"] = int(raw) * 1024
                    break
        except (OSError, IndexError):
            pass
    return values
