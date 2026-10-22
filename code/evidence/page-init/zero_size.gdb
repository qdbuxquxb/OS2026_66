set pagination off
set confirm off
set tcp connect-timeout 5
file /home/ctf/os/实验二/lab2/lab2_new/bin/kernel
target remote 127.0.0.1:35003
break pmm_init
continue
set variable memory_base = 0x80000000
set variable memory_size = 0x0
set $memmap_calls = 0
break *best_fit_init_memmap
commands
silent
set $memmap_calls = $memmap_calls + 1
continue
end
break __panic
continue
printf "PANIC=%s\n", fmt
printf "MEMMAP_CALLS=%d\n", $memmap_calls
disconnect
quit
