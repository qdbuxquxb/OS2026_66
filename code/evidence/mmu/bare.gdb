set pagination off
set confirm off
handle SIGPIPE nostop noprint pass
break get_physical_address if addr == 0x80200000 && mmu_idx == 1 && access_type == 2
run
set $pa_ptr = physical
printf "BARE: addr=%#lx satp=%#lx mmu_idx=%d\n", addr, env->satp, mmu_idx
bt 6
finish
printf "BARE_PA=%#lx\n", *$pa_ptr
tbreak tlb_set_page
continue
printf "BARE_TLB_FILL: va=%#lx pa=%#lx mmu_idx=%d\n", vaddr, paddr, mmu_idx
bt 4
kill
quit
