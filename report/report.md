# 操作系统实验报告

## 实验基本信息

| 项目 | 内容 |
| --- | --- |
| **实验名称** | Lab 3：断，都可以断（中断与异常处理） |
| **小组成员** | 2414132-国轩、2411963-孟子玉、2411185-韩东儒 |
| **完成日期** | 2026-11-02 |

### 小组分工

| 成员 | 实验任务 | 报告任务 |
| --- | --- | --- |
| 2414132-国轩 | 衔接实验二的页初始化与 Best-Fit，实现 Trap 上下文恢复及汇编入口，统筹代码整合 | 实验目的、整体逻辑、上下文恢复与入口分析、全文整合 |
| 2411963-孟子玉 | 实现时钟中断、非法指令和断点异常处理，核对 Trap 返回位置 | 中断与异常处理、时钟续设及关机机制、实现问题分析 |
| 2411185-韩东儒 | 分析中断保护接口，整理官方评分及补充测试，核对运行记录 | 实验环境、中断保护、测试与验证 |

实验总结由国轩汇总，孟子玉、韩东儒分别核对中断处理和测试部分。

### 实验文件组织

本实验对应 Git 分支 `lab3`，仓库根目录包含以下两个文件夹：

```text
code/                       实现后的源码、验证脚本及运行日志
report/
├── report.md               实验报告
├── prompt.md               本实验提示词汇总
└── images/                 报告引用的测试截图
```

源码和运行日志分别位于 `code/`、`code/evidence/`，报告、提示词及截图位于 `report/`。

-----

## 一、实验目的

1. 理解 RISC-V 中 Trap、中断和异常的关系，掌握内核识别和分发 Trap 的基本过程。
2. 理解 `stvec`、`sepc`、`scause`、`sstatus` 等寄存器在 Trap 进入与返回时的作用。
3. 根据已有 `SAVE_ALL` 和 `struct trapframe`，实现上下文恢复及汇编入口到 C 语言处理函数的调用。
4. 实现持续的时钟中断处理，以及非法指令、断点异常的识别和返回。
5. 理解保存原中断状态再关闭中断的必要性，并通过实际运行检查寄存器、执行位置和内存分配状态是否正确恢复。

-----

## 二、实验环境

实际验证环境为 Ubuntu 22.04.5 LTS（WSL2，`x86_64`）、`riscv64-unknown-elf-gcc` 15.1.0、QEMU 4.1.1 和 OpenSBI v0.4。QEMU 使用 `virt` 机器，默认内存为 128 MiB，运行单个 hart。

| 项目 | 本次使用情况 |
| --- | --- |
| 实验源码 | `lab3.zip` 提供的实验框架，源码位于 `code/` |
| 编译与链接 | 原工程 Makefile、RISC-V 交叉工具链及链接脚本 |
| 模拟器 | QEMU 4.1.1 |
| 固件 | QEMU 配套的 OpenSBI v0.4，使用 `-bios default` |
| 验证方式 | 内核自检、官方 `make grade`、Python 补充脚本 |

| 成员 | AI 编程工具 | 底层模型 | 备注 |
| --- | --- | --- | --- |
| 2414132-国轩 | Codex（VS Code 插件） | GPT-6 | 辅助分析 Trap frame、实现上下文恢复，整合代码和报告 |
| 2411963-孟子玉 | Claude（VS Code 插件） | DeepSeek-V4-Flash | 辅助实现时钟中断、非法指令与断点异常处理 |
| 2411185-韩东儒 | DeepSeek Harness | DeepSeek-V4-Flash | 辅助分析中断保护，整理补充测试和运行结果 |

启动命令沿用框架的 `-device loader,file=bin/ucore.img,addr=0x80200000`，将内核镜像放入指定物理地址。默认启动日志中可以看到 OpenSBI 版本、设备树内存信息和内核输出。

-----

## 三、实验整体逻辑分析

