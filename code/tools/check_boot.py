#!/usr/bin/env python3
"""Build and boot both PMMs with multiple RAM sizes; restore Best-Fit at exit."""
import concurrent.futures
import json
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / 'evidence'
OUT.mkdir(exist_ok=True)
version = subprocess.check_output(['qemu-system-riscv64', '--version'], text=True).splitlines()[0]
assert version == 'QEMU emulator version 4.1.1', version

def build(variant):
    result = subprocess.run(['make', '-j8', f'PMM={variant}'], cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    (OUT / f'build-{variant}.log').write_text(result.stdout)
    assert result.returncode == 0, result.stdout

def boot(variant, ram):
    qemu = subprocess.Popen(['qemu-system-riscv64', '-machine', 'virt',
        '-nographic', '-bios', 'default', '-m', str(ram), '-device',
        f'loader,file={ROOT}/bin/ucore.img,addr=0x80200000'],
        cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        data, _ = qemu.communicate(timeout=2)
    except subprocess.TimeoutExpired:
        # The teaching kernel intentionally spins after its checks.
        qemu.terminate()
        data, _ = qemu.communicate(timeout=5)
    text = data.decode(errors='replace')
    (OUT / f'qemu-{variant}-{ram}M.log').write_text(text)
    manager = 'best_fit_pmm_manager' if variant == 'best-fit' else 'buddy_pmm_manager'
    required = [f'memory management: {manager}', 'check_alloc_page() succeeded!',
        'buddy_check() succeeded!', 'slub_check() succeeded!', 'mmu_probe() succeeded!']
    assert all(message in text for message in required) and 'panic' not in text, text
    return {'pmm': variant, 'ram_mib': ram, 'result': 'PASS',
            'idle_kernel_terminated_by_test': True}

results = []
try:
    for variant in ('best-fit', 'buddy'):
        build(variant)
        with concurrent.futures.ThreadPoolExecutor(3) as pool:
            results.extend(pool.map(lambda ram: boot(variant, ram), [64, 128, 256]))
finally:
    build('best-fit')
(OUT / 'boot-tests.json').write_text(json.dumps(results, indent=2) + '\n')
for result in results:
    print(f"{result['pmm']} {result['ram_mib']} MiB: {result['result']}")
