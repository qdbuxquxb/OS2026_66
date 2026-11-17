#include <console.h>
#include <defs.h>
#include <stdio.h>

/* HIGH level console I/O */

/* *
 * cputch - writes a single character @c to stdout, and it will
 * increace the value of counter pointed by @cnt.
 * */
<<<<<<< Updated upstream:code/lab1/kern/libs/stdio.c
static void cputch(int c, int *cnt) {
=======
static void
cputch(int c, int *cnt)
{
>>>>>>> Stashed changes:code/kern/libs/stdio.c
    cons_putc(c);
    (*cnt)++;
}

/* *
 * vcprintf - format a string and writes it to stdout
 *
 * The return value is the number of characters which would be
 * written to stdout.
 *
 * Call this function if you are already dealing with a va_list.
 * Or you probably want cprintf() instead.
 * */
<<<<<<< Updated upstream:code/lab1/kern/libs/stdio.c
int vcprintf(const char *fmt, va_list ap) {
=======
int vcprintf(const char *fmt, va_list ap)
{
>>>>>>> Stashed changes:code/kern/libs/stdio.c
    int cnt = 0;
    vprintfmt((void *)cputch, &cnt, fmt, ap);
    return cnt;
}

/* *
 * cprintf - formats a string and writes it to stdout
 *
 * The return value is the number of characters which would be
 * written to stdout.
 * */
<<<<<<< Updated upstream:code/lab1/kern/libs/stdio.c
int cprintf(const char *fmt, ...) {
=======
int cprintf(const char *fmt, ...)
{
>>>>>>> Stashed changes:code/kern/libs/stdio.c
    va_list ap;
    int cnt;
    va_start(ap, fmt);
    cnt = vcprintf(fmt, ap);
    va_end(ap);
    return cnt;
}

/* cputchar - writes a single character to stdout */
<<<<<<< Updated upstream:code/lab1/kern/libs/stdio.c
void cputchar(int c) { cons_putc(c); }

/* *
 * cputs- writes the string pointed by @str to stdout and
 * appends a newline character.
 * */
int cputs(const char *str) {
    int cnt = 0;
    char c;
    while ((c = *str++) != '\0') {
        cputch(c, &cnt);
    }
    cputch('\n', &cnt);
    return cnt;
}

/* getchar - reads a single non-zero character from stdin */
int getchar(void) {
=======
void cputchar(int c)
{
    cons_putc(c);
}

/* getchar - reads a single non-zero character from stdin */
int getchar(void)
{
>>>>>>> Stashed changes:code/kern/libs/stdio.c
    int c;
    while ((c = cons_getc()) == 0) /* do nothing */;
    return c;
}
