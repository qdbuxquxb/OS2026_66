#!/usr/bin/env python3
"""Exercise page_init boundary cases by injecting DTB results through GDB."""
import json
import pathlib
import re
import socket
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / 'evidence/page-init'
OUT.mkdir(parents=True, exist_ok=True)
nm = subprocess.check_output(['riscv64-unknown-elf-nm', str(ROOT / 'bin/kernel')], text=True)
end = int(re.search(r'^([0-9a-f]+) . end$', nm, re.M).group(1), 16)
desc_pa = ((end - 0xffffffff40000000 + 4095) // 4096) * 4096
zero_free_end = desc_pa
while zero_free_end < desc_pa + ((zero_free_end - 0x80000000) // 4096) * 40:
    zero_free_end += 4096
check_line = next(i for i, s in enumerate((ROOT / 'kern/mm/pmm.c').read_text().splitlines(), 1)
                  if s.strip() == 'check_alloc_page();')
cases = [
    ('zero_size', 0x80000000, 0, 'invalid physical memory range'),
    ('overflow', 0x80000000, 0xffffffffffffffff, 'invalid physical memory range'),
    ('wrong_base', 0x80001000, 0x8000000, 'invalid physical memory range'),
    ('descriptors_do_not_fit', 0x80000000, 0x100000, 'not enough memory'),
    ('no_complete_free_page', 0x80000000, zero_free_end - 0x80000000, None),
    ('partial_tail_page', 0x80000000, zero_free_end - 0x80000000 + 123, None),
    ('clamped_upper_bound', 0x80000000, 0x10000000, None),
]
results = []
for name, base, size, panic in cases:
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    with (OUT / f'{name}-qemu.log').open('w') as qlog:
        qemu = subprocess.Popen(['qemu-system-riscv64', '-machine', 'virt',
            '-nographic', '-bios', 'default', '-device',
            f'loader,file={ROOT}/bin/ucore.img,addr=0x80200000',
            '-S', '-gdb', f'tcp:127.0.0.1:{port}'], stdout=qlog, stderr=subprocess.STDOUT)
        try:
            script = OUT / f'{name}.gdb'
            stop = '__panic' if panic else f'pmm.c:{check_line}'
            commands = f'''set pagination off
set confirm off
set tcp connect-timeout 5
file {ROOT}/bin/kernel
target remote 127.0.0.1:{port}
break pmm_init
continue
set variable memory_base = {base:#x}
set variable memory_size = {size:#x}
set $memmap_calls = 0
break *best_fit_init_memmap
commands
silent
set $memmap_calls = $memmap_calls + 1
continue
end
break {stop}
continue
'''
            if panic:
                commands += 'printf "PANIC=%s\\n", fmt\nprintf "MEMMAP_CALLS=%d\\n", $memmap_calls\n'
            else:
                commands += '''printf "INIT_RETURN: npage=%#lx nr_free=%u calls=%d\\n", npage, 'best_fit_pmm.c'::free_area.nr_free, $memmap_calls
'''
            commands += 'disconnect\nquit\n'
            script.write_text(commands)
            result = subprocess.run(['riscv64-unknown-elf-gdb', '-q', '-nx', '-batch', '-x', str(script)],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=15)
            (OUT / f'{name}-gdb.log').write_text(result.stdout)
            assert result.returncode == 0, result.stdout
            if panic:
                assert f'PANIC={panic}' in result.stdout and 'MEMMAP_CALLS=0' in result.stdout, result.stdout
            else:
                match = re.search(r'INIT_RETURN: npage=(0x[0-9a-f]+) nr_free=(\d+) calls=(\d+)', result.stdout)
                assert match, result.stdout
                npage, free, calls = int(match[1], 16), int(match[2]), int(match[3])
                if name == 'clamped_upper_bound':
                    assert npage == 0x88000 and free > 0 and calls == 1
                else:
                    assert npage == zero_free_end // 4096 and free == 0 and calls == 0
            results.append({'case': name, 'result': 'PASS'})
            print(name + ': PASS')
        finally:
            qemu.terminate()
            qemu.wait(timeout=5)
(OUT / 'result.json').write_text(json.dumps(results, indent=2) + '\n')