### 3.1 本章节的逻辑主线

实验一完成了最小内核的启动，实验二建立了物理内存管理。本次实验进一步解决：内核运行过程中发生中断或异常时，怎样暂停原来的执行、处理事件，再回到正确的位置继续运行。

Trap 处理既需要硬件提供入口和状态寄存器，也需要软件保存通用寄存器。处理器进入 S 模式的 Trap 入口时，会记录 `sepc`、`scause` 等状态，并调整 `sstatus` 中的中断使能和来源特权级信息，但不会自动把全部通用寄存器压入内核栈。因此，入口汇编必须先保存执行现场，才能调用可能改写寄存器的 C 函数。

OpenSBI 运行在 M 模式，内核运行在 S 模式。M 模式通过 `mideleg`、`medeleg` 配置中断和异常的委托，受委托的 Trap 交给 S 模式入口处理。内核调用 `sbi_set_timer()` 时，则通过 S 模式的 `ecall` 请求 M 模式固件设置时钟事件。

本次的完整处理链为：

```text
发生 Trap
  → 跳转到 stvec 指向的 __alltraps
  → SAVE_ALL 在当前内核栈上保存 Trap frame
  → 将 Trap frame 地址传给 trap(tf)
  → trap_dispatch() 区分中断和异常
  → 对应 handler 完成处理，必要时调整 tf->epc
  → 返回 __trapret
  → RESTORE_ALL 恢复上下文
  → sret 返回原执行流
```

这里“返回”是否正确，既取决于通用寄存器是否恢复，也取决于 `sepc` 和 `sstatus` 是否正确。时钟中断不应跳过被打断的指令；本实验要求处理后跳过的非法指令和断点指令，则需要根据指令长度更新返回地址。

### 3.2 功能的逐步实现

1. 衔接页初始化和 Best-Fit，保留页分配接口的中断保护。
2. 根据 `SAVE_ALL` 核对 Trap frame，完成 `RESTORE_ALL` 与入口到 `trap()` 的调用。
3. 初始化统一 Trap 入口，运行物理内存自检。

-----

## 四、实验内容与实现

已完成实验二代码衔接和 Trap 入口与上下文恢复，对应提示词 P1、P2，见 [prompt.md](./prompt.md)。

### 4.1 实验二代码衔接

**负责人：** 2414132-国轩

#### 任务提示词（P1）

```text
[PROMPT]
任务：补齐 code/kern/mm/{pmm.c,best_fit_pmm.c} 的 lab2 位置，接入页初始化与默认 Best-Fit；可复用实验二成果。
操作：修改实际文件，保留本次中断保护、原有测试与公开结构；页初始化署 2414132，Best-Fit 沿用 2411963。
输出：说明迁移点、编译结果和未完成的依赖；只用 QEMU 4.1.1，不改官方测试。

[RELY]
读取同目录 pmm.h、memlayout.h、default_pmm.c，以及 driver/dtb.h、libs/list.h。
DTB 提供内存基址和长度；pages[i] 对应页号 nbase+i，npage 为页号上界。宏以本次工程为准。

[GUARANTEE]
实现 static void page_init(void)，补全 best_fit_pmm_manager 所需接口并选为默认；保留 basic_check、best_fit_check。

[SPECIFICATION]
page_init：Pre 为 DTB 已解析、分配器已初始化；Post 为仅剩余完整空闲页被注册，固件、内核、页描述符和尾部不足一页区域不可分配。
Case：无效基址、零长度、溢出或描述符放不下时 panic；没有完整空闲页时不得调用 init_memmap。管理范围不超过 DTB 与框架上界。
Best-Fit：初始化为空；注册/释放准确计数并合并相邻块；正页数请求选择最小合适块，等大取低地址，恰好分配请求页数。无合适连续块时返回 NULL 且状态不变；零页请求断言拒绝。
Requirements：保持原测试对 free_list、nr_free 的状态约定，不覆盖实验三新增的中断保护与原子位操作。
```

