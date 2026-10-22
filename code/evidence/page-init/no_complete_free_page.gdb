set pagination off
set confirm off
set tcp connect-timeout 5
file /home/ctf/os/实验二/lab2/lab2_new/bin/kernel
target remote 127.0.0.1:48225
break pmm_init
continue
set variable memory_base = 0x80000000
set variable memory_size = 0x20f000
set $memmap_calls = 0
break *best_fit_init_memmap
commands
silent
set $memmap_calls = $memmap_calls + 1
continue
end
break pmm.c:121
continue
printf "INIT_RETURN: npage=%#lx nr_free=%u calls=%d\n", npage, 'best_fit_pmm.c'::free_area.nr_free, $memmap_calls
disconnect
quit
