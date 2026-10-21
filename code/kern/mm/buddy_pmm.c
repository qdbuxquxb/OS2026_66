// lab2 function2-3 2414132
#include <buddy_pmm.h>
#include <stdio.h>

/* 2^15 pages cover the framework's maximum manageable 128 MiB. */
#define MAX_ORDER 15
#define BUDDY_ALLOCATED (1UL << 2)
#define BUDDY_FREE (1UL << 3)
static list_entry_t areas[MAX_ORDER + 1];
static size_t nr_free;

static unsigned int order_for(size_t n) {
    unsigned int order = 0;
    while (order < MAX_ORDER && ((size_t)1 << order) < n) {
        ++order;
    }
    return order;
}

static void buddy_init(void) {
    for (unsigned int i = 0; i <= MAX_ORDER; ++i) {
        list_init(&areas[i]);
    }
    nr_free = 0;
}

static void add_block(struct Page *base, unsigned int order) {
    size_t count = (size_t)1 << order;
    /* XOR physical page numbers, not descriptor addresses or pool offsets. */
    while (order < MAX_ORDER) {
        size_t buddy_ppn = page2ppn(base) ^ count;
        if (buddy_ppn < nbase || buddy_ppn >= npage) {
            break;
        }
        struct Page *other = &pages[buddy_ppn - nbase];
        if (!(other->flags & BUDDY_FREE) || !PageProperty(other) ||
            other->property != count) {
            break;
        }
        list_del(&other->page_link);
        ClearPageProperty(other);
        other->flags &= ~BUDDY_FREE;
        other->property = 0;
        if (other < base) {
            base = other;
        }
        count <<= 1;
        ++order;
    }
    base->property = count;
    base->flags |= BUDDY_FREE;
    SetPageProperty(base);
    list_add(&areas[order], &base->page_link);
}

static void buddy_init_memmap(struct Page *base, size_t n) {
    assert(n > 0);
    for (struct Page *p = base; p < base + n; ++p) {
        assert(PageReserved(p));
        p->flags = p->property = 0;
        set_page_ref(p, 0);
    }
    nr_free += n;
    /* Decompose arbitrary ranges without losing unaligned leading/tail pages. */
    while (n != 0) {
        unsigned int order = MAX_ORDER;
        while (((size_t)1 << order) > n ||
               (page2ppn(base) & (((size_t)1 << order) - 1)) != 0) {
            --order;
        }
        size_t count = (size_t)1 << order;
        add_block(base, order);
        base += count;
        n -= count;
    }
}

static struct Page *buddy_alloc_pages(size_t n) {
    assert(n > 0);
    if (n > nr_free || n > ((size_t)1 << MAX_ORDER)) {
        return NULL;
    }
    unsigned int want = order_for(n), order = want;
    while (order <= MAX_ORDER && list_empty(&areas[order])) {
        ++order;
    }
    if (order > MAX_ORDER) {
        return NULL;
    }
    struct Page *base = le2page(list_next(&areas[order]), page_link);
    list_del(&base->page_link);
    ClearPageProperty(base);
    base->flags &= ~BUDDY_FREE;
    while (order > want) {
        --order;
        struct Page *half = base + ((size_t)1 << order);
        half->property = (size_t)1 << order;
        half->flags |= BUDDY_FREE;
        SetPageProperty(half);
        list_add(&areas[order], &half->page_link);
    }
    size_t count = (size_t)1 << want;
    for (struct Page *p = base; p < base + count; ++p) {
        p->flags = BUDDY_ALLOCATED;
        p->property = 0;
        set_page_ref(p, 0);
    }
    base->property = count;
    nr_free -= count;
    return base;
}

static void buddy_free_pages(struct Page *base, size_t n) {
    assert(n > 0 && n <= ((size_t)1 << MAX_ORDER));
    unsigned int order = order_for(n);
    size_t count = (size_t)1 << order;
    assert(base >= pages && base + count <= pages + (npage - nbase));
    assert((page2ppn(base) & (count - 1)) == 0);
    assert(base->property == count);
    for (struct Page *p = base; p < base + count; ++p) {
        assert(p->flags == BUDDY_ALLOCATED);
        p->flags = p->property = 0;
        set_page_ref(p, 0);
    }
    nr_free += count;
    add_block(base, order);
}

static size_t buddy_nr_free_pages(void) { return nr_free; }

