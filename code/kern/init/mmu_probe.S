/* lab2 MMU debug probe 2411963
 * Two real loads from the same VA after a fence: miss, then hit.
 * These labels give the two GDB sessions stable instruction boundaries.
 */
.section .text
.globl mmu_debug_load
.type mmu_debug_load, @function
mmu_debug_load:
    sfence.vma
.globl mmu_load_first
mmu_load_first:
    ld t0, 0(a0)
.globl mmu_load_second
mmu_load_second:
    ld a0, 0(a0)
.globl mmu_load_done
mmu_load_done:
    ret
.size mmu_debug_load, . - mmu_debug_load
