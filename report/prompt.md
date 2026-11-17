# Lab4 提示词汇总

小组成员：国轩 2414132、孟子玉 2411963、韩东儒 2411185。

本实验共使用以下 7 份提示词，按课程四段式组织，并与报告对应模块保持一致。执行位置为 `lab4` 交付目录，源码位于 `code/`。先完成 P1、P2，再完成 P3、P4；P5、P6 依赖 P1 的页表检查，P7 最后执行。下列相对路径均以交付目录为基准。

各提示词以源码、编译和实际运行记录判断结果。

## P1 前序物理内存管理与 Best-Fit 衔接

负责人：国轩 2414132。

```text
[PROMPT]
任务：补全 code/kern/mm/{pmm.c,default_pmm.c} 的 lab2 位置，使内核完成物理内存初始化并接入 Best-Fit。
操作：修改实际文件，注释署 2414132；保留 lab4 的页表检查、中断保护和 basic_check/best_fit_check。
输出：说明迁移点、lab4 适配方式和编译启动结果；使用 QEMU 4.1.1。

[RELY]
读取 code/kern/mm/{pmm.h,memlayout.h,mmu.h}、code/kern/driver/dtb.h 与 code/libs/list.h。get_memory_base/get_memory_size 提供 DTB 内存范围；pages[i] 对应页号 nbase+i，npage 是页号上界；lab4 的可管理上界为 KERNTOP - PHYSICAL_MEMORY_OFFSET，Page 含 pra_page_link/pra_vaddr。

[GUARANTEE]
实现 static void page_init(void)；
实现 Best-Fit 的 init/init_memmap/alloc_pages/free_pages/nr_free_pages，注册 const struct pmm_manager default_pmm_manager，保留原有两个测试函数。

[SPECIFICATION]
page_init：Pre 为 DTB 已解析、PMM 已初始化；Post 为 va_pa_offset、npage、pages 正确，固件/内核/描述符数组和尾部不完整页不进入空闲区。
Case：基址非 DRAM_BASE、零长度、地址溢出、描述符放不下时 panic；无完整空闲页时不调用 init_memmap。
Best-Fit：按地址维护空闲块；注册/释放计数并合并相邻块；分配选最小合适块，等大取低地址；无合适块返回 NULL 且状态不变；n==0 断言拒绝。
Requirements：保留 lab4 的 Page 字段初始化和外层中断保护。
```

## P2 虚拟内存页操作

负责人：国轩 2414132。

```text
[PROMPT]
任务：补全 code/kern/mm/pmm.c 的 LAB4 function1 位置，实现 page_insert/page_remove。
操作：修改实际文件，注释署 2414132；保留 get_pte、测试函数和公开接口，允许 static 辅助函数。
输出：说明引用计数、旧映射覆盖和 TLB 失效处理，并给出 check_pgdir 结果。

[RELY]
读取 code/kern/mm/{pmm.c,pmm.h,memlayout.h}。get_pte 定位页表项并按 create 分配中间页表；Page 的 ref 是引用计数；check_pgdir 会先映射 p1→0x0、p2→PGSIZE，再把 p1 重映射到 PGSIZE，最后删除并检查引用计数与空闲页数。

[GUARANTEE]
int page_insert(pde_t *pgdir, struct Page *page, uintptr_t la, uint32_t perm);
void page_remove(pde_t *pgdir, uintptr_t la);
允许 static page_remove_pte 辅助函数。

[SPECIFICATION]
page_insert：Pre 为 pgdir 有效；Post 为 la 映射到 page，权限为 perm，引用计数正确，TLB 失效。
Case 1：原映射同一 page：不重复增引用，只更新权限。
Case 2：原映射其他 page：撤销旧映射、减旧页引用，必要时释放，再建新映射。
Case 3：原无有效映射：直接建立。
Case 4：get_pte 分配失败：返回 -E_NO_MEM，不留半完成映射。
page_remove：有映射时清 PTE、减引用、必要时释放并失效 TLB；无映射时安静返回，可重复调用。
Requirements：不泄漏页表页；不修改 get_pte 和框架测试。
```

## P3 进程创建与初始化

负责人：孟子玉 2411963。

