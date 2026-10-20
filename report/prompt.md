# Lab2 提示词汇总

小组成员：国轩 2414132、孟子玉 2411963、韩东儒 2411185。

提示词中的 `code/` 为源码目录。

## P1 物理内存初始化

负责人：国轩 2414132。

```text
[PROMPT]
任务：在 code/kern/mm/pmm.c 的 lab2 function1 标记处完成物理内存初始化，使可用完整物理页交由当前分配器管理。
操作要求：修改实际文件；保留框架接口、启动映射和已有测试，注释署 2414132。不要重装工具链。
输出要求：说明修改点、编译结果与实际检查结果；未执行的检查明确注明。

[RELY]
阅读 code/kern/mm/{pmm.h,memlayout.h,mmu.h} 和 code/kern/driver/dtb.h。
已有 get_memory_base/get_memory_size、init_memmap、pa2page、PADDR 及对齐/页面状态宏。
Page 含 ref、flags、property、page_link；pages[i] 对应物理页号 nbase+i，npage 是物理页号上界。
end 是内核末端虚拟地址；地址偏移、DRAM 基址及管理上界以工程定义为准。

[GUARANTEE]
实现 static void page_init(void)；正确维护 va_pa_offset、npage、pages。允许新增 static 辅助函数。

[SPECIFICATION]
page_init：
Pre-Condition：启动映射有效，DTB 已解析，当前 pmm_manager 已初始化。
Post-Condition：描述符覆盖可管理物理页；固件、内核、描述符数组和不完整尾页不会被分配。
Case 1：范围有效且空间足够时，描述符数组位于 end 之后并按页对齐，已用页保留，仅注册剩余完整空闲页；输出探测范围。
Case 2：DTB 信息缺失、基址不符合框架、地址溢出或描述符无法放下时，以 panic 终止，禁止越界写入和注册空闲区。
Case 3：没有剩余完整页面时，空闲数为零，不调用 init_memmap。
Requirements：管理范围不超过 DTB 末端及框架上界；区分虚拟地址、物理地址、页号与描述符地址。
```

## P2 Best-Fit 连续页分配

负责人：孟子玉 2411963。

```text
[PROMPT]
任务：补全 code/kern/mm/best_fit_pmm.c 的 lab2 标记处，完成 Best-Fit，并在 pmm.c 中将它设为默认分配器。
操作要求：修改实际文件，注释署 2411963；不得修改 basic_check、best_fit_check、官方评分工具及公开数据结构。
输出要求：列出改动，并用 QEMU 4.1.1 执行编译、启动和 make grade，记录真实结果。

[RELY]
参考 code/kern/mm/default_pmm.c；读取同目录 pmm.h、memlayout.h，以及 code/libs/list.h。
Page 的 property 表示空闲块页数，PageProperty 标识空闲块首页。原测试直接使用 free_list、nr_free，并保存恢复它们。

[GUARANTEE]
实现以下 static 接口及 const struct pmm_manager best_fit_pmm_manager：
void best_fit_init(void);
void best_fit_init_memmap(struct Page *base, size_t n);
struct Page *best_fit_alloc_pages(size_t n);
void best_fit_free_pages(struct Page *base, size_t n);
size_t best_fit_nr_free_pages(void);
注册原有 best_fit_check；修改 init_pmm_manager 的默认选择。允许 static 辅助函数。

[SPECIFICATION]
best_fit_init：Pre 为首次初始化；Post 为空闲链表为空、计数为零。
best_fit_init_memmap：Pre 为 n>0 且区间全部保留；Post 为这些页恰好注册一次，引用计数清零、空闲数增加 n。
best_fit_alloc_pages：Pre 为 n>0、空闲状态一致。
Post/Case 1：存在足够大的连续块时，选最小合适块，等大时取低地址；恰好分配 n 页，余块保持可用，空闲数减少 n，返回块不再标为空闲首页。
Post/Case 2：总数不足或碎片导致无合适块时，返回 NULL，链表与计数不变。n==0 用断言拒绝。
best_fit_free_pages：Pre 为有效的已分配连续区间、n>0；Post 为回收恰好 n 页，并合并前后物理相邻空闲块，不重叠、不重复计数。
best_fit_nr_free_pages：返回真实空闲页总数，无副作用。
Requirements：空闲块按地址组织，状态必须兼容原有两个测试函数。
```
