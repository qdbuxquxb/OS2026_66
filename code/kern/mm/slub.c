// lab2 SLUB Challenge 2411185
#include <slub.h>
#include <pmm.h>
#include <stdio.h>
#include <string.h>

#define CACHE_COUNT 8
#define SLAB_MAGIC 0x534c5542534d414cUL
#define LARGE_MAGIC 0x534c55424c415247UL
struct slab {
    uint64_t magic;
    unsigned int cache, capacity, inuse;
    void *freelist;
    list_entry_t link;
    uint64_t used[4];
};
struct large_header { uint64_t magic; size_t npages; };
static struct {
    size_t size;
    list_entry_t partial, full;
} caches[CACHE_COUNT];

static size_t object_offset(void) { return ROUNDUP(sizeof(struct slab), 16); }

void slub_init(void) {
    for (size_t i = 0; i < CACHE_COUNT; ++i) {
        caches[i].size = (size_t)16 << i;
        list_init(&caches[i].partial);
        list_init(&caches[i].full);
    }
}

static struct slab *new_slab(unsigned int index) {
    struct Page *page = alloc_page();
    if (page == NULL) { return NULL; }
    struct slab *s = (struct slab *)(page2pa(page) + va_pa_offset);
    memset(s, 0, sizeof(*s));
    s->magic = SLAB_MAGIC;
    s->cache = index;
    s->capacity = (PGSIZE - object_offset()) / caches[index].size;
    assert(s->capacity > 0 && s->capacity <= 256);
    /* Free objects carry their own next pointers; allocated payload has no header. */
    for (size_t i = s->capacity; i > 0; --i) {
        void *object = (char *)s + object_offset() + (i - 1) * caches[index].size;
        *(void **)object = s->freelist;
        s->freelist = object;
    }
    list_add(&caches[index].partial, &s->link);
    return s;
}

void *kmalloc(size_t size) {
    if (size == 0 || size > (size_t)-1 - sizeof(struct large_header) - PGSIZE) {
        return NULL;
    }
    if (size > ((size_t)16 << (CACHE_COUNT - 1))) {
        size_t n = ROUNDUP(size + sizeof(struct large_header), PGSIZE) / PGSIZE;
        struct Page *page = alloc_pages(n);
        if (page == NULL) { return NULL; }
        struct large_header *h = (void *)(page2pa(page) + va_pa_offset);
        h->magic = LARGE_MAGIC;
        h->npages = n;
        return h + 1;
    }
    unsigned int index = 0;
    while (caches[index].size < size) { ++index; }
    struct slab *s;
    if (list_empty(&caches[index].partial)) {
        s = new_slab(index);
        if (s == NULL) { return NULL; }
    } else {
        s = to_struct(list_next(&caches[index].partial), struct slab, link);
    }
    void *object = s->freelist;
    s->freelist = *(void **)object;
    size_t slot = ((char *)object - (char *)s - object_offset()) / caches[index].size;
    assert(!(s->used[slot / 64] & (1UL << (slot % 64))));
    s->used[slot / 64] |= 1UL << (slot % 64);
    if (++s->inuse == s->capacity) {
        list_del(&s->link);
        list_add(&caches[index].full, &s->link);
    }
    return object;
}

void kfree(void *ptr) {
    if (ptr == NULL) { return; }
    struct slab *s = (void *)ROUNDDOWN((uintptr_t)ptr, PGSIZE);
    if (s->magic == LARGE_MAGIC) {
        struct large_header *h = (void *)s;
        assert(ptr == (void *)(h + 1));
        size_t n = h->npages;
        h->magic = 0;
        free_pages(pa2page(PADDR(h)), n);
        return;
    }
    assert(s->magic == SLAB_MAGIC && s->cache < CACHE_COUNT);
    unsigned int index = s->cache;
    size_t offset = (uintptr_t)ptr - (uintptr_t)s;
    assert(offset >= object_offset());
    offset -= object_offset();
    assert(offset % caches[index].size == 0);
    size_t slot = offset / caches[index].size;
    assert(slot < s->capacity && s->inuse > 0);
    assert(s->used[slot / 64] & (1UL << (slot % 64)));
    s->used[slot / 64] &= ~(1UL << (slot % 64));
    if (s->inuse == s->capacity) {
        list_del(&s->link);
        list_add(&caches[index].partial, &s->link);
    }
    *(void **)ptr = s->freelist;
    s->freelist = ptr;
    if (--s->inuse == 0) {
        list_del(&s->link);
        s->magic = 0;
        free_page(pa2page(PADDR(s)));
    }
}

