#!/usr/bin/env python3
"""Reproduce Lab2's two-GDB MMU experiment and save raw debugger evidence."""
import argparse
import json
import os
import pathlib
import re
import socket
import subprocess

import pexpect

ROOT = pathlib.Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--qemu', default=os.environ.get('QEMU_DEBUG'),
                    help='Path to a QEMU 4.1.1 debug build (or set QEMU_DEBUG).')
parser.add_argument('--out', type=pathlib.Path, default=ROOT / 'evidence/mmu')
args = parser.parse_args()
if not args.qemu:
    parser.error('specify --qemu PATH or set QEMU_DEBUG to a QEMU 4.1.1 debug build')
args.out.mkdir(parents=True, exist_ok=True)
symbols = {}
for line in subprocess.check_output(['riscv64-unknown-elf-nm', str(ROOT / 'bin/kernel')], text=True).splitlines():
    fields = line.split()
    if len(fields) == 3:
        symbols[fields[2]] = int(fields[0], 16)
watch = symbols['mmu_debug_word']
with socket.socket() as sock:
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]

def command(gdb, text):
    gdb.sendline(text)
    gdb.expect_exact('(gdb) ')
    result = gdb.before
    if re.search(r'(No symbol|Cannot access|Error in|No registers|not being run|There is no member|Attempt to extract)', result):
        raise RuntimeError(result)
    return result

