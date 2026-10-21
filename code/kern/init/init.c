#include <console.h>
#include <defs.h>
#include <pmm.h>
#include <stdio.h>
#include <string.h>
#include <dtb.h>

int kern_init(void) __attribute__((noreturn));
void grade_backtrace(void);
void print_kerninfo(void);

// lab2 MMU debug probe 2411963
uint64_t mmu_debug_word = 0x24141322411185UL;
extern uint64_t mmu_debug_load(const volatile uint64_t *address);

/* *
 * print_kerninfo - print the information about kernel, including the location
 * of kernel entry, the start addresses of data and text segements, the start
 * address of free memory and how many memory that kernel has used.
 * */
void print_kerninfo(void) {
    extern char etext[], edata[], end[];
    cprintf("Special kernel symbols:\n");
    cprintf("  entry  0x%016lx (virtual)\n", (uintptr_t)kern_init);
    cprintf("  etext  0x%016lx (virtual)\n", etext);
    cprintf("  edata  0x%016lx (virtual)\n", edata);
    cprintf("  end    0x%016lx (virtual)\n", end);
    cprintf("Kernel executable memory footprint: %dKB\n",
            (end - (char*)kern_init + 1023) / 1024);
}

int kern_init(void) {
    extern char edata[], end[];
    memset(edata, 0, end - edata);
    dtb_init();
    cons_init();  // init the console
    const char *message = "(THU.CST) os is loading ...\0";
    //cprintf("%s\n\n", message);
    cputs(message);

    print_kerninfo();

    // grade_backtrace();
    pmm_init();  // init physical memory management

    assert(mmu_debug_load(&mmu_debug_word) == mmu_debug_word);
    cprintf("mmu_probe() succeeded!\n");

    /* do nothing */
    while (1)
        ;
}

