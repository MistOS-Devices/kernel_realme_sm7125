#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Exercise production manual KProfiles ABI and creation cleanup."""
from test_helpers import ROOT, function_body, run_c
code=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <errno.h>
#include <limits.h>
#include <string.h>
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x,v) ((x)=(v))
#define PAGE_SIZE 4096
#define scnprintf snprintf
struct kobject {int unused;}; struct kobj_attribute {int unused;};
static unsigned int kp_mode;
static struct kobject obj, *kp_kobj, *kernel_kobj;
static int kp_attr_group, fail_create, fail_group, puts_count, removes;
static struct kobject *kobject_create_and_add(const char *name, struct kobject *parent) { return fail_create ? NULL : &obj; }
static int sysfs_create_group(struct kobject *k, int *g) { return fail_group ? -ENOMEM : 0; }
static void sysfs_remove_group(struct kobject *k, int *g) { removes++; }
static void kobject_put(struct kobject *k) { puts_count++; }
static int kstrtouint(const char *buf, unsigned int base, unsigned int *value) {
 char *end; errno=0; if(*buf=='-') return -EINVAL;
 unsigned long v=strtoul(buf,&end,base);
 if(errno || v>UINT_MAX) return -ERANGE;
 if(end==buf || (*end && strcmp(end,"\n"))) return -EINVAL;
 *value=v; return 0;
}
'''
for sig,name in [
 ('int kp_active_mode(void)','kp_active_mode'),
 ('int kp_set_mode(unsigned int level)','kp_set_mode'),
 ('ssize_t kp_mode_show(struct kobject *kobj, struct kobj_attribute *attr, char *buf)','kp_mode_show'),
 ('ssize_t kp_mode_store(struct kobject *kobj, struct kobj_attribute *attr, const char *buf, size_t count)','kp_mode_store'),
 ('int kp_init(void)','kp_init'),('void kp_exit(void)','kp_exit')]:
 code+='\nstatic '+sig+'\n'+function_body('drivers/misc/kprofiles/main.c',name)
code+=r'''
int main(void) {
 char buf[32]; assert(kp_active_mode()==0);
 for(unsigned int i=0;i<4;i++) { assert(!kp_set_mode(i)); assert(kp_active_mode()==(int)i); }
 assert(kp_set_mode(4)==-EINVAL && kp_active_mode()==3);
 assert(kp_set_mode(UINT_MAX)==-EINVAL && kp_active_mode()==3);
 const char *bad[]={"-1","4","junk","1junk","4294967296","9999999999999999999999"};
 for(unsigned i=0;i<sizeof(bad)/sizeof(bad[0]);i++) {
  assert(kp_mode_store(NULL,NULL,bad[i],strlen(bad[i]))<0); assert(kp_active_mode()==3);
 }
 assert(kp_mode_store(NULL,NULL,"2\n",2)==2 && kp_active_mode()==2);
 assert(kp_mode_show(NULL,NULL,buf)==2 && !strcmp(buf,"2\n"));
 fail_create=1; assert(kp_init()==-ENOMEM && puts_count==0);
 fail_create=0; fail_group=1; assert(kp_init()==-ENOMEM && puts_count==1);
 fail_group=0; assert(!kp_init()); kp_exit(); assert(puts_count==2 && removes==1);
 puts("PASS: manual KProfiles validated ABI, state and sysfs creation cleanup");
}
'''
run_c(code)
header=(ROOT/'include/linux/kprofiles.h').read_text()
import re
header=re.sub(r'^#include.*$', '', header, flags=re.M)
run_c('#include <assert.h>\n#include <errno.h>\n#include <limits.h>\n'+header+r'''
int main(void) { assert(kp_active_mode()==0); assert(kp_set_mode(1)==-ENODEV); }
''')
print('PASS: KProfiles config-off API remains inert')
