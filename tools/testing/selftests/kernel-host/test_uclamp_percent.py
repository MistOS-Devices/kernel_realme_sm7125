#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Exercise the real cgroup parser and uclamp percentage conversion."""
from test_helpers import function_body, run_c
code = r'''
#include <assert.h>
#include <ctype.h>
#include <errno.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
typedef long long s64;
typedef unsigned long long u64;
#define SCHED_CAPACITY_SCALE 1024
#define SCHED_CAPACITY_SHIFT 10
#define UCLAMP_PERCENT_SHIFT 2
#define UCLAMP_PERCENT_SCALE 10000
#define DIV_ROUND_CLOSEST_ULL(a,b) (((a)+(b)/2)/(b))
struct uclamp_request {s64 percent; u64 util; int ret;};
static char *strim(char *s) {
 while (isspace((unsigned char)*s)) s++;
 char *end=s+strlen(s); while(end>s && isspace((unsigned char)end[-1])) *--end=0;
 return s;
}
'''
for sig,path,name in [
 ('u64 power_of_ten(int power)','kernel/cgroup/cgroup.c','power_of_ten'),
 ('int cgroup_parse_float(const char *input, unsigned dec_shift, s64 *v)','kernel/cgroup/cgroup.c','cgroup_parse_float'),
 ('struct uclamp_request capacity_from_percent(char *buf)','kernel/sched/core.c','capacity_from_percent'),
]:
 if name == 'cgroup_parse_float':
  code += '\n#pragma GCC diagnostic push\n#pragma GCC diagnostic ignored \"-Wsign-compare\"\n'
 code += '\nstatic '+sig+'\n'+function_body(path,name)
 if name == 'cgroup_parse_float': code += '\n#pragma GCC diagnostic pop\n'
code += r'''
static struct uclamp_request parse(const char *s) {
 char buf[128]; strcpy(buf,s); return capacity_from_percent(buf);
}
int main(void) {
 assert(!parse("12.50").ret && parse("12.50").util==128);
 assert(!parse("6.25").ret && parse("6.25").util==64);
 assert(parse("0").util==0 && parse("100").util==1024);
 assert(parse(" max\n").util==1024 && parse("12.345").percent==1235);
 const char *bad[]={"", "bad", "-1", "-0.5", "101", "1x", "12..5", "1.2junk", "99999999999999999999999999", "0.000000000000000000000000000000"};
 for (unsigned i=0;i<sizeof(bad)/sizeof(bad[0]);i++) assert(parse(bad[i]).ret<0);
 puts("PASS: uclamp percentages, whitespace, rounding and malformed/overflow input");
}
'''
run_c(code)
