# SPDX-License-Identifier: GPL-2.0
from test_helpers import function_body, run_c

run_c(r'''
#include <assert.h>
#include <stdio.h>
#define ZS_HANDLE_SIZE 8
struct size_class {unsigned int index;};
struct zs_pool {struct size_class *size_class[32];};
static int get_size_class_index(unsigned int size) {return (size+31)/32;}
unsigned int zs_lookup_class_index(struct zs_pool *pool,unsigned int size)
''' + function_body('mm/zsmalloc.c','zs_lookup_class_index') + r'''
int main(void) {
 struct zs_pool p;struct size_class classes[32];
 for(unsigned int i=0;i<32;i++){classes[i].index=i;p.size_class[i]=&classes[i];}
 assert(zs_lookup_class_index(&p,32)==2);
 assert(zs_lookup_class_index(&p,24)==1);
 puts("PASS: ZRAM class comparisons include the allocator handle overhead");
}
''')
