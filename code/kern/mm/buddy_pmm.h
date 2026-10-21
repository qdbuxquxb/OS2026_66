#ifndef __KERN_MM_BUDDY_PMM_H__
#define __KERN_MM_BUDDY_PMM_H__
#include <pmm.h>
extern const struct pmm_manager buddy_pmm_manager;
/* Run with a temporary pool, then restore the active page manager. */
void buddy_check(void);
#endif
