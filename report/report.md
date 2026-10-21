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
3. 理解 First-Fit，实现并比较 Best-Fit 与 Buddy 连续物理页分配算法。
4. 使用两个 GDB 分别调试内核和 QEMU，观察 Sv39 页表查询、TLB 填充与命中的过程。

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

我们的实现顺序是先建立正确的可用物理页范围，再完成不同的页分配算法。页表调试则帮助我们从模拟硬件的执行过程验证：内核使用的虚拟地址怎样对应到这些物理内存。

### 3.2 功能的逐步实现

1. **进入分页运行环境。** `entry.S` 保存启动参数，设置启动页表和 `satp`，刷新 TLB，并转入高地址的 `kern_init`。本次框架已提供这部分主要代码。
2. **读取内存信息。** `kern_init` 先清零 BSS，再调用 `dtb_init()`，保存设备树中的物理内存基址和长度。
3. **初始化物理页管理。** `pmm_init()` 先选择并初始化分配器，再由 `page_init()` 安排描述符数组、标记保留页，并通过 `init_memmap()` 注册空闲区。
4. **实现连续页分配。** 在理解 First-Fit 的基础上实现 Best-Fit，并实现按二次幂拆分、合并的 Buddy。二者通过同一组 `pmm_manager` 接口接入内核。
5. **验证实现与地址转换。** 通过框架检查、自编测试和多种内存配置验证分配器，再通过双 GDB 观察真实访存指令对应的页表查询和 TLB 行为。

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
| 内核 `end` 虚拟地址 | `0xffffffffc0207188` |
| 描述符数组物理起点 | `0x80208000` |
| 描述符数量 | 32768 个 |
| 单个 `Page` 大小 | 40 字节 |
| 描述符数组占用 | `0x140000` 字节，即 1280 KiB |
| 空闲区物理起点 | `0x80348000` |
| 初始空闲页数 | 31928 页 |

这些值随内核布局变化而变化，初始化代码根据链接符号和描述符大小计算，没有将表中的地址写死。

#### Challenge：如何获取未知硬件的可用物理内存范围

可以由固件或引导程序提供内存映射信息，内核通过约定的接口取得并解析。例如，本实验从 `a1` 取得设备树地址，再解析内存节点的 `reg` 属性。

取得一段 RAM 的基址和长度后，还需要扣除固件保留区、内核以及其他仍在使用的区域，才能得到可分配范围。本实验在解析后只保留内存基址和长度，后续不再使用原始 DTB，因此不长期保留其存储区。更完整的系统还需要处理多个内存区间和设备树中的保留内存信息。

直接向未知地址读写来探测内存存在风险：该地址可能属于设备寄存器，也可能触发总线异常或破坏已有数据。因此，在固件提供内存信息的环境中，应优先使用这些信息。

### 4.2 功能模块二、任务一：理解 First-Fit

**负责人：** 2411185-韩东儒

First-Fit 的主要实现位于 `code/kern/mm/default_pmm.c`，通过按地址排列的空闲块链表管理连续页。链表中的每个节点代表一个空闲块，块首页的 `property` 表示页数，`PageProperty` 表示它是空闲块首页。

| 函数 | 主要作用 |
| --- | --- |
| `default_init()` | 初始化空闲链表和空闲页计数 |
| `default_init_memmap()` | 将指定的保留页转为空闲页，建立块首页，并按地址插入链表 |
| `default_alloc_pages(n)` | 从低地址开始查找第一个至少有 `n` 页的块，取出所需页面，保留剩余部分 |
| `default_free_pages(base, n)` | 重置回收页状态，按地址插回链表，并与前后相邻空闲块合并 |
| `default_nr_free_pages()` | 返回当前空闲页总数 |

分配时，如果某块刚好有 `n` 页，就将整块移出链表；如果更大，就把剩余部分作为新的空闲块。释放时先检查前块末端是否等于当前块起点，再检查当前块末端是否等于后块起点，连续时进行合并。合并后只保留新块首页的标记，防止一个空闲区被重复计数。

**First-Fit 的改进空间。** 设空闲块数为 `B`，当前查找和按地址插入最坏都需要扫描链表。可以按大小建立辅助索引或空闲块分组，减少不合适块的检查；也可以尝试 Next-Fit，减少每次都从链表头部开始的重复扫描。不过 Next-Fit 会改变搜索起点，并不保证更少的碎片。改进时还要考虑索引维护成本和相邻块合并是否方便。 另外，给定 `default_pmm.c` 中的尾插分支在 `list_add()` 后没有结束循环，下一轮会再次访问新插入的节点，存在重复插入和破坏链表的风险；这里应补充 `break`。本实验保留该参考文件，在 Best-Fit 的统一插入函数中通过插入后结束搜索避免这一问题。

