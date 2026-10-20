# 操作系统实验报告

## 实验基本信息

| 项目 | 内容 |
| --- | --- |
| **实验名称** | Lab 2：物理内存和页表 |
| **小组成员** | 2414132-国轩、2411963-孟子玉、2411185-韩东儒 |
| **完成日期** | 2026-10-20 |

### 小组分工

| 成员 | 实验任务 | 报告任务 |
| --- | --- | --- |
| 2414132-国轩 | 物理内存探测与页描述符初始化、Buddy 分配器及其测试，统筹代码整合 | 实验目的、整体逻辑、物理内存初始化、Buddy、全文整合 |
| 2411963-孟子玉 | Best-Fit 分配器、双 GDB 页表与 TLB 调试 | Best-Fit 的实现及改进分析、页表调试过程、问题分析 |
| 2411185-韩东儒 | First-Fit 代码分析、SLUB 分配器及其测试、运行结果核对 | 实验环境、First-Fit 分析、SLUB、测试与验证 |

实验总结由三人共同讨论，国轩负责汇总，孟子玉、韩东儒核对各自负责的内容。

### 实验文件组织

本实验对应 Git 分支 `lab2`，仓库根目录包含以下两个文件夹：

```text
code/                  实验源码、验证脚本及原始日志
report/
├── report.md          实验报告
├── prompt.md          本实验提示词汇总
└── images/            报告引用的测试记录截图
```

源码和测试日志分别位于 `code/`、`code/evidence/`，报告、提示词及截图位于 `report/`。

-----

## 一、实验目的

1. 理解内核如何从设备树中取得物理内存信息，以及如何排除固件、内核镜像和管理数据占用的空间。
2. 掌握以物理页为单位记录内存状态的方法，区分虚拟地址、物理地址、物理页号与 `Page` 描述符。
3. 理解连续物理页管理，实现 Best-Fit 分配与回收。

-----

## 二、实验环境

实际验证所用环境为 Ubuntu 22.04.5 LTS（WSL2，`x86_64`）、`riscv64-unknown-elf-gcc` 15.1.0、QEMU 4.1.1、OpenSBI v0.4 和 RISC-V GDB 16.3.90。实验使用仓库 `code/` 目录中的 Makefile、链接脚本和内核代码。页表调试另外使用带调试信息的 QEMU 4.1.1，以及用于调试 QEMU 源码的 GDB 12.1。

| 成员 | AI 编程工具 | 底层模型 | 备注 |
| --- | --- | --- | --- |
| 2414132-国轩 | Codex（VS Code 插件） | GPT-6 | 辅助梳理物理内存初始化与 Buddy 分配逻辑，核对实现并整合报告 |
| 2411963-孟子玉 | Claude（VS Code 插件） | DeepSeek-V4-Flash | 辅助完成 Best-Fit，分析页表查询与 TLB 调试结果 |
| 2411185-韩东儒 | DeepSeek Harness | DeepSeek-V4-Flash | 辅助分析 First-Fit 和 SLUB，整理运行结果与测试截图 |

-----

## 三、实验整体逻辑分析

### 3.1 本章节的逻辑主线

实验一让内核能够启动并输出信息，实验二进一步解决“内核能够使用哪些内存，以及如何把内存分配出去”的问题。

这里有两条相互配合的线索。一条是物理内存管理：从设备树读取内存范围，为每个物理页建立描述符，把真正空闲的页面交给分配器，再实现页面的分配与回收。另一条是地址转换：入口汇编已经建立启动页表并开启 Sv39，后续 C 代码在高位虚拟地址运行，因此访问物理页及其描述符时必须分清地址之间的关系。

我们的实现顺序是先建立正确的可用物理页范围，再完成 Best-Fit 页分配。启动页表提供内核高地址与物理内存之间的固定映射，页描述符和空闲区的初始化都依赖这一地址关系。

### 3.2 功能的逐步实现

1. **进入分页运行环境。** `entry.S` 保存启动参数，设置启动页表和 `satp`，刷新 TLB，并转入高地址的 `kern_init`。本次框架已提供这部分主要代码。
2. **读取内存信息。** `kern_init` 先清零 BSS，再调用 `dtb_init()`，保存设备树中的物理内存基址和长度。
3. **初始化物理页管理。** `pmm_init()` 先选择并初始化分配器，再由 `page_init()` 安排描述符数组、标记保留页，并通过 `init_memmap()` 注册空闲区。
4. **实现连续页分配。** 通过 `pmm_manager` 接口接入 Best-Fit，实现最小合适块选择、分裂与相邻块合并。
5. **验证物理页管理。** 运行默认内核及课程评分，检查页初始化与 Best-Fit。

