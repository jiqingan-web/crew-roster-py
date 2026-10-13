"""与网页版（js/core.js @ 4ac2b38）对照：tests/golden_js.json 由 tools/parity_dump.js 生成。
若本机有 node 且设置 ROSTER_APP=网页版目录，则现场重新生成对照数据。"""
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, '..', 'tools'))
import parity_dump  # noqa: E402


def _norm(o):
    if isinstance(o, dict): return {k: _norm(v) for k, v in o.items() if v is not None}
    if isinstance(o, list): return [_norm(v) for v in o]
    return o


def _golden():
    app = os.environ.get('ROSTER_APP')
    if app and shutil.which('node'):
        out = subprocess.run(['node', os.path.join(HERE, '..', 'tools', 'parity_dump.js'), app], capture_output=True, text=True, check=True).stdout
        return json.loads(out)
    with open(os.path.join(HERE, 'golden_js.json'), encoding='utf-8') as f: return json.load(f)


def test_parity_with_js():
    js = _norm(_golden()); py = _norm(json.loads(json.dumps(parity_dump.dump(), ensure_ascii=False)))
    for k in js:
        assert py[k] == js[k], f'与网页版不一致：{k}'
