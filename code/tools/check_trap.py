#!/usr/bin/env python3
"""Lab4 Trap/clock probe.

The official `make grade` does not trigger traps, so this script copies the
project to a temporary directory, injects a short probe at the start of
init_main, builds it, runs QEMU, and writes the raw log to
code/evidence/trap-probe.log. The working tree is never modified.

Run from code/ with QEMU 4.1.1 and the RISC-V toolchain in PATH.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence"
LOG = EVIDENCE / "trap-probe.log"

PROBE = '''    extern volatile size_t ticks;
    cprintf("PROBE before ebreak\\n");
    asm volatile("ebreak");
    cprintf("PROBE after ebreak\\n");
    cprintf("PROBE before illegal16\\n");
    asm volatile(".word 0x00000000");
    cprintf("PROBE after illegal16\\n");
    cprintf("PROBE before illegal32\\n");
    asm volatile(".word 0x0000007b");
    cprintf("PROBE after illegal32\\n");
    while (ticks < 105) { }
    cprintf("PROBE timer ticks=%d\\n", (int)ticks);
'''


def main() -> int:
    EVIDENCE.mkdir(exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="lab4-trap-"))
    src = tmp / "src"
    try:
        shutil.copytree(
            ROOT,
            src,
            ignore=shutil.ignore_patterns("obj", "bin", "evidence", ".git", ".notes"),
        )
        proc = src / "kern/process/proc.c"
        text = proc.read_text(encoding="utf-8")
        marker = "init_main(void *arg)\n{\n"
        if marker not in text:
            print("ERROR: init_main pattern not found", file=sys.stderr)
            return 1
        text = text.replace(marker, marker + PROBE, 1)
        proc.write_text(text, encoding="utf-8")

        build = subprocess.run(
            ["make"], cwd=src, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        if build.returncode != 0:
            print(build.stdout)
            print("ERROR: build failed", file=sys.stderr)
            return 1

        command = [
            "qemu-system-riscv64", "-machine", "virt", "-nographic",
            "-bios", "default", "-device",
            "loader,file=bin/ucore.img,addr=0x80200000",
        ]
        try:
            run = subprocess.run(
                command, cwd=src, text=True, timeout=30,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            )
            output = run.stdout
        except subprocess.TimeoutExpired as exc:
            output = (exc.stdout or "")
            if isinstance(output, bytes):
                output = output.decode("utf-8", "replace")

        LOG.write_text(output, encoding="utf-8")
        print(output)
        required = [
            "PROBE after ebreak",
            "Illegal instruction at",
            "PROBE after illegal16",
            "PROBE after illegal32",
            "PROBE timer ticks=105",
        ]
        missing = [item for item in required if item not in output]
        if missing:
            print("ERROR: missing markers: " + ", ".join(missing), file=sys.stderr)
            return 1
        print("Trap probe passed; log: " + str(LOG))
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