-----

## 四、实验内容与实现

我们用 `[PROMPT]`、`[RELY]`、`[GUARANTEE]` 和 `[SPECIFICATION]` 分别描述任务、已有资源、接口及行为约束。对应提示词汇总见 [prompt.md](./prompt.md)。

### 4.1 功能模块一：物理内存探测与页描述符初始化

**负责人：** 2414132-国轩

主要实现 `code/kern/mm/pmm.c` 中的函数：

```c
static void page_init(void);
```

#### 任务提示词（P1）

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

#### Spec 与提示词设计

这一任务首先要确定“哪些页可以交给分配器”。因此，spec 将地址类型、管理上界、描述符占用和整页边界分别列为约束，并将成功初始化、无效内存信息、没有完整空闲页分成三种情形。提示词明确 `npage` 是物理页号上界，要求保留启动映射和已有接口，以避免把描述符数组长度或内核虚实地址关系理解错误。

#### 内存信息与地址关系

`dtb_init()` 从启动时传入的设备树中提取内存范围，`page_init()` 通过 `get_memory_base()`、`get_memory_size()` 取得结果。本次默认配置为 128 MiB，物理内存范围是 `[0x80000000, 0x88000000)`。

这段范围不能全部交给分配器：前部有 OpenSBI 和内核，内核之后还要存放 `Page` 描述符数组。描述符本身也是内存中的数据，必须占用实际页面。

本实验使用的虚实地址关系为：

```text
虚拟地址 = 物理地址 + 0xffffffff40000000
物理地址 = 虚拟地址 - 0xffffffff40000000
```

`pages` 保存描述符数组的虚拟地址，`pages[i]` 对应物理页号 `nbase + i`。其中 `nbase = 0x80000000 / 4096`，`npage` 是可管理物理页号的上界，因此描述符数量是 `npage - nbase`，不能直接把 `npage` 当作数组长度。

#### 初始化过程

`page_init()` 先设置 `va_pa_offset`，检查设备树范围是否有效。由于框架的描述符换算和启动映射以 `DRAM_BASE` 为基准，本次实现要求基址为 `0x80000000`，并拒绝零长度和地址相加溢出的情况。

接下来，把设备树末端与 `PHYSICAL_MEMORY_END` 取较小值，再向下按页对齐，得到可管理末端。这样既不会超过设备树报告的内存，也不会超过当前框架设定的管理范围。

描述符数组放在内核 `end` 之后，起点向上按页对齐。写入数组前先检查整个数组是否能够放入可管理内存。随后将所有描述符置为保留状态，再把数组末端向上按页对齐，得到空闲区起点。仅当起点小于可管理末端时，才调用 `init_memmap()`。

默认 Best-Fit 构建中，各部分的实际布局如下：

| 项目 | 本次构建中的值 |
| --- | --- |
| 内核 `end` 虚拟地址 | `0xffffffffc0206078` |
| 描述符数组物理起点 | `0x80207000` |
| 描述符数量 | 32768 个 |
| 单个 `Page` 大小 | 40 字节 |
| 描述符数组占用 | `0x140000` 字节，即 1280 KiB |
| 空闲区物理起点 | `0x80347000` |
| 初始空闲页数 | 31929 页 |

这些值随内核布局变化而变化，初始化代码根据链接符号和描述符大小计算，没有将表中的地址写死。

#### Challenge：如何获取未知硬件的可用物理内存范围

可以由固件或引导程序提供内存映射信息，内核通过约定的接口取得并解析。例如，本实验从 `a1` 取得设备树地址，再解析内存节点的 `reg` 属性。

取得一段 RAM 的基址和长度后，还需要扣除固件保留区、内核以及其他仍在使用的区域，才能得到可分配范围。本实验在解析后只保留内存基址和长度，后续不再使用原始 DTB，因此不长期保留其存储区。更完整的系统还需要处理多个内存区间和设备树中的保留内存信息。

直接向未知地址读写来探测内存存在风险：该地址可能属于设备寄存器，也可能触发总线异常或破坏已有数据。因此，在固件提供内存信息的环境中，应优先使用这些信息。

### 4.2 功能模块二、任务二：实现 Best-Fit

**负责人：** 2411963-孟子玉

#### 任务提示词（P2）

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

实现文件为 `code/kern/mm/best_fit_pmm.c`，主要接口如下：

