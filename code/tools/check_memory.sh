#!/bin/sh
# Lab4: boot the kernel with 64/128/256 MiB and print the key lines.
# Run from code/ after `source ~/OS/env.sh` (QEMU 4.1.1 must be in PATH).

set -u

if [ ! -f bin/ucore.img ]; then
    echo "building kernel..." >&2
    make >/dev/null 2>&1 || { make; exit 1; }
fi

for m in 64M 128M 256M; do
    echo "===== QEMU -m $m ====="
    tmp=$(mktemp)
    timeout 15 qemu-system-riscv64 \
        -machine virt -m "$m" -bios default \
        -device loader,file=bin/ucore.img,addr=0x80200000 \
        -display none -monitor none -serial "file:$tmp" >/dev/null 2>&1 || true
    if [ ! -s "$tmp" ]; then
        echo "no serial output captured; qemu version:" >&2
        qemu-system-riscv64 --version >&2 || true
    else
        grep -E "Size:|memory management|check_alloc_page|check_pgdir|check_vmm|this initproc|To U:" "$tmp"
    fi
    rm -f "$tmp"
    echo
done