// lab2 SLUB tests 2411185
static void check_bytes(void *ptr, size_t n, unsigned char value) {
    unsigned char *p = ptr;
    for (size_t i = 0; i < n; ++i) { assert(p[i] == value); }
}

void slub_check(void) {
    size_t before = nr_free_pages();
    assert(kmalloc(0) == NULL && kmalloc((size_t)-1) == NULL);
    kfree(NULL);
    static const size_t sizes[] = {1, 15, 16, 17, 31, 32, 33, 63, 64, 65,
        127, 128, 129, 255, 256, 257, 511, 512, 513, 1023, 1024, 1025,
        2047, 2048, 2049, 4096, 5000, 8192};
    void *objects[sizeof(sizes) / sizeof(sizes[0])];
    for (size_t i = 0; i < sizeof(objects) / sizeof(objects[0]); ++i) {
        objects[i] = kmalloc(sizes[i]);
        assert(objects[i] != NULL && ((uintptr_t)objects[i] & 15) == 0);
        memset(objects[i], (int)i + 1, sizes[i]);
    }
    for (size_t i = 0; i < sizeof(objects) / sizeof(objects[0]); ++i) {
        check_bytes(objects[i], sizes[i], i + 1);
        kfree(objects[i]);
    }
    assert(nr_free_pages() == before);

    /* Fill several slabs, reopen full slabs, reuse holes, retain live payload. */
    void *small[300];
    for (size_t i = 0; i < 300; ++i) {
        small[i] = kmalloc(16);
        assert(small[i] != NULL);
        for (size_t j = 0; j < i; ++j) { assert(small[i] != small[j]); }
        memset(small[i], (unsigned char)i, 16);
    }
    for (size_t i = 0; i < 300; i += 2) { kfree(small[i]); }
    for (size_t i = 1; i < 300; i += 2) {
        check_bytes(small[i], 16, (unsigned char)i);
    }
    size_t after_holes = nr_free_pages();
    for (size_t i = 0; i < 300; i += 2) {
        small[i] = kmalloc(16);
        assert(small[i] != NULL);
    }
    assert(nr_free_pages() == after_holes);
    for (size_t i = 0; i < 300; ++i) { kfree(small[i]); }
    assert(nr_free_pages() == before);

    /* A partial slab must still serve objects when the page layer is exhausted. */
    void *live = kmalloc(16);
    static struct Page *held[64];
    static size_t held_sizes[64];
    size_t held_count = 0;
    for (int order = 15; order >= 0; --order) {
        struct Page *page;
        while ((page = alloc_pages((size_t)1 << order)) != NULL) {
            assert(held_count < 64);
            held[held_count] = page;
            held_sizes[held_count++] = (size_t)1 << order;
        }
    }
    assert(live && held_count > 0 && nr_free_pages() == 0);
    void *reuse = kmalloc(16);
    assert(reuse != NULL && kmalloc(2048) == NULL && kmalloc(5000) == NULL);
    kfree(reuse);
    for (size_t i = 0; i < held_count; ++i) { free_pages(held[i], held_sizes[i]); }
    kfree(live);

    /* Deterministic mixed-size stress with independent content and overlap checks. */
    void *slots[32] = {0};
    size_t lengths[32] = {0};
    unsigned char patterns[32] = {0};
    uint32_t rng = 0x2414132;
    for (size_t step = 0; step < 2000; ++step) {
        rng = rng * 1664525U + 1013904223U;
        size_t i = (rng >> 16) % 32;
        if (slots[i] != NULL) {
            check_bytes(slots[i], lengths[i], patterns[i]);
            kfree(slots[i]);
            slots[i] = NULL;
        } else {
            lengths[i] = 1 + ((rng >> 3) % 8000);
            slots[i] = kmalloc(lengths[i]);
            assert(slots[i] != NULL);
            for (size_t j = 0; j < 32; ++j) {
                if (j != i && slots[j] != NULL) {
                    assert((uintptr_t)slots[i] + lengths[i] <= (uintptr_t)slots[j] ||
                           (uintptr_t)slots[j] + lengths[j] <= (uintptr_t)slots[i]);
                }
            }
            patterns[i] = (unsigned char)(step + 1);
            memset(slots[i], patterns[i], lengths[i]);
        }
    }
    for (size_t i = 0; i < 32; ++i) {
        if (slots[i] != NULL) {
            check_bytes(slots[i], lengths[i], patterns[i]);
            kfree(slots[i]);
        }
    }
    for (size_t i = 0; i < CACHE_COUNT; ++i) {
        assert(list_empty(&caches[i].partial) && list_empty(&caches[i].full));
    }
    assert(nr_free_pages() == before);
    cprintf("slub_check() succeeded! (size classes, reuse, reclaim, OOM, 2000 mixed operations)\n");
}
