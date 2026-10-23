#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Test production profile scaling, DDR input and preserved max-boost lifetime."""
import re
from test_helpers import ROOT, function_body, run_c
header=re.sub(r'^#include.*$', '', (ROOT/'include/linux/kprofiles.h').read_text(), flags=re.M)
prefix=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <errno.h>
#include <limits.h>
static int mode;
int kp_active_mode(void) { return mode; }
#define CONFIG_KPROFILES 1
'''
code=prefix+header+r'''
#define READ_ONCE(x) (x)
#define CONFIG_DEVFREQ_INPUT_BOOST_DURATION_MS 58
#define BIT(n) (1UL<<(n))
#define test_bit(n,p) (!!(*(p)&BIT(n)))
#define set_bit(n,p) (*(p)|=BIT(n))
#define msecs_to_jiffies(v) (v)
enum {SCREEN_OFF,INPUT_BOOST,MAX_BOOST};
struct boost_dev { void *df; unsigned long state; int input_unboost, boost_waitq; };
static int system_unbound_wq, delay, wakes;
static int mod_delayed_work(int wq, int *work, unsigned int ms) { delay=ms; return 0; }
static void wake_up(int *queue) { wakes++; }
static void __devfreq_boost_kick(struct boost_dev *b)
'''+function_body('drivers/devfreq/devfreq_boost.c','__devfreq_boost_kick')+r'''
int main(void) {
 unsigned int expected[]={80,40,80,120};
 for(mode=0;mode<4;mode++) {
  assert(kp_input_boost_duration(80)==expected[mode]);
  assert(kp_input_boost_duration(0)==0);
 }
 mode=1; assert(kp_input_boost_duration(1)==1);
 assert(kp_input_boost_duration(UINT_MAX)==2147483648U);
 mode=3; assert(kp_input_boost_duration(1)==2);
 assert(kp_input_boost_duration(UINT_MAX)==UINT_MAX);
 assert(kp_input_boost_duration(UINT_MAX-1)==UINT_MAX);
 struct boost_dev b={.df=&b,.state=BIT(MAX_BOOST)};
 mode=0; __devfreq_boost_kick(&b); assert(delay==58 && wakes==1);
 mode=1; __devfreq_boost_kick(&b); assert(delay==29 && wakes==2);
 mode=2; __devfreq_boost_kick(&b); assert(delay==58 && wakes==3);
 mode=3; __devfreq_boost_kick(&b); assert(delay==87 && wakes==4);
 assert(b.state&BIT(MAX_BOOST));
 b.state|=BIT(SCREEN_OFF); __devfreq_boost_kick(&b); assert(wakes==4);
 b.state=0; b.df=NULL; __devfreq_boost_kick(&b); assert(wakes==4);
 puts("PASS: KProfiles scaling/overflow and DDR input profiles preserve max/screen-off");
}
'''
run_c(code)
run_c('#include <assert.h>\n#include <errno.h>\n#include <limits.h>\n'+header+r'''
int main(void) { assert(kp_input_boost_duration(80)==80); assert(kp_input_boost_duration(UINT_MAX)==UINT_MAX); }
''')
