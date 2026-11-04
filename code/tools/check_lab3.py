#!/usr/bin/env python3
"""Supplement official Lab3 grading in a disposable source copy, using QEMU 4.1.1.

Checks all integer registers across 16/32-bit breakpoint/illegal exceptions
and a real timer interrupt; also checks interrupt guards and normal shutdown.
Does not modify the working kernel or the supplied grading tools.
"""
import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--qemu', default='/opt/os-lab/qemu-4.1.1/bin/qemu-system-riscv64')
parser.add_argument('--out', type=Path, default=ROOT / 'evidence' / 'supplemental')
args = parser.parse_args()
args.out = args.out.resolve()
args.out.mkdir(parents=True, exist_ok=True)
version = subprocess.check_output([args.qemu, '--version'], text=True).splitlines()[0]
if version != 'QEMU emulator version 4.1.1':
    raise SystemExit('Expected QEMU 4.1.1: ' + version)

CASES = {
    'break16': '.2byte 0x9002',
    'break32': '.4byte 0x00100073',
    'illegal16': '.2byte 0x0000',
    'illegal32': '.4byte 0x0000007b',
    'timer': 'wfi',
}

def assembly():
    lines = ['.text', '.option push', '.option norvc']
    for name, instruction in CASES.items():
        lines += ['.balign 4', '.globl probe_' + name, 'probe_' + name + ':',
                  'addi sp, sp, -544']
        for i in range(1, 32):
            if i != 2:
                lines.append(f'sd x{i}, {i * 8}(sp)')
        # Expected values for registers intentionally left unchanged.
        for i in (1, 2, 3, 4):
            lines.append(f'sd x{i}, {(32 + i) * 8}(a0)')
        for i in range(5, 32):
            lines.append(f'li x{i}, {0x100 + i}')
        lines.append(instruction)
        # Snapshot every register before using any scratch register.
        for i in range(32):
            lines.append(f'sd x{i}, {256 + i * 8}(sp)')
        lines += ['ld t0, 80(sp)', 'addi t1, sp, 256', 'li t2, 32',
                  '1:', 'ld t3, 0(t1)', 'sd t3, 0(t0)',
                  'addi t0, t0, 8', 'addi t1, t1, 8',
                  'addi t2, t2, -1', 'bnez t2, 1b']
        for i in range(1, 32):
            if i != 2:
                lines.append(f'ld x{i}, {i * 8}(sp)')
        lines += ['addi sp, sp, 544', 'ret']
    return '\n'.join(lines + ['.option pop', ''])

C_SOURCE = r"""
#include <assert.h>
#include <clock.h>
#include <intr.h>
#include <pmm.h>
#include <riscv.h>
#include <stdio.h>
#include <../sync/sync.h>
void probe_break16(uintptr_t *);
void probe_break32(uintptr_t *);
void probe_illegal16(uintptr_t *);
void probe_illegal32(uintptr_t *);
void probe_timer(uintptr_t *);
static void check_probe(void (*probe)(uintptr_t *), const char *name) {
    uintptr_t values[64];
    for (size_t i = 0; i < 64; ++i) { values[i] = 0; }
    for (size_t i = 5; i < 32; ++i) { values[32 + i] = 0x100 + i; }
    uintptr_t enabled = read_csr(sstatus) & SSTATUS_SIE;
    probe(values);
    for (size_t i = 0; i < 32; ++i) {
        if (values[i] != values[32 + i]) {
            cprintf("SUPPLEMENT FAIL %s x%lu: %lx != %lx\n",
                    name, i, values[i], values[32 + i]);
            panic("register mismatch");
        }
    }
    assert((read_csr(sstatus) & SSTATUS_SIE) == enabled);
    assert(read_csr(sscratch) == 0);
    cprintf("SUPPLEMENT PASS %s: all 32 GPRs, SP, interrupt state\n", name);
}
void supplement_exceptions(void) {
    check_probe(probe_break16, "break16");
    check_probe(probe_break32, "break32");
    check_probe(probe_illegal16, "illegal16");
    check_probe(probe_illegal32, "illegal32");
}
void supplement_timer(void) {
    size_t before = ticks;
    check_probe(probe_timer, "timer");
    assert(ticks > before);
    for (int enabled = 0; enabled <= 1; ++enabled) {
        if (enabled) { intr_enable(); } else { intr_disable(); }
        size_t free_before = nr_free_pages();
        struct Page *page = alloc_page();
        assert(page != NULL);
        assert(!!(read_csr(sstatus) & SSTATUS_SIE) == enabled);
        free_page(page);
        assert(nr_free_pages() == free_before);
        assert(!!(read_csr(sstatus) & SSTATUS_SIE) == enabled);
        bool outer, inner;
        local_intr_save(outer);
        local_intr_save(inner);
        local_intr_restore(inner);
        assert(!(read_csr(sstatus) & SSTATUS_SIE));
        local_intr_restore(outer);
        assert(!!(read_csr(sstatus) & SSTATUS_SIE) == enabled);
    }
    intr_enable();
    cprintf("SUPPLEMENT PASS interrupt guards and free-page conservation\n");
}
"""

with tempfile.TemporaryDirectory(prefix='lab3_supplement_') as tmp:
    work = Path(tmp) / 'code'
    shutil.copytree(ROOT, work, ignore=shutil.ignore_patterns(
        'bin', 'obj', 'evidence', '.git', '__pycache__'))
    (work / 'kern/init/supplement_context.S').write_text(assembly())
    (work / 'kern/init/supplement.c').write_text(C_SOURCE)
    init = work / 'kern/init/init.c'
    text = init.read_text()
    text = 'void supplement_exceptions(void);\nvoid supplement_timer(void);\n' + text
    pos = text.rindex('idt_init();') + len('idt_init();')
    text = text[:pos] + '\n    supplement_exceptions();' + text[pos:]
    text = text.replace('intr_enable();', 'intr_enable();\n    supplement_timer();', 1)
    init.write_text(text)
    with (args.out / 'build.log').open('w') as log:
        subprocess.run(['make', '-j8'], cwd=work, stdout=log,
                       stderr=subprocess.STDOUT, check=True)
    result = subprocess.run([args.qemu, '-machine', 'virt', '-nographic',
        '-bios', 'default', '-device', 'loader,file=bin/ucore.img,addr=0x80200000',
        '-monitor', 'none', '-no-reboot'], cwd=work, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, timeout=25)
    output = result.stdout.decode(errors='replace')
    (args.out / 'qemu.log').write_text(output)
    for name in CASES:
        assert 'SUPPLEMENT PASS ' + name + ':' in output, output
    assert 'SUPPLEMENT PASS interrupt guards' in output, output
    assert 'SUPPLEMENT FAIL' not in output and 'panic' not in output.lower(), output
    assert output.splitlines().count('100 ticks') == 10, output
    assert result.returncode == 0, result.returncode
    summary = {'qemu': version, 'cases': list(CASES), 'all_32_gprs': 'PASS',
               'interrupt_guards': 'PASS', 'reports_before_shutdown': 10,
               'normal_shutdown_exit_code': result.returncode, 'result': 'PASS'}
    (args.out / 'result.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))
