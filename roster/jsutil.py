"""与 JS 行为一致的小工具（取整、取模、排序、深拷贝），保证与网页版数值一致。"""
import json
import math
from functools import cmp_to_key


def jround(x):
    """JS Math.round：.5 向 +∞ 取整。"""
    return math.floor(x + 0.5)


def jmod(a, b):
    """JS % ：结果符号随被除数。"""
    return math.fmod(a, b) if isinstance(a, float) or isinstance(b, float) else (abs(a) % abs(b)) * (1 if a >= 0 else -1)


def jsort(arr, cmp):
    """原地稳定排序（等价于 JS Array.prototype.sort(cmp)）。"""
    arr.sort(key=cmp_to_key(lambda a, b: _sgn(cmp(a, b))))
    return arr


def jsorted(arr, cmp):
    return sorted(arr, key=cmp_to_key(lambda a, b: _sgn(cmp(a, b))))


def _sgn(v):
    if v is None or v != v:  # NaN
        return 0
    return (v > 0) - (v < 0)


def clone(o):
    return json.loads(json.dumps(o, ensure_ascii=False))


def includes_obj(lst, o):
    for x in lst:
        if x is o:
            return True
    return False


def index_obj(lst, o):
    for i, x in enumerate(lst):
        if x is o:
            return i
    return -1


def fmt1(x):
    """JS toFixed(1)"""
    return f"{x:.1f}"


def uniq(seq):
    seen = []
    s = set()
    for x in seq:
        k = x if not isinstance(x, (dict, list)) else id(x)
        if k in s:
            continue
        s.add(k)
        seen.append(x)
    return seen