### 4.3 功能模块二、任务二：实现 Best-Fit

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

### 4.4 功能模块二、任务三：Buddy System

**负责人：** 2414132-国轩

#### 实现提示词（P3）

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

#### 测试提示词（P4）

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

新增 `code/kern/mm/buddy_pmm.c` 和 `buddy_pmm.h`，定义 `buddy_pmm_manager`，通过框架的页管理接口接入内核。

#### Spec 与提示词设计

Buddy 的 spec 重点约定了请求页数与实际占用页数的区别，以及释放时仍传入原请求页数。实现提示词同时要求用物理页号定义伙伴、完整接收非对齐区间；测试提示词则通过地址唯一性、边界和空闲计数检验这些约定，并要求隔离测试结束后恢复原分配器。

#### 分配与回收

Buddy 按阶数组织空闲块，`order` 阶的块包含 `2^order` 页。本实现设置 0 至 15 阶的空闲链表，覆盖当前框架的物理页范围。

初始化时，可用区起点和长度不一定符合二次幂边界，因此 `buddy_init_memmap()` 每次选择当前地址满足对齐、且不会超过剩余长度的最大块。这样可以完整接收非对齐、非二次幂长度的区间。

申请 `n` 页时，先向上取整到二次幂。例如申请 3 页实际占用 4 页，申请 5 页实际占用 8 页。若对应阶没有空闲块，就寻找更高阶的块，逐级对半拆分，把暂时不用的一半放回相应链表。

释放时根据请求恢复实际块大小，检查块首地址、长度和已分配状态，再寻找伙伴：

```c
buddy_ppn = page2ppn(base) ^ count;
```

这里异或的是物理页号，`count` 是当前块的页数。只有伙伴处于 Buddy 空闲状态、大小也相同，才能合并并继续尝试更高阶。我们使用独立的 `BUDDY_FREE` 标记识别 Buddy 空闲块，避免隔离测试时把外部 Best-Fit 链表中的块误当作伙伴。

构建时默认仍为 Best-Fit，执行 `make PMM=buddy qemu` 可切换为 Buddy。Makefile 为选择项设置了构建标记，切换后会重新编译分配器选择代码，避免沿用上一次配置的目标文件。

#### 测试覆盖及有效性

| 测试情形 | 检查内容及作用 |
| --- | --- |
| 3 页和 5 页请求 | 分别占用 4 页、8 页，空闲数减少 12，且返回范围不重叠 |
| 分裂后完整回收 | 释放后能再次申请整个 64 页块，验证逐级合并确实完成 |
| 逐页耗尽 | 64 个单页地址互不重复，耗尽后返回 `NULL` |
| 交错释放 | 仅释放隔页时无法申请连续 2 页；释放其余页后重新形成完整块 |
| 非对齐 93 页区间 | 分配恰好 93 个不同页面，均在区间内，验证首尾页面没有丢失 |
| 超大请求 | 申请失败，不把区间之外的页面返回给调用者 |

默认启动时先向 Best-Fit 申请临时池，在隔离池中完成上述 Buddy 测试，最后恢复原分配器并归还整个临时池，检查空闲页数恢复。以 Buddy 作为主分配器启动时，则在真实空闲页池上检查分配、回收及状态不变量。

这些检查同时比较地址范围、唯一性、实际页数和回收后的总量，能够发现只看“返回值非空”无法暴露的重叠分配、丢页或合并不完整问题。Buddy 的代价是按二次幂取整产生内部碎片，本实验中的 3 页请求就会多占用 1 页。

### 4.5 分支任务：使用 GDB 调试页表查询与 TLB

**负责人：** 2411963-孟子玉

#### 调试提示词（P7）

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

#### 调试方法

我们用普通 GDB 启动带调试信息的 QEMU，观察模拟器源码；再用 RISC-V GDB 连接 QEMU 的 GDB stub，观察内核寄存器和指令。QEMU 作为普通 GDB 的子进程运行，两个调试器分别控制模拟器和内核。

为了稳定观察同一地址的两次访问，在 `code/kern/init/mmu_probe.S` 中加入了很短的测试函数：

```asm
sfence.vma
ld t0, 0(a0)
ld a0, 0(a0)
ret
```