#### Spec 与提示词设计

迁移代码时，我们主要考虑可用页面的范围和分配器状态。规格要求排除已占用区域，明确内存信息无效、描述符空间不足时的处理，并保留原测试使用的 `free_list`、`nr_free`。提示词同时要求保留实验三的中断保护，使迁入的分配器与新框架衔接。

实验三的 `code/kern/mm/pmm.c` 和 `best_fit_pmm.c` 留有实验二代码的补充位置。我们迁入页初始化和 Best-Fit 管理函数，并在 `init_pmm_manager()` 中选择 `best_fit_pmm_manager`。

`page_init()` 仍从设备树取得物理内存范围，在内核末端之后安排页描述符数组，将固件、内核和描述符占用的页面排除，只把剩余完整页面交给分配器。实验三没有定义实验二中的 `PHYSICAL_MEMORY_END`，因此改为从现有布局计算管理上界：

```c
uintptr_t limit = KERNTOP - PHYSICAL_MEMORY_OFFSET;
uintptr_t maxpa = mem_end < limit ? mem_end : limit;
```

当前布局计算出的上界仍为 `0x88000000`。随后再按页向下对齐，避免把不完整尾页纳入管理。

迁移时保留了实验三 `alloc_pages()`、`free_pages()` 和 `nr_free_pages()` 外层的 `local_intr_save()`、`local_intr_restore()`。这些保护属于本次框架新增内容，直接用实验二的整个文件覆盖会丢失它们。Best-Fit 原有的 `basic_check()`、`best_fit_check()` 保持不变。

### 4.2 功能模块一：Trap 上下文恢复与入口

**负责人：** 2414132-国轩

#### 任务提示词（P2）

```text
[PROMPT]
任务：补全 code/kern/trap/trapentry.S 的 lab3 位置，使 Trap 能进入 C 处理函数并恢复返回。
操作：修改实际文件，注释署 2414132；保持 SAVE_ALL、trapframe 布局、trap 签名及官方测试不变。
输出：说明布局对应和返回状态，记录实际编译结果；使用 QEMU 4.1.1，其他模块未完成时如实说明。

[RELY]
读取 trapentry.S、trap.h、trap.c 及 code/libs/riscv.h。SAVE_ALL 是保存布局依据；采用 RISC-V 调用约定及 S 模式 Trap 返回机制。

[GUARANTEE]
实现 RESTORE_ALL；补全 __alltraps 到 void trap(struct trapframe *tf) 的调用；处理后经 __trapret 和 sret 返回。

[SPECIFICATION]
RESTORE_ALL：Pre 为 sp 指向有效 Trap frame；Post 为可写整数寄存器恢复，sepc 使用 tf->epc，sstatus 使用保存的返回状态，sp 回到 Trap 前的值。
__alltraps：Pre 为当前内核栈有效；Post 为 trap 收到正确的 frame 地址，C 函数返回后仍能读取同一 frame 并恢复。
Case：处理函数改写 tf->epc 时，返回到新地址；未改写时保持原执行位置。S 模式 Trap 返回仍为 S 模式，不强制清除 SPP。
Requirements：正确处理 x2 的特殊保存方式、栈对齐和调用造成的寄存器变化；不要求用户栈切换。旧 CSR 名称不兼容时，仅加必要汇编别名，不改 SAVE_ALL。
```

#### Spec 与提示词设计

这一模块的规格从 `SAVE_ALL` 已有的保存方式出发，要求 C 函数收到正确的 Trap frame，返回时恢复整数寄存器、栈指针和返回状态。由于原始 `sp` 经由 `sscratch` 保存，提示词中特别要求核对 x2 对应的槽位，并保持汇编布局与 `struct trapframe` 一致。