```c
static void best_fit_init(void);
static void best_fit_init_memmap(struct Page *base, size_t n);
static struct Page *best_fit_alloc_pages(size_t n);
static void best_fit_free_pages(struct Page *base, size_t n);
static size_t best_fit_nr_free_pages(void);
```

Best-Fit 的 spec 同时约定了选择策略和状态变化：成功分配须选择最小合适块，失败时计数与链表保持不变，释放后按地址合并。提示词列出框架测试所依赖的内部状态，要求自行完成管理函数与注册结构，并保留两个测试函数，以保证算法能够接入已有框架。

Best-Fit 与 First-Fit 使用相同的空闲块表示，区别主要在分配时的选择方式：遍历空闲块，选择能够满足请求且页数最少的一块。如果找到正好匹配的块，就可以提前结束；相同大小的块按地址顺序优先选择低地址块。

例如，空闲链表中依次有 8 页和 3 页的块，申请 2 页时，First-Fit 会使用前面的 8 页块，Best-Fit 会使用 3 页块。这说明 Best-Fit 的判断依据是满足请求后留下的空间大小。

我们仍按地址维护链表，因为这便于回收时寻找相邻块。`insert_and_merge()` 统一处理插入与前后合并，供初始化和释放使用。分配时先移除选中的块并清除首页空闲标记；若还有剩余页面，再为剩余块设置长度和标记。空闲计数只按实际分配或回收的页数变化。

文件原有的 `basic_check()`、`best_fit_check()` 保持不变，实现保留了它们直接访问 `free_list`、`nr_free` 所需的状态约定。完成模块后，在 `init_pmm_manager()` 中默认选择 `best_fit_pmm_manager`，确保内核实际运行并检查的是新实现。

**Best-Fit 的改进空间。** 当前分配最坏仍需扫描全部空闲块，时间复杂度为 `O(B)`。可以增加按块大小排序的平衡树或分级索引，加快最小合适块的查找，同时保留按地址判断相邻关系的机制。Best-Fit 也可能留下很多很小的空闲块，因此“本次剩余最少”并不等于“长期碎片最少”，还需要结合请求分布评估。

### 4.3 实现中的问题

**框架宏不能直接假定存在。** 第一次编译 `page_init()` 时使用了 `MIN`，编译器报告未声明。检查框架后改用条件表达式取得两个内存末端的较小值，随后重新编译通过。

-----

## 五、测试与验证

### 5.1 编译与启动

在仓库根目录执行以下命令，完成编译和默认 Best-Fit 启动：

```bash
cd code
make
make qemu
```

内核检查输出如下：

```text
memory management: best_fit_pmm_manager
check_alloc_page() succeeded!
```

完整输出见 [Best-Fit 启动日志](../code/evidence/qemu-best-fit-128M.log)。完成检查后内核进入循环，日志末尾的 QEMU 终止信号来自自动测试程序。

### 5.2 课程评分

执行 `make grade`，物理内存初始化和 Best-Fit 检查通过：

```text
  -check page init:                          OK
  -check best fit:                           OK
Total Score: 20/20
```

[评分日志](../code/evidence/make-grade.log)记录了检查结果。两个框架测试函数与课程评分工具保持不变。

-----

## 六、实验总结与收获

### 对操作系统的理解

| 本实验知识点 | 对应的 OS 原理及联系 |
| --- | --- |
| 物理页描述符与保留区域 | 内存管理首先要明确资源边界；管理数据本身也占用资源，不能把它覆盖的页面再次分配 |
| First-Fit 与 Best-Fit | 都在连续空闲块中选择可用区域，选择策略影响查找开销和外部碎片，及时合并相邻块是两者共同需要的机制 |
| Sv39 页表与大页 | 页表项不一定指向下一级；本次根页表的叶子项直接映射 1 GiB，体现了大页减少查询层级的作用 |

本实验虽然开启了分页，但主要使用固定的启动映射，还没有实现完整的进程虚拟地址空间管理。按需分页、缺页处理与换页、写时复制、进程间隔离，以及多核环境下的分配同步和 TLB 一致性，都没有在本次实验中完成。

-----

## 参考资料

1. [课程实验指导：实验二练习要求](http://oslab.mobisys.top/lab2026/_book/lab2/lab2_2_1_exercise.html)。
2. [课程实验指导：物理内存探测](http://oslab.mobisys.top/lab2026/_book/lab2/lab2_3_5_2_search_phymem_layout.html)。
3. [课程实验指导：页表与 TLB 调试](http://oslab.mobisys.top/lab2026/_book/lab2/lab2_4_qemu_mmu_debug.html)。