刷新 TLB 后连续执行两条加载指令，读同一个测试变量。RISC-V GDB 控制执行位置，普通 GDB 则在慢路径、页表查询与 TLB 填充函数中设置断点。两个 GDB 的启动、断点设置和执行控制由 `code/tools/debug_mmu.py` 完成，调试输出保存在日志中。


#### 从虚拟地址到物理地址

本次默认构建中，第一条加载指令的 PC 为 `0xffffffffc0200158`，被访问地址为 `0xffffffffc0207010`，`satp` 为 `0x8000000000080206`。

第一次读取未命中 TLB 后，实际调用栈中的关键路径为：

```text
生成的访存代码
  → helper_le_ldq_mmu / load_helper
  → tlb_fill
  → riscv_cpu_tlb_fill
  → get_physical_address
```

成功翻译并通过权限检查后，`riscv_cpu_tlb_fill()` 调用 `tlb_set_page()` 建立缓存项。`get_physical_address()` 中观察到：

| 观察项 | 实际值及解释 |
| --- | --- |
| 分页模式 | Sv39，最多三级，`levels = 3` |
| 根页表物理地址 | `0x80206000`，来自 `satp` 中的物理页号 |
| 根页表索引 | `0x1ff`，即第 511 项 |
| 被读取 PTE 的物理地址 | `0x80206000 + 511 × 8 = 0x80206ff8` |
| PTE 值 | `0x200000cf` |
| PTE 中的物理页号 | `0x80000` |
| 命中层级 | 第一次循环，`i = 0`，`ptshift = 18` |

PTE 的 `V` 有效，`R/W/X` 不全为零，说明它直接是叶子项；`A/D` 也已经置位。它把高地址的 1 GiB 虚拟区间映射到从 `0x80000000` 开始的物理区间。因此，这次查询在根页表就结束，不需要继续读取下两级页表。

对于这种大页，物理地址除了 PTE 中的高位页号，还要结合虚拟地址中低层页号对应的偏移。最终得到物理页基址 `0x80207000`，再加原地址低 12 位的 `0x10`，得到本次读取的字节物理地址 `0x80207010`，与固定偏移换算一致。


#### 页表查询中的关键分支

结合 QEMU 4.1.1 的 `target/riscv/cpu_helper.c`，`get_physical_address()` 的主要判断如下。表中未命中的错误分支来自源码分析，本次加载实际走的是有效叶子项路径。

| 判断 | 处理及含义 |
| --- | --- |
| 有效访问特权为 M 模式、无 MMU，或分页模式为 Bare | 直接返回恒等映射；数据访问需先考虑 `MPRV/MPP` 对有效特权的影响 |
| Sv39 地址高位不是第 38 位的符号扩展 | 返回转换失败，不继续查表 |
| `!(pte & PTE_V)` | 页表项无效，返回转换失败 |
| `!(pte & (PTE_R \| PTE_W \| PTE_X))` | 当前项指向下一级页表，用 `ppn << 12` 更新 `base`，继续循环；若最终仍没有叶子项，则转换失败 |
| `W=1` 且 `R=0` | 保留的叶子权限组合，返回转换失败 |
| 叶子项的特权、读写执行权限或大页物理对齐不满足要求 | 返回转换失败；读权限判断还需结合 `MXR`，S 模式对用户页的访问需结合 `SUM` |
| 合法叶子项 | 必要时更新 `A/D`，组合 PTE 高位页号与虚拟地址的低层页号，返回物理页基址和权限 |

每次读取 PTE 前会检查其物理地址的 PMP 访问权限；转换成功后，`riscv_cpu_tlb_fill()` 还会检查目标物理访问的 PMP 权限，通过后才建立 TLB 项。转换失败时，探测调用返回失败，普通访存则进入对应的异常处理路径。本次 PTE 为 `0x200000cf`，有效、可读写、`A/D` 已置位且大页对齐满足要求，因此无需更新 PTE，在第一次循环中返回成功。

#### TLB 查询、填充与命中

QEMU 的 TLB 查询既包括生成的快速访存代码，也包括慢路径中的补充检查。在 x86 代码生成后端，`tcg_out_tlb_load()` 生成索引计算、地址标记比较及命中后的地址调整；未命中时转入加载辅助函数。在 `cputlb.c` 中，`load_helper()` 还会检查主 TLB 和 victim TLB，仍未命中时才调用架构相关的填充函数。 具体分支是主项 `!tlb_hit(tlb_addr, addr)` 后继续判断 `!victim_tlb_hit(...)`，两者都未命中才进入 `tlb_fill()`。`tcg_out_tlb_load()` 在翻译指令时生成快速路径机器码，后续命中时执行这些机器码，不会每次调用这个 C 函数。