主要实现文件为 `code/kern/trap/trapentry.S`，填写 `RESTORE_ALL` 和 `__alltraps` 中的指定位置。已有 `SAVE_ALL`、`struct trapframe` 以及 `trap(struct trapframe *tf)` 的签名均保持不变。

#### Trap 入口初始化

框架的 `idt_init()` 将 `sscratch` 清零，并把 `__alltraps` 的地址写入 `stvec`。入口通过 `.align(2)` 保证 4 字节对齐，地址最低两位为 `00`，对应 Direct 模式：交给 S 模式处理的中断和异常统一从 `__alltraps` 进入，再由 C 函数分发。

这种编码也兼容旧版直接保存 4 字节对齐入口地址的方式：旧地址最低两位原本就是零，在加入模式字段后仍表示 Direct 模式。

`kern_init()` 在 `pmm_init()` 前后调用 `idt_init()`，完成页分配自检后进入主循环。当前保留中断与异常的 Trap frame 诊断函数，时钟初始化和使能将在具体处理函数完成后接入。

进入 S 模式 Trap 时，硬件将原 `SIE` 保存到 `SPIE`，清除 `SIE`，并在 `SPP` 中记录来源特权级。`SAVE_ALL` 保存的是这时的 `sstatus`，其中 `SPIE` 保留了返回时需要恢复的中断使能状态。

#### Trap frame 的布局

在 RV64 中，`REGBYTES` 为 8。`SAVE_ALL` 在栈上预留 `36 × 8 = 288` 字节，对应 32 个通用寄存器槽位和 4 个 CSR 槽位。

| 内容 | 相对 Trap frame 起点的偏移 | 作用 |
| --- | --- | --- |
| `x0`～`x31` | `0`～`31 × 8` 字节 | 保存通用寄存器，其中 `x2` 槽位保存 Trap 发生前的栈指针 |
| `status` | `32 × 8 = 256` 字节 | 保存 Trap 入口处的 `sstatus` |
| `epc` | `33 × 8 = 264` 字节 | 保存 `sepc`，供处理函数检查或修改返回位置 |
| `badvaddr` | `34 × 8 = 272` 字节 | 保存 `stval`，框架沿用旧名称 |
| `cause` | `35 × 8 = 280` 字节 | 保存 `scause`，用于识别 Trap 类型 |

`sp` 的处理与其他通用寄存器不同。入口先用 `csrw sscratch, sp` 暂存原始栈指针，再下移 `sp` 分配 Trap frame。随后通过 `csrrw s0, sscratch, x0` 取回原始值，并将 `sscratch` 清零，最后把该值写入 `x2` 对应的槽位。因此，x2 槽位保存进入 Trap 前的 `sp`，当前 `sp` 则指向 Trap frame 的起点。

#### 恢复上下文

`RESTORE_ALL` 先读取并恢复 `sstatus`、`sepc`，再恢复通用寄存器。关键顺序如下：

```asm
LOAD s1, 32*REGBYTES(sp)
LOAD s2, 33*REGBYTES(sp)
csrw sstatus, s1
csrw sepc, s2

# 按保存偏移恢复 x1、x3～x31
# ...
LOAD x2, 2*REGBYTES(sp)
```

先使用 `s1`、`s2` 作为临时寄存器写回 CSR，再从 Trap frame 恢复它们原本的值，可以避免恢复后的寄存器被再次覆盖。`x0` 恒为零，无需加载。

`sp` 必须最后恢复，因为前面的加载都依赖当前栈顶作为 Trap frame 的基址。如果提前恢复 `sp`，后续指令就会从错误位置读数据。最后直接读回原始 `sp`，也就回收了当前 Trap frame 所占的栈空间，无需再额外加 288 字节。

`scause` 和 `stval` 的副本供处理函数读取本次 Trap 的原因及附加信息。返回时写回 `sstatus` 和 `sepc`，分别恢复返回状态和执行位置。

#### 汇编入口调用 C 函数