# A host GDB owns QEMU as its child, so ptrace_scope=1 requires no sudo/attach.
host_log = (args.out / 'host-gdb.log').open('w')
guest_log = (args.out / 'guest-gdb.log').open('w')
host = guest = None
try:
    host = pexpect.spawn('gdb', ['-q', '-nx', '--args', args.qemu,
        '-machine', 'virt', '-nographic', '-bios', 'default',
        '-device', f'loader,file={ROOT}/bin/ucore.img,addr=0x80200000',
        '-S', '-gdb', f'tcp:127.0.0.1:{port}',
        '-serial', f'file:{args.out}/qemu.log', '-monitor', 'none'],
        encoding='utf-8', codec_errors='replace', echo=False, timeout=30)
    host.logfile = host_log
    host.expect_exact('(gdb) ')
    config = args.out / 'host-setup.gdb'
    config.write_text(f'''set editing off
set pagination off
set confirm off
handle SIGPIPE nostop noprint pass
set $slow_calls = 0
set $fill_calls = 0
break helper_le_ldq_mmu
commands
silent
set $slow_calls = $slow_calls + 1
printf "DATA LOAD SLOW PATH: addr=%#lx calls=%d\\n", addr, $slow_calls
bt 5
continue
end
break riscv_cpu_tlb_fill if address == {watch:#x} && access_type == 0
disable 1 2
''')
    command(host, f'source {config}')
    host.sendline('run')
    host.expect('Continuing|Starting program:')
    guest = pexpect.spawn('riscv64-unknown-elf-gdb', ['-q', '-nx', str(ROOT / 'bin/kernel')],
                          encoding='utf-8', codec_errors='replace', echo=False, timeout=30)
    guest.logfile = guest_log
    guest.expect_exact('(gdb) ')
    command(guest, 'set editing off')
    command(guest, 'set pagination off')
    command(guest, 'set confirm off')
    command(guest, f'target remote 127.0.0.1:{port}')
    command(guest, 'break *mmu_load_first')
    command(guest, 'continue')
    command(guest, 'p/x $pc')
    command(guest, 'p/x $a0')
    command(guest, 'p/x $satp')
    command(guest, 'x/3i $pc')
    host.sendcontrol('c')
    host.expect_exact('(gdb) ')
    command(host, 'enable 1 2')
    host.sendline('continue')
    # The guest step blocks until the host debugger resumes QEMU.
    guest.sendline('si')
    host.expect_exact('(gdb) ')
    command(host, 'set $fill_calls = $fill_calls + 1')
    command(host, 'set $rv_env = &((RISCVCPU *)cs)->env')
    command(host, 'set $rv_cpu = (RISCVCPU *)cs')
    command(host, 'bt 8')
    command(host, f'break get_physical_address if addr == {watch:#x} && access_type == 0')
    command(host, 'continue')
    command(host, 'set $pa_ptr = physical')
    command(host, 'p/x env->satp')
    command(host, 'p mmu_idx')
    command(host, f'tbreak cpu_helper.c:254 if addr == {watch:#x} && access_type == 0')
    command(host, 'continue')
    walk_text = command(host, 'printf "WALK: levels=%d i=%d shift=%d idx=%#lx base=%#lx pte_addr=%#lx pte=%#lx\\n", levels, i, ptshift, idx, base, pte_addr, pte')
    command(host, 'next')
    command(host, 'p/x ppn')
    command(host, 'finish')
    pa_text = command(host, 'printf "TRANSLATED PA=%#lx\\n", *$pa_ptr')
    command(host, 'disable 3')
    count_config = args.out / 'count-fills.gdb'
    count_config.write_text('''commands 2
silent
set $fill_calls = $fill_calls + 1
printf "ADDITIONAL TLB FILL: count=%d\\n", $fill_calls
continue
end
''')
    command(host, f'source {count_config}')
    host.sendline('continue')
    guest.expect_exact('(gdb) ')
    command(guest, 'p/x $pc')
    command(guest, 'p/x $t0')

    # QEMU's guest is stopped in its GDB stub; inspect the soft TLB from the host.
    host.sendcontrol('c')
    host.expect_exact('(gdb) ')
    command(host, f'set $watch = {watch:#x}')
    command(host, 'set $index = ($watch >> 12) & ($rv_cpu->neg.tlb.f[1].mask >> 5)')
    command(host, 'set $entry = &$rv_cpu->neg.tlb.f[1].table[$index]')
    tlb_text = command(host, 'printf "TLB: index=%lu addr_read=%#lx addend=%#lx host_address=%#lx\\n", $index, $entry->addr_read, $entry->addend, $watch + $entry->addend')
    command(host, 'x/gx ($watch + $entry->addend)')
    before = command(host, 'printf "BEFORE SECOND LOAD: slow=%d fill=%d\\n", $slow_calls, $fill_calls')
    host.sendline('continue')
    command(guest, 'si')
    value_text = command(guest, 'p/x $a0')
    command(guest, 'p/x $pc')
    host.sendcontrol('c')
    host.expect_exact('(gdb) ')
    after = command(host, 'printf "AFTER SECOND LOAD: slow=%d fill=%d\\n", $slow_calls, $fill_calls')
    assert 'slow=1 fill=1' in before and 'slow=1 fill=1' in after
    assert '0x24141322411185' in value_text
    pa = int(re.search(r'TRANSLATED PA=(0x[0-9a-f]+)', pa_text).group(1), 16)
    physical_byte = pa | (watch & 0xfff)
    assert physical_byte == (watch - 0xffffffff40000000) & ((1 << 64) - 1)
    assert 'levels=3 i=0 shift=18 idx=0x1ff' in walk_text
    pte = int(re.search(r'pte=(0x[0-9a-f]+)', walk_text).group(1), 16)
    tag = int(re.search(r'addr_read=(0x[0-9a-f]+)', tlb_text).group(1), 16)
    assert pte == 0x200000cf and tag == (watch & ~0xfff)
    result = {'virtual_address': hex(watch), 'physical_page_base': hex(pa),
              'physical_address': hex(physical_byte),
              'pte': hex(pte), 'soft_tlb_read_tag': hex(tag), 'leaf_size': '1 GiB',
              'slow_load_calls_after_two_loads': 1, 'tlb_fills_after_two_loads': 1,
              'loaded_value': '0x24141322411185', 'two_gdb': 'PASS'}
    (args.out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
finally:
    if guest is not None:
        guest.close(force=True)
    if host is not None:
        host.close(force=True)
    host_log.close()
    guest_log.close()

# Control run before paging: the same soft TLB is filled even in Bare mode.
bare_config = args.out / 'bare.gdb'
bare_config.write_text('''set pagination off
set confirm off
handle SIGPIPE nostop noprint pass
break get_physical_address if addr == 0x80200000 && mmu_idx == 1 && access_type == 2
run
set $pa_ptr = physical
printf "BARE: addr=%#lx satp=%#lx mmu_idx=%d\\n", addr, env->satp, mmu_idx
bt 6
finish
printf "BARE_PA=%#lx\\n", *$pa_ptr
tbreak tlb_set_page
continue
printf "BARE_TLB_FILL: va=%#lx pa=%#lx mmu_idx=%d\\n", vaddr, paddr, mmu_idx
bt 4
kill
quit
''')
bare = subprocess.run(['gdb', '-q', '-nx', '-batch', '-x', str(bare_config),
    '--args', args.qemu, '-machine', 'virt', '-nographic', '-bios', 'default',
    '-device', f'loader,file={ROOT}/bin/ucore.img,addr=0x80200000',
    '-serial', f'file:{args.out}/bare-qemu.log', '-monitor', 'none'],
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=45)
(args.out / 'bare-host-gdb.log').write_text(bare.stdout)
assert bare.returncode == 0, bare.stdout
assert 'BARE: addr=0x80200000 satp=0 mmu_idx=1' in bare.stdout, bare.stdout
assert 'BARE_PA=0x80200000' in bare.stdout, bare.stdout
assert 'BARE_TLB_FILL: va=0x80200000 pa=0x80200000 mmu_idx=1' in bare.stdout, bare.stdout
result['bare_identity_translation_and_soft_tlb'] = 'PASS'
(args.out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
print('Bare-mode identity translation and soft TLB: PASS')
