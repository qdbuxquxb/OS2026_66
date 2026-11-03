# Lab3 提示词汇总

小组成员：国轩 2414132、孟子玉 2411963、韩东儒 2411185。

本文件汇总实验二代码衔接、Trap 入口与恢复、中断与异常处理，对应 P1～P3。源码路径相对于 `lab3` 分支根目录。

## P1 前序物理内存管理衔接

负责人：国轩 2414132。

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

## P2 Trap 上下文恢复与入口

负责人：国轩 2414132。

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

## P3 中断与异常处理

负责人：孟子玉 2411963。

```text
[PROMPT]
任务：在 code/kern/trap/trap.c 的 lab3 位置实现中断与异常处理。
操作：修改实际文件，注释署 2411963；保留已有函数和签名，只加必要 include/常量，不改官方测试。
输出：用 QEMU 4.1.1 检查运行行为并记录结果；SHUTDOWN_AFTER 未定义时取 10，并说明这一选择。

[RELY]
读取 trap.h、driver/clock.{c,h}、libs/{riscv.h,sbi.h}。依赖 trapframe、ticks、TICK_NUM、原因宏、clock_set_next_event、print_ticks、print_trapframe、sbi_shutdown。

[GUARANTEE]
实现 void interrupt_handler(struct trapframe *tf) 和 void exception_handler(struct trapframe *tf)。

[SPECIFICATION]
interrupt_handler：Pre 为有效 frame；Post 为按去掉中断标志的原因号分发。每次 IRQ_S_TIMER 都安排后续事件且 ticks 恰增一次，每 TICK_NUM 次打印一次统计，累计 SHUTDOWN_AFTER 次统计后关机；不推进 epc。
Case：U/S/M 的软件、定时器、外部中断输出相应类型提示，S 定时器执行上述逻辑。未知类型打印 Unknown interrupt: cause %lu 并输出 frame；S 软件提示为 Supervisor software interrupt。
exception_handler：Pre 为有效 frame，待跳过的指令位于可读内核映射；非法指令输出 Illegal instruction at 0x%016lx\n，断点输出 Breakpoint at 0x%016lx\n；随后按目标支持的 16/32 位编码推进 epc，返回后不重复执行该指令。
Case：其他异常只输出 frame，不推进 epc，不声称恢复成功。
Requirements：不实现用户态、缺页恢复或设备驱动，不假定所有异常指令都长 4 字节。
```