```text
[PROMPT]
任务：补全 code/kern/process/proc.c 的 LAB4 function2 位置，实现内核线程创建与初始化。
操作：修改实际文件，注释署 2411963；保留 forkret、setup_kstack、put_kstack、get_pid、hash_proc 等框架函数。
输出：说明 PCB 初始状态、idleproc/initproc 创建过程和首次运行上下文，并给出进程创建测试结果。

[RELY]
读取 code/kern/process/{proc.c,proc.h}、code/kern/trap/trap.h 与 code/kern/mm/memlayout.h。KSTACKPAGE=2、KSTACKSIZE=8 KiB；内核线程共享 boot_pgdir_pa；context 保存 ra、sp、s0~s11。

[GUARANTEE]
static struct proc_struct *alloc_proc(void);
void proc_init(void);
int kernel_thread(int (*fn)(void *), void *arg, uint32_t clone_flags);
int do_fork(uint32_t clone_flags, uintptr_t stack, struct trapframe *tf);
static void copy_thread(struct proc_struct *proc, uintptr_t esp, struct trapframe *tf);
static int copy_mm(uint32_t clone_flags, struct proc_struct *proc);

[SPECIFICATION]
alloc_proc：返回清零 PCB；state=UNINIT、pid=-1、其余字段清零、pgdir=boot_pgdir_pa、链表已初始化；失败返回 NULL。
proc_init：初始化 proc_list/hash_list；创建 idleproc（pid 0、RUNNABLE、kstack=bootstack、need_resched=1、current=idleproc）；用 kernel_thread 创建 initproc（pid 1）。
kernel_thread：清零 trapframe；s0=fn、s1=arg、epc=kernel_thread_entry；status 置 SPP/SPIE、清 SIE；调用 do_fork。
do_fork：alloc_proc→setup_kstack→copy_mm→copy_thread→分配 pid、挂 hash/proc_list→wakeup_proc；返回 pid，失败回收。
copy_thread：内核栈顶放 trapframe，a0=0；esp==0 时 sp=tf；context.ra=forkret、context.sp=tf。
copy_mm：内核线程 proc->mm=NULL，返回 0。
Requirements：idleproc 复用当前现场；不改已有 forkret/setup_kstack/get_pid/hash_proc。
```

## P4 调度与上下文切换

负责人：韩东儒 2411185。

```text
[PROMPT]
任务：补全 code/kern/{schedule/sched.c,process/proc.c,process/switch.S} 的 LAB4 function3 位置，实现调度与上下文切换。
操作：修改实际文件，注释署 2411185；schedule/proc_run 使用现有中断保护，switch.S 只保存/恢复寄存器。
输出：说明调度规则、页表切换和首次运行链路，并给出 Schedule 测试结果。

[RELY]
读取 code/kern/process/{proc.c,proc.h,switch.S}、code/kern/schedule/sched.c 与 code/kern/mm/pmm.h。proc_list 保存可调度线程；struct context 含 ra、sp、s0~s11；satp 切换和 flush_tlb 可参考 pmm.c 的 enable_paging()。

[GUARANTEE]
在 proc.c 实现 void cpu_idle(void)、void proc_run(struct proc_struct *proc)；
在 sched.c 实现 void schedule(void)；
在 switch.S 实现 void switch_to(struct context *from, struct context *to)。

[SPECIFICATION]
cpu_idle：循环检查 current->need_resched，置位时调用 schedule。
schedule：清 need_resched；从 proc_list 选下一个 RUNNABLE；当前非 idle 从当前下一个开始，当前为 idle 从链表头开始；找不到回退 idleproc；next->runs++；next!=current 时 proc_run。
proc_run：proc!=current 时在临界区更新 current、切换 satp 到 next->pgdir、flush_tlb、switch_to。
switch_to：只保存/恢复 ra、sp、s0~s11，不参与调度判断。
Requirements：调度和切换在关中断临界区内完成；不修改进程状态机和 PCB 字段。
```

## P5 Trap 入口与上下文恢复

负责人：国轩 2414132。

