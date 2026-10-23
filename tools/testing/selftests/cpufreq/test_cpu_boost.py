#!/usr/bin/env python3
"""Run the actual touch-boost workers against a refcounted scheduler model."""
import os
import pathlib
import re
import shlex
import subprocess
import tempfile
import sys

root = pathlib.Path(__file__).resolve().parents[4]
source = (root/'drivers/cpufreq/cpu-boost.c').read_text()
sys.path.insert(0, str(root/'tools/testing/selftests/kernel-host'))
from test_helpers import function_body
header = re.sub(r'^#include.*$', '', (root/'include/linux/kprofiles.h').read_text(), flags=re.M)
active = re.search(r'static \w+(?: \w+)? sched_boost_active;', source).group()
workers = source[source.index('static void do_input_boost_rem('):
                 source.index('static void cpuboost_input_event(')]
code = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <limits.h>
typedef unsigned long long u64;
struct input_handle {int unused;};
struct work_struct { int unused; };
struct cpu_sync { unsigned int input_boost_freq, input_boost_min; };
static struct cpu_sync sync_info[2]={{1248000,0},{1555200,0}};
static unsigned int sched_boost_on_input=2, input_boost_ms=80;
static int refs[4], input_boost_rem, cpu_boost_wq, scheduled_ms;
static int mode, input_boost_work, queued, queued_count;
static bool input_boost_enabled=true;
static u64 now_us=1000000, last_input_time;
#define MIN_INPUT_INTERVAL 150000
#define USEC_PER_MSEC 1000
#define min_t(type,a,b) ((type)(a)<(type)(b)?(type)(a):(type)(b))
#define work_pending(p) (queued)
#define queue_work(w,p) ((void)(w),(void)(p),queued=1,queued_count++)
#define ktime_get() (now_us)
#define ktime_to_us(v) (v)
int kp_active_mode(void) { return mode; }
#define READ_ONCE(x) (x)
#define per_cpu(array,i) array[i]
#define for_each_possible_cpu(i) for(i=0;i<2;i++)
#define pr_debug(...) ((void)0)
#define pr_err(...) ((void)0)
#define cancel_delayed_work_sync(p) ((void)(p))
#define msecs_to_jiffies(ms) (ms)
#define queue_delayed_work(w,p,t) ((void)(w),(void)(p),scheduled_ms=(t))
static void update_policy_online(void) {}
static int sched_set_boost(int type) {
 if (type==0) { refs[1]=refs[2]=refs[3]=0; return 0; }
 if (type < -3 || type > 3) return -1;
 if (type>0) refs[type]++;
 else if (refs[-type]) refs[-type]--;
 return 0;
}
'''
code += '\n#define CONFIG_KPROFILES 1\n' + header
workers += '\nstatic void cpuboost_input_event(struct input_handle *handle, unsigned int type, unsigned int code, int value)\n' + function_body('drivers/cpufreq/cpu-boost.c', 'cpuboost_input_event')
main = r'''
int main(void) {
 assert(kp_input_boost_duration(80)==80);
 struct work_struct work={0};
 refs[1]=1; refs[2]=1; /* Other clients' full and conservative boosts. */
 do_input_boost(&work);
 assert(refs[1]==1 && refs[2]==2);
 assert(sync_info[1].input_boost_min==1555200);
 sched_boost_on_input=1; /* Setting changes while our old request is active. */
 do_input_boost(&work);
 assert(refs[1]==2 && refs[2]==1);
 do_input_boost_rem(&work);
 assert(refs[1]==1 && refs[2]==1);
 assert(sync_info[0].input_boost_min==0 && sync_info[1].input_boost_min==0);
 sched_boost_on_input=99; /* Failed requests must not acquire ownership. */
 do_input_boost(&work);
 do_input_boost_rem(&work);
 assert(refs[1]==1 && refs[2]==1);
 sched_boost_on_input=UINT_MAX; /* Must not become a signed disable request. */
 do_input_boost(&work);
 assert(refs[1]==1 && refs[2]==1);
 do_input_boost_rem(&work);
 assert(refs[1]==1 && refs[2]==1);
 sched_boost_on_input=2;
 const unsigned int durations[]={80,40,80,120};
 for(mode=0;mode<4;mode++) {
  do_input_boost(&work); assert(scheduled_ms==(int)durations[mode]);
  do_input_boost_rem(&work);
  assert(refs[1]==1 && refs[2]==1);
 }
 mode=1; cpuboost_input_event(NULL,0,0,0);
 assert(queued_count==1);
 mode=3; do_input_boost(&work); queued=0;
 assert(scheduled_ms==120); /* Pending work samples mode at execution. */
 mode=1; now_us+=19000; cpuboost_input_event(NULL,0,0,0);
 assert(queued_count==1);
 now_us+=1000; cpuboost_input_event(NULL,0,0,0);
 assert(queued_count==2); /* Battery40ms coalesces only20ms. */
 queued=0; do_input_boost_rem(&work);
 input_boost_ms=0; now_us+=1000000; cpuboost_input_event(NULL,0,0,0);
 assert(queued_count==2);
 puts("PASS: boost refresh, expiry and invalid settings preserve other clients");
}
'''
with tempfile.TemporaryDirectory() as tmp:
    path = pathlib.Path(tmp)
    (path/'test.c').write_text(code+active+'\n'+workers+main)
    subprocess.run(shlex.split(os.environ.get('HOSTCC', 'cc')) +
                   ['-Wall','-Wextra','-Werror','-Wno-unused-parameter',
                    '-fsanitize=address,undefined',str(path/'test.c'),
                    '-o',str(path/'test')],check=True)
    subprocess.run([str(path/'test')],check=True)
