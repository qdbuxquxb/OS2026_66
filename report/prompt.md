# Lab2 提示词汇总

小组成员：国轩 2414132、孟子玉 2411963、韩东儒 2411185。

本实验使用的 7 份提示词如下，分别对应物理内存初始化、Best-Fit、Buddy、SLUB 及页表调试。

提示词中的 `code/` 为源码目录。P1、P2 完成物理页初始化与默认分配器；P3、P5 分别实现 Buddy 和 SLUB，P4、P6 对应各自的测试；P7 用于双 GDB 页表与 TLB 调试。

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

## P3 Buddy 分配器实现

负责人：国轩 2414132。

```text
[PROMPT]
任务：新增 code/kern/mm/buddy_pmm.c、buddy_pmm.h，实现 Buddy 连续页分配，并接入 pmm.c、Makefile。
操作要求：修改实际文件，注释署 2414132；保留默认 Best-Fit、已有测试、Page 和 pmm_manager 公开定义。
输出要求：支持 make PMM=buddy qemu，并可切回默认；用 QEMU 4.1.1 编译启动，说明实际占用页数与释放约定。

[RELY]
阅读 code/kern/mm/{pmm.h,memlayout.h,best_fit_pmm.c}。
复用 pmm_manager 接口、Page 描述符、page2ppn/page2pa、pages/nbase/npage；物理范围按框架限制。

[GUARANTEE]
实现 const struct pmm_manager buddy_pmm_manager 及以下 static 接口：
void buddy_init(void);
void buddy_init_memmap(struct Page *base, size_t n);
struct Page *buddy_alloc_pages(size_t n);
void buddy_free_pages(struct Page *base, size_t n);
size_t buddy_nr_free_pages(void);
void buddy_validate(void);
允许内部状态与 static 辅助函数；保留后续独立添加 buddy_check 的空间。

[SPECIFICATION]
buddy_init：Pre 为首次初始化或隔离池已无活跃分配；Post 为管理状态为空、空闲计数为零。
buddy_init_memmap：Pre 为 n>0、区间保留且不与已管理区间重叠；Post 为全部页面可管理，非对齐、非二次幂的首尾页面不丢失。
buddy_alloc_pages：Pre 为 n>0；成功时返回按实际块大小对齐、至少 n 页的二次幂块，计数扣除实际页数；无合适块或请求过大时返回 NULL，状态不变。
buddy_free_pages：Pre 为本分配器返回的块及原请求 n；Post 为实际占用页全部回收，所有可合并的同阶伙伴充分合并；重复或与实际块大小不匹配的释放用断言拒绝。
buddy_nr_free_pages：准确返回空闲页数，无副作用。
buddy_validate：检查空闲块大小、物理对齐、范围、计数及伙伴合并状态；通过后不改变资源状态。
Requirements：伙伴关系以物理页号定义，不能误合并其他分配器的块；零页请求用断言拒绝；切换构建配置须使选择代码重新编译。
```

## P4 Buddy 独立测试

负责人：国轩 2414132。

```text
[PROMPT]
任务：在 code/kern/mm/buddy_pmm.c 添加 Buddy 测试，并接入 pmm.c 的初始化检查。
操作要求：修改实际文件，注释署 2414132；不得改写算法来迎合测试，也不得修改官方测试。
输出要求：运行测试，说明各断言验证什么；失败时保留现场并分析，不用打印 PASS 代替断言。

[RELY]
读取已实现的 buddy_pmm_manager 及 code/kern/mm/pmm.h。
可使用 alloc_pages/free_pages/nr_free_pages、页地址转换、assert、cprintf；掌握请求向上取整到二次幂的接口约定。

[GUARANTEE]
实现 void buddy_check(void)，在 buddy_pmm.h 声明，并由 pmm_init 调用。

[SPECIFICATION]
Pre-Condition：物理页初始化完成，当前分配器可用。
Post-Condition：验证结束后主分配器和空闲总数恢复，测试不影响池外页面或仍在使用的内存。
Case 1：默认模式用隔离池验证 3/5 页请求、实际占用 4/8 页、地址对齐与不重叠、分裂后重新获得完整 64 页块。
Case 2：逐页耗尽后返回 NULL；交错释放不能凭空形成连续块；全部释放后能完整合并。
Case 3：非对齐 93 页区间须恰好返回 93 个唯一且不越界的页面，超大请求失败且状态不变。
Case 4：Buddy 已是主分配器时，在真实页池上检查分配、释放及计数恢复，不得重置活跃管理状态。
Requirements：用地址范围、唯一性和资源守恒检验结果，不照抄算法内部的判断作为唯一依据。
```

## P5 SLUB 对象分配器实现

负责人：韩东儒 2411185。