```text
[PROMPT]
任务：补全 code/kern/trap/trapentry.S 的 lab3 位置，使 Trap 能进入 C 处理函数并恢复返回。
操作：修改实际文件，注释署 2414132；保持 SAVE_ALL、trapframe 布局和 trap 签名不变。
输出：说明布局对应和返回状态，记录实际编译结果，并给出 Trap 测试结果。

[RELY]
读取 code/kern/trap/{trapentry.S,trap.h,trap.c} 与 code/libs/riscv.h。SAVE_ALL 是保存布局依据；原始 sp 经 sscratch 写入 x2，lab4 不保存 x0；采用 RISC-V 调用约定和 sret 返回机制。

[GUARANTEE]
补全 RESTORE_ALL；
在 __alltraps 中把当前 frame 地址传给 trap()。
允许只新增必要的汇编别名。

[SPECIFICATION]
RESTORE_ALL：Pre 为 sp 指向有效 frame；Post 为 sstatus/sepc、x1/x3~x31 恢复，x2 最后恢复；不读 x0 槽位。
__alltraps：Pre 为内核栈有效；Post 为 trap 收到正确 tf，返回后同一 frame 可恢复；tf->epc 被修改时返回新地址。
Requirements：先恢复 CSR 再恢复通用寄存器；保持 16 字节栈对齐；只处理内核态 Trap。
```

## P6 中断与异常处理

负责人：孟子玉 2411963。

```text
[PROMPT]
任务：补全 code/kern/trap/trap.c 的 lab3 位置，实现 interrupt_handler 和 exception_handler。
操作：修改实际文件，注释署 2411963；保留 trap()、print_trapframe 等已有函数和签名。
输出：说明时钟续设、ticks 计数、关机条件和异常返回位置，并给出 Trap 测试结果。

[RELY]
读取 code/kern/trap/trap.c、code/kern/driver/clock.{c,h} 与 code/libs/{riscv.h,sbi.h}。依赖 trapframe、ticks、TICK_NUM、原因宏、clock_set_next_event、print_trapframe 和 sbi_shutdown。

[GUARANTEE]
void interrupt_handler(struct trapframe *tf);
void exception_handler(struct trapframe *tf);

[SPECIFICATION]
interrupt_handler：按去掉最高位的原因号分发；S 时钟每次续设事件、ticks 恰增一次；每 TICK_NUM 次打印；累计 SHUTDOWN_AFTER 次后 sbi_shutdown；其他类型输出提示；未知类型打印原因和 frame；不推进 epc。
exception_handler：非法指令/断点输出规定格式；读取首半字，低两位为 3 则 epc+=4，否则 epc+=2；其他异常打印 frame，不推进 epc。
Requirements：不实现用户态、缺页恢复或设备驱动；不假定异常指令都是 4 字节。
```

## P7 编译、启动、评分与 Trap 补充验证

负责人：韩东儒 2411185。

```text
[PROMPT]
任务：验证 lab4 实现，覆盖 PMM、进程创建、调度、Trap 与时钟。
操作：使用 QEMU 4.1.1 和工程 Makefile；探针只放临时副本，不修改工作源码，不输出虚假 PASS。
输出：保存构建、启动、make grade 和 Trap 探针日志；失败时保留现场。

[RELY]
读取 code/Makefile、code/tools/{inject.py,grade.sh,test_lab4.c} 与 code/kern/{trap,process,schedule}。已有 alloc_page/free_page、page_insert/page_remove、kernel_thread/schedule、ticks 和 Trap 处理函数。

[GUARANTEE]
在 code/tools 提供 check_trap.py、check_memory.sh，日志写入 code/evidence/；临时副本验证结束后不留在正式源码。

[SPECIFICATION]
Case 1：make clean && make 成功，QEMU 正常启动，检查 Best-Fit、check_pgdir、check_vmm 和 initproc 输出。
Case 2：make grade 三项全部通过，总分 30/30。
Case 3：分别以 64/128/256 MiB 启动，检查初始化与上界截断。
Case 4：临时副本触发 ebreak、16/32 位非法指令，等待 100 ticks 检查继续运行，并等待到关机阈值检查正常退出。
Requirements：记录 QEMU/GCC 版本、退出码和完整日志；失败时保留现场。
```