保存现场后，当前 `sp` 就是 `struct trapframe` 的起始地址。按 RISC-V 调用约定，第一个参数放在 `a0`，因此入口补充：

```asm
mv a0, sp
jal trap
```

此时原来的 `a0` 和 `ra` 已保存在 Trap frame 中，设置参数和调用函数不会丢失被打断程序的值。288 字节也是 16 的整数倍，因此在原栈对齐的前提下，调用 C 函数仍满足栈对齐要求。`trap()` 返回时保持调用前的栈位置，接着执行 `__trapret` 中的恢复和 `sret`。

`sret` 根据 `sstatus.SPP` 决定返回特权级，并将 `SPIE` 中保存的中断使能状态恢复到 `SIE`。本实验处理的 Trap 来自内核 S 模式，保存的 `SPP` 为 1，因此 `sret` 返回后继续在 S 模式运行。框架的 `trap_in_kernel(tf)` 也是通过检查保存的 `SPP` 判断 Trap 是否来自内核。

### 4.3 实现与验证中的问题

**旧 CSR 名称与新版汇编器不兼容。** 首次编译时，汇编器报告 `unknown CSR 'sbadaddr'`。框架沿用旧名称，而该寄存器在当前命名中为 `stval`，编号是 `0x143`。我们在 `code/libs/riscv.h` 中增加仅对汇编生效的 `sbadaddr` 到 `0x143` 的别名，保留了原有 `SAVE_ALL` 的指令和保存布局，再编译通过。

**内存上界宏缺失。** 迁入 `page_init()` 后，编译器指出 `PHYSICAL_MEMORY_END` 未定义。对照实验三的内存布局，改为用 `KERNTOP - PHYSICAL_MEMORY_OFFSET` 计算上界，保持当前管理范围，并保留实验三原有的头文件定义。

-----

## 五、测试与验证

在 `code/` 中使用 QEMU 4.1.1 编译并启动内核，页分配自检通过，显示物理内存范围和启动页表地址后进入主循环。本阶段未开启时钟中断，运行日志中没有时钟统计输出。

```text
memory management: best_fit_pmm_manager
check_alloc_page() succeeded!
```

记录见 [编译日志](../code/evidence/build.log)和[启动日志](../code/evidence/qemu-stage1.log)。测试程序收集到启动结果后终止处于主循环的模拟器。Trap 恢复与入口汇编已通过编译，异常返回与持续时钟的运行检查在处理函数接入后进行。

-----

## 六、实验总结与收获

页初始化使分配器获得可用物理页，统一 Trap 入口则为中断与异常处理准备了执行现场。两部分都依赖准确的地址和布局关系：页描述符需要对应物理页，恢复代码需要对应保存时的栈内偏移。

原始 `sp` 保存在 x2 槽位，恢复时最后读回。结合结构体和汇编逐项检查后，我们理解了 Trap frame 如何连接汇编入口与 C 函数。后续将接入具体处理函数，检查处理后的返回状态。

-----

## 参考资料

1. [课程实验指导：实验三练习要求](http://oslab.mobisys.top/lab2026/_book/lab3/lab3_2_1_exercise.html)。
2. [课程实验指导：中断入口点](http://oslab.mobisys.top/lab2026/_book/lab3/lab3_3_2_trapentry.html)。
3. [课程实验指导：中断处理程序](http://oslab.mobisys.top/lab2026/_book/lab3/lab3_3_3_trap.html)。
4. [课程实验指导：时钟中断](http://oslab.mobisys.top/lab2026/_book/lab3/lab3_3_4_clock.html)。
5. [课程实验指导：中断的关闭和开启](http://oslab.mobisys.top/lab2026/_book/lab3/lab3_3_5_atomic.html)。
6. [课程实验指导：RISC-V 中断介绍](http://oslab.mobisys.top/lab2026/_book/lab3/lab3_3_1_introduce.html)。