```text
[PROMPT]
任务：新增 code/kern/mm/slub.c、slub.h，实现单 CPU 的简化 SLUB，为内核提供任意正字节数的对象分配。
操作要求：修改实际文件，注释署 2411185；仅增加必要初始化调用，不修改底层页分配接口、公开 Page 定义或已有测试。
输出要求：说明小对象与大对象的资源归属、分配失败和释放约定，并使用 QEMU 4.1.1 编译运行。

[RELY]
读取 code/kern/mm/pmm.h、memlayout.h 及已完成的两种页分配器。
底层提供 alloc_pages/free_pages，Buddy 可能多分配到二次幂；page2pa、pa2page、PADDR 和 va_pa_offset 处理地址转换。
可使用 code/libs 中的链表和内存操作；没有宿主 malloc 或内核堆可依赖。

[GUARANTEE]
实现 void slub_init(void)、void *kmalloc(size_t size)、void kfree(void *ptr)，在 slub.h 声明；允许 static 辅助函数和内部元数据。

[SPECIFICATION]
slub_init：Pre 为页管理已就绪且尚无 SLUB 活跃对象；Post 为对象缓存可用且不预占无关页面。
kmalloc：Pre 为初始化完成。
Post/Case 1：不超过 2048 字节的正请求，由最小可容纳的 16～2048 字节二次幂大小类服务，优先复用已有空位。
Post/Case 2：更大请求由连续页支撑；成功结果按 16 字节对齐，满足请求长度，与所有活跃对象不重叠。
Post/Case 3：零长度、算术溢出或资源不足返回 NULL，不泄漏已取得资源。
kfree：Pre 为 NULL 或尚未释放的合法返回指针；NULL 无操作，合法对象恢复可复用状态；空 slab 和大对象占用页能正确归还，包括底层 Buddy 的取整占用。
Requirements：使用 partial/full 状态区分可分配与已满 slab；检查小对象边界与重复释放。无需多核锁、每 CPU 缓存或 NUMA。
```

## P6 SLUB 独立测试

负责人：韩东儒 2411185。

```text
[PROMPT]
任务：在 code/kern/mm/slub.c 添加对象分配测试，并接入 pmm_init。
操作要求：修改实际文件，注释署 2411185；保留 kmalloc/kfree 行为与已有测试，允许新增 static 测试辅助函数。
输出要求：分别以 Best-Fit、Buddy 为页分配器运行，保留失败信息与真实结果。

[RELY]
读取 code/kern/mm/slub.h、pmm.h 及实现中的公开分配约定。
可依赖 assert、memset、页计数和地址区间比较，不依赖 slab 私有布局作为唯一验证依据。

[GUARANTEE]
实现 void slub_check(void)，在 slub.h 声明；初始化后调用它。

[SPECIFICATION]
Pre-Condition：页分配器、SLUB 已初始化，没有外部活跃 SLUB 对象。
Post-Condition：对象全部释放，空闲页数恢复，测试缓存无遗留对象。
Case 1：覆盖各大小类的前后边界及 2049、4096、5000、8192 字节，检查对齐，并读写完整请求长度。
Case 2：300 个小对象覆盖多个 slab；交错释放后验证未释放数据，重新分配复用空位，不额外占页。
Case 3：耗尽页层后，现有缓存空位仍能分配，新缓存和大对象返回 NULL；释放后资源恢复。
Case 4：执行 2000 次确定性的混合分配/释放，检查活跃对象内容及范围互不重叠。
Requirements：包含 kmalloc(0)、极大请求与 kfree(NULL)；两种页分配器均适用，不能假设空闲页可一次连续分配完。
```

## P7 页表与 TLB 调试

负责人：孟子玉 2411963。

```text
[PROMPT]
任务：新增 code/tools/debug_mmu.py，并仅增加必要的内核探针，用双 GDB 观察一次真实访存的页表查询、TLB 填充及随后命中。
操作要求：修改实际文件，注释署 2411963；使用带调试信息的 QEMU 4.1.1，不覆盖日常模拟器，不修改官方测试或强行伪造观测结果。
输出要求：保存两端原始日志和结果；区分客户虚拟地址、客户物理地址与宿主地址，失败明确报告。

[RELY]
读取 code/kern/init/{entry.S,init.c}、code/kern/mm/{pmm.h,memlayout.h}。
RISC-V GDB 调试客户内核，宿主 GDB 调试 QEMU；QEMU 源码中关注 cpu_helper.c 的 get_physical_address/riscv_cpu_tlb_fill、cputlb.c 的加载和填充路径，以及宿主后端的 TLB 快速路径。

[GUARANTEE]
提供 python3 tools/debug_mmu.py --qemu PATH --out DIR（在 code/ 中执行）。
如需探针，在 kern/init 下新增，声明与调用一致；脚本负责启动、连接和清理自己的调试进程。

[SPECIFICATION]
Pre-Condition：内核已编译，两个 GDB 与带符号的 QEMU 4.1.1 可用。
Post-Condition：原始记录能将具体指令、被访问地址、PTE、翻译结果和 TLB 状态对应起来，退出后不遗留调试进程。
Case 1：受控访问引发首次 miss，观察 satp、索引、叶子层级、权限及物理地址，正确包含页内偏移。
Case 2：后续同地址访问命中，结合读值、TLB 项和实际慢路径/填充计数验证，不能只凭输出文字判断。
Case 3：Bare 模式对照，记录恒等转换与软件 TLB 行为；若根级大页直接命中，如实记录，不声称访问了三级。
Requirements：支持本机进程调试权限及中文路径；端口和断点范围受控，调试器读取内存不能混作客户实际访存的证据。
```
