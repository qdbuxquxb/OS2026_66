set editing off
set pagination off
set confirm off
handle SIGPIPE nostop noprint pass
set $slow_calls = 0
set $fill_calls = 0
break helper_le_ldq_mmu
commands
silent
set $slow_calls = $slow_calls + 1
printf "DATA LOAD SLOW PATH: addr=%#lx calls=%d\n", addr, $slow_calls
bt 5
continue
end
break riscv_cpu_tlb_fill if address == 0xffffffffc0208010 && access_type == 0
disable 1 2