本次填充后的软件 TLB 读标记是 `0xffffffffc0207000`。QEMU 将这里的转换缓存为 4 KiB 粒度的项，尽管内核页表采用的是 1 GiB 叶子映射。该项还保存 `addend`，用客户虚拟地址加上它得到 QEMU 进程中的内存地址，后者与被模拟系统的物理地址属于不同的地址空间。

两次读取的实际记录为：

```text
BEFORE SECOND LOAD: slow=1 fill=1
AFTER SECOND LOAD:  slow=1 fill=1
```

两条指令都读到 `0x24141322411185`。第二次读取没有再次进入加载慢路径和 TLB 填充函数，结合缓存标记与返回值，可以验证它复用了第一次建立的转换。


#### 与 Bare 模式的对照

在内核尚未开启分页时，对 `0x80200000` 的取指进行调试，观察到：

```text
BARE: addr=0x80200000 satp=0 mmu_idx=1
BARE_PA=0x80200000
BARE_TLB_FILL: va=0x80200000 pa=0x80200000 mmu_idx=1
```

此时没有页表遍历，输入地址按恒等关系得到客户物理地址，但 QEMU 仍调用了 `tlb_set_page()`。这说明模拟器的软件 TLB 还服务于客户地址到 QEMU 进程内存的访问加速，并不是硬件页表翻译缓存的逐项照搬。真实硬件 TLB 的核心职责是缓存地址转换及权限；QEMU 软件 TLB 还带有进程内地址调整和内存访问路径信息。

这组 Bare 对照观察的是取指，前面的 Sv39 测试观察的是数据加载，用来比较转换路径，不据此比较两种模式的访存性能。

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
buddy_check() succeeded! (rounding, split, merge, exhaustion, unaligned range)
mmu_probe() succeeded!
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

### 5.3 Buddy 与双 GDB 检查

默认 Best-Fit 启动执行 Buddy 隔离池测试；使用 `make PMM=buddy qemu` 切换为 Buddy，真实页池分配与回收检查通过。两种配置均使用 128 MiB RAM。

页表调试脚本完成两次同地址读取及 Bare 对照。两次读取均得到 `0x24141322411185`，第二次读取后慢路径和填充计数仍为 1。

- [Buddy 启动日志](../code/evidence/qemu-buddy-128M.log)
- [双 GDB 调试结果](../code/evidence/mmu-live/result.json)
- [RISC-V GDB 记录](../code/evidence/mmu-live/guest-gdb.log)
- [QEMU 源码 GDB 记录](../code/evidence/mmu-live/host-gdb.log)
- [Bare 模式记录](../code/evidence/mmu-live/bare-host-gdb.log)

-----

## 六、实验总结与收获

### 对操作系统的理解

| 本实验知识点 | 对应的 OS 原理及联系 |
| --- | --- |
| 物理页描述符与保留区域 | 内存管理首先要明确资源边界；管理数据本身也占用资源，不能把它覆盖的页面再次分配 |
| First-Fit 与 Best-Fit | 都在连续空闲块中选择可用区域，选择策略影响查找开销和外部碎片，及时合并相邻块是两者共同需要的机制 |
| Buddy 拆分与合并 | 用二次幂大小和地址对齐规则简化块管理，代价是请求取整造成内部碎片 |
| Sv39 页表与大页 | 页表项不一定指向下一级；本次根页表的叶子项直接映射 1 GiB，体现了大页减少查询层级的作用 |
| TLB 与地址转换 | 缓存可以避免重复页表查询；通过 QEMU 实现还能看到客户物理地址、QEMU 进程内地址与模拟器缓存之间的区别 |

本实验虽然开启了分页，但主要使用固定的启动映射，还没有实现完整的进程虚拟地址空间管理。按需分页、缺页处理与换页、写时复制、进程间隔离，以及多核环境下的分配同步和 TLB 一致性，都没有在本次实验中完成。

-----

## 参考资料

1. [课程实验指导：实验二练习要求](http://oslab.mobisys.top/lab2026/_book/lab2/lab2_2_1_exercise.html)。
2. [课程实验指导：物理内存探测](http://oslab.mobisys.top/lab2026/_book/lab2/lab2_3_5_2_search_phymem_layout.html)。
3. [课程实验指导：页表与 TLB 调试](http://oslab.mobisys.top/lab2026/_book/lab2/lab2_4_qemu_mmu_debug.html)。
