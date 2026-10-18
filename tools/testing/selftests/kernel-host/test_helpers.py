# SPDX-License-Identifier: GPL-2.0
"""Compile selected production code with small host-side kernel fixtures."""
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[4]


def function_body(path, name):
    source = (ROOT / path).read_text()
    match = re.search(r'\b' + re.escape(name) + r'\([^;{}]*\)\s*\{', source)
    if not match:
        raise ValueError(f'{name} not found in {path}')
    start = match.end() - 1
    depth = 1
    end = start + 1
    # These fixtures select functions without braces in strings or comments.
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


def run_c(code):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory)
        source = path / 'test.c'
        binary = path / 'test'
        source.write_text(code)
        compiler = shlex.split(os.environ.get('HOSTCC', 'cc'))
        subprocess.run(compiler + ['-Wall', '-Wextra', '-Werror',
                       '-Wno-unused-parameter', '-Wno-unused-function',
                       '-fsanitize=address,undefined', str(source),
                       '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True)