/* Check all free-list orders, alignment, counts, overlap and maximal merging. */
static void buddy_validate(void) {
    size_t total = 0;
    for (unsigned int order = 0; order <= MAX_ORDER; ++order) {
        size_t count = (size_t)1 << order;
        for (list_entry_t *le = list_next(&areas[order]); le != &areas[order];
             le = list_next(le)) {
            struct Page *p = le2page(le, page_link);
            assert(PageProperty(p) && p->property == count);
            assert((page2ppn(p) & (count - 1)) == 0);
            for (size_t i = 0; i < count; ++i) {
                assert(!PageReserved(p + i) && !((p + i)->flags & BUDDY_ALLOCATED));
                assert(i == 0 || !PageProperty(p + i));
            }
            size_t ppn = page2ppn(p) ^ count;
            if (order < MAX_ORDER && ppn >= nbase && ppn < npage) {
                struct Page *other = &pages[ppn - nbase];
                assert(!(other->flags & BUDDY_FREE) ||
                       !PageProperty(other) || other->property != count);
            }
            total += count;
        }
    }
    assert(total == nr_free);
}

const struct pmm_manager buddy_pmm_manager = {
    .name = "buddy_pmm_manager", .init = buddy_init,
    .init_memmap = buddy_init_memmap, .alloc_pages = buddy_alloc_pages,
    .free_pages = buddy_free_pages, .nr_free_pages = buddy_nr_free_pages,
    .check = buddy_validate,
};

// lab2 Buddy tests 2414132
void buddy_check(void) {
    const struct pmm_manager *saved = pmm_manager;
    size_t before = nr_free_pages();
    if (saved == &buddy_pmm_manager) {
        struct Page *a = alloc_pages(3), *b = alloc_pages(5), *c = alloc_page();
        assert(a && b && c && a->property == 4 && b->property == 8);
        assert(nr_free_pages() == before - 13);
        assert(a + 4 <= b || b + 8 <= a);
        assert(c < a || c >= a + 4);
        assert(c < b || c >= b + 8);
        free_pages(b, 5);
        free_page(c);
        free_pages(a, 3);
        buddy_validate();
        assert(nr_free_pages() == before);
        cprintf("buddy_check() succeeded! (live Buddy manager)\n");
        return;
    }
    struct Page *pool = alloc_pages(128);
    assert(pool != NULL);
    /* Test a complete aligned order-6 block independently of the live pool. */
    struct Page *base = pool + ((64 - (page2ppn(pool) & 63)) & 63);
    pmm_manager = &buddy_pmm_manager;
    buddy_init();
    for (size_t i = 0; i < 64; ++i) { SetPageReserved(base + i); }
    buddy_init_memmap(base, 64);
    assert(nr_free_pages() == 64);
    struct Page *a = alloc_pages(3), *b = alloc_pages(5);
    assert(a && b && a != b);
    assert(a->property == 4 && b->property == 8 && nr_free_pages() == 52);
    assert(a + 4 <= b || b + 8 <= a);
    free_pages(a, 3);
    free_pages(b, 5);
    buddy_validate();
    assert((a = alloc_pages(64)) == base && alloc_page() == NULL);
    free_pages(a, 64);
    struct Page *single[64];
    for (size_t i = 0; i < 64; ++i) {
        single[i] = alloc_page();
        assert(single[i] != NULL);
        for (size_t j = 0; j < i; ++j) { assert(single[j] != single[i]); }
    }
    assert(nr_free_pages() == 0 && alloc_page() == NULL);
    for (size_t i = 0; i < 64; i += 2) { free_page(single[i]); }
    assert(alloc_pages(2) == NULL); /* Enough pages, but no contiguous buddies. */
    for (size_t i = 1; i < 64; i += 2) { free_page(single[i]); }
    buddy_validate();
    assert((a = alloc_pages(64)) == base);
    free_pages(a, 64);

    /* Reinitialize with an unaligned, non-power-of-two 93-page pool. */
    buddy_init();
    for (size_t i = 0; i < 128; ++i) {
        pool[i].flags = pool[i].property = 0;
        set_page_ref(pool + i, 0);
    }
    for (size_t i = 1; i < 94; ++i) { SetPageReserved(pool + i); }
    buddy_init_memmap(pool + 1, 93);
    buddy_validate();
    assert(alloc_pages(94) == NULL && alloc_pages((size_t)-1) == NULL);
    struct Page *all[93];
    for (size_t i = 0; i < 93; ++i) {
        all[i] = alloc_page();
        assert(all[i] >= pool + 1 && all[i] < pool + 94);
        for (size_t j = 0; j < i; ++j) { assert(all[j] != all[i]); }
    }
    assert(alloc_page() == NULL);
    for (size_t i = 93; i > 0; --i) { free_page(all[i - 1]); }
    buddy_validate();
    assert(nr_free_pages() == 93);
    for (size_t i = 0; i < 128; ++i) { pool[i].flags = pool[i].property = 0; }
    pmm_manager = saved;
    free_pages(pool, 128);
    assert(nr_free_pages() == before);
    cprintf("buddy_check() succeeded! (rounding, split, merge, exhaustion, unaligned range)\n");
}
