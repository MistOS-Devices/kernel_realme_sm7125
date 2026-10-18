#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Exercise the production ext4 fsync barrier and its error propagation."""
from test_helpers import function_body, run_c

body = function_body('fs/ext4/fsync.c', 'ext4_sync_file')
barrier = body[body.index('if (needs_barrier)'):body.index('\nout:')]
run_c(r'''
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#define GFP_KERNEL 0
struct super_block { void *s_bdev; } sb;
struct inode { struct super_block *i_sb; } inode_data = { &sb };
static bool nonrot, durable;
static int flush_error;
static void *bdev_get_queue(void *bdev) { return bdev; }
static bool blk_queue_nonrot(void *queue) { return nonrot; }
static int blkdev_issue_flush(void *bdev, int gfp, void *sector) {
    durable = !flush_error;
    return flush_error;
}
static void blkdev_issue_flush_nowait(void *bdev, int gfp) {}
static int fsync_barrier(int ret, bool needs_barrier) {
    struct inode *inode = &inode_data;
    int err;
    if (!needs_barrier)
        goto issue_flush; /* The no-journal barrier path. */
''' + barrier + r'''
    return ret;
}
int main(void) {
    for (int disk = 0; disk < 2; disk++) {
        nonrot = disk;
        for (int journal = 0; journal < 2; journal++) {
            durable = false; flush_error = 0;
            assert(fsync_barrier(0, journal) == 0 && durable);
            flush_error = -5;
            assert(fsync_barrier(0, journal) == -5);
            assert(fsync_barrier(-28, journal) == -28);
        }
    }
    puts("PASS: ext4 fsync waits for the barrier and preserves errors");
}
''')
