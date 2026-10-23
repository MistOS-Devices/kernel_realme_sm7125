# SPDX-License-Identifier: GPL-2.0
"""Catch chunk-boundary confusion when freeing swap-shadow ranges."""
from test_helpers import function_body, run_c

run_c(r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define __rcu
#define SWAP_ADDRESS_SPACE_SHIFT 6
typedef struct { unsigned long val; } swp_entry_t;
struct radix_tree_iter { unsigned long index, next_index; };
struct tree { void *slots[128]; unsigned long limit; };
struct address_space { int tree_lock; struct tree page_tree; } spaces[2];
static swp_entry_t swp_entry(int type,unsigned long offset) { return (swp_entry_t){offset}; }
static struct address_space *swap_address_space(swp_entry_t e) { assert(e.val<128); return &spaces[e.val>>6]; }
static void spin_lock_irq(int *lock) {}
static void spin_unlock_irq(int *lock) {}
static void **next_slot(struct tree *root,struct radix_tree_iter *it,unsigned long start) {
 for(unsigned long i=start;i<root->limit;i++)if(root->slots[i]) {
  it->index=i; it->next_index=(i/64+1)*64; return &root->slots[i];
 }
 return NULL;
}
#define radix_tree_for_each_slot(slot,root,it,start) \
 for((slot)=next_slot(root,it,start); (slot); (slot)=next_slot(root,it,(it)->index+1))
static void *radix_tree_deref_slot_protected(void **slot,int *lock) { return *slot; }
static bool radix_tree_exceptional_entry(void *p) { return (uintptr_t)p&2; }
static void radix_tree_iter_delete(struct tree *root,struct radix_tree_iter *it,void **slot) { *slot=NULL; }
static void clear_shadow_from_swap_cache(int type,unsigned long begin,unsigned long end)
''' + function_body('mm/swap_state.c', 'clear_shadow_from_swap_cache') + r'''
int main(void) {
 spaces[0].page_tree.limit=64; spaces[1].page_tree.limit=128;
 for(int i=1;i<=11;i++)spaces[0].page_tree.slots[i]=(void *)2;
 clear_shadow_from_swap_cache(0,1,10);
 for(int i=1;i<=10;i++)assert(!spaces[0].page_tree.slots[i]);
 assert(spaces[0].page_tree.slots[11]==(void *)2);
 spaces[0].page_tree.slots[7]=(void *)2;
 clear_shadow_from_swap_cache(0,3,5);
 assert(spaces[0].page_tree.slots[7]==(void *)2);
 spaces[0].page_tree.slots[62]=spaces[0].page_tree.slots[63]=(void *)2;
 spaces[1].page_tree.slots[64]=spaces[1].page_tree.slots[66]=spaces[1].page_tree.slots[67]=(void *)2;
 spaces[1].page_tree.slots[65]=(void *)4; /* resident page, not a shadow */
 clear_shadow_from_swap_cache(0,62,66);
 assert(!spaces[0].page_tree.slots[62] && !spaces[0].page_tree.slots[63]);
 assert(!spaces[1].page_tree.slots[64] && !spaces[1].page_tree.slots[66]);
 assert(spaces[1].page_tree.slots[65]==(void *)4 && spaces[1].page_tree.slots[67]==(void *)2);
 puts("PASS: swap-shadow cleanup covers whole ranges, preserves resident/out-of-range slots");
}
''')
