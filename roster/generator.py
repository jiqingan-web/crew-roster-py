"""示例数据生成（与 JS generateSample 同种子、同逻辑，结果逐项一致）。"""
import math

from .rules import (AIRPORTS, AUTH_CATS, DAYS, DAY, RANK_VAL, isFO, isInstr, isNew, rng, blockMin,
                    defaultSettings, pairingHours)
from .jsutil import jsorted

SUR = '王李张刘陈杨黄赵吴周徐孙马朱胡郭何高林罗郑梁谢宋唐许韩冯邓曹彭曾肖田董袁潘于蒋蔡余杜叶程苏魏吕丁任沈姚卢姜崔钟谭陆汪范金石廖贾夏韦付方邹熊白孟秦邱江尹薛闫段雷侯龙史陶黎贺顾毛郝龚邵万钱严覃武戴莫孔向汤'
GIV = ['伟', '强', '磊', '军', '勇', '杰', '涛', '斌', '超', '明', '刚', '平', '辉', '鹏', '华', '飞', '鑫', '波', '宇', '浩', '凯', '健', '俊', '帆', '帅', '旭', '宁', '龙', '林', '阳', '洋', '翔', '峰', '晨', '博', '昊', '睿', '航', '子轩', '一鸣', '志强', '建国', '海涛', '天佑', '思远', '浩然', '俊杰', '晓东', '文博', '明轩', '雨辰', '嘉豪', '国栋', '振宇', '立新', '云飞', '少华', '春雷', '晓峰', '子豪', '静', '婷', '丹', '雪', '琳']


def _cat(c):
    a = AIRPORTS[c]
    return a[3] if len(a) > 3 else None


def generateSample(seed=None, opt=None):
    opt = opt or {}
    r = rng(seed or 20261101)

    def pick(a): return a[math.floor(r() * len(a))]
    comp = [['TC', 2], ['TB', 3], ['TL', 5], ['J3', 23], ['SPIC', 1], ['US', 2], ['J0', 1], ['机长A', 1], ['机长B', 1],
            ['F8', 2], ['F7', 12], ['F6', 11], ['F5', 11], ['F4', 7], ['F3', 15], ['F2', 2], ['F1', 1]]
    used = set(); pilots = []; no = 10230
    specialAll = [c for c in AIRPORTS if _cat(c) in AUTH_CATS]

    def byCat(c): return [x for x in specialAll if _cat(x) == c]
    for rk, n in comp:
        for _ in range(n):
            while True:
                nm = pick(SUR) + pick(GIV)
                if nm not in used: break
            used.add(nm)
            no += 1 + math.floor(r() * 37)
            auth = []
            if isInstr(rk): auth = specialAll[:]
            elif rk == 'J3':
                auth = specialAll[:] if r() < 0.75 else [x for x in specialAll if _cat(x) != 'LHASA' and r() < 0.7]
            elif isNew(rk): auth = [x for x in byCat('PLATEAU') if r() < 0.4]
            else:
                v = RANK_VAL[rk]
                if v >= 6: auth = [x for x in specialAll if _cat(x) != 'LHASA' and r() < 0.85]
                elif v >= 4: auth = [x for x in specialAll if _cat(x) in ('PLATEAU', 'ZBCF') and r() < 0.6]
            pilots.append({'id': 'E' + str(no), 'name': nm, 'rank': rk, 'auth': auth, 'prefs': [], 'leave': []})
    S = defaultSettings()
    offCount = {'C': [0] * (DAYS + 1), 'F': [0] * (DAYS + 1)}

    def lim(p): return S['maxOffFO'] if isFO(p['rank']) else S['maxOffCapt']
    def key(p): return 'F' if isFO(p['rank']) else 'C'
    leaveP = [p for p in pilots if r() < 0.07]
    for p in leaveP:
        s = 1 + math.floor(r() * 25); n = 3 + math.floor(r() * 3)
        d = s
        while d < s + n and d <= DAYS:
            if offCount[key(p)][d] < lim(p):
                p['leave'].append(d); offCount[key(p)][d] += 1
            d += 1
    for p in pilots:
        tries = 0
        while len(p['prefs']) < 2:
            tries += 1
            if tries > 50: break
            d = 1 + math.floor(r() * DAYS)
            if d in p['prefs'] or d in p['leave'] or offCount[key(p)][d] >= lim(p): continue
            p['prefs'].append(d); offCount[key(p)][d] += 1
        p['prefs'].sort()

    normal = [c for c in AIRPORTS if c != 'ZUUU' and not _cat(c)]  # noqa: F841 (与 JS 保持一致)
    fltNo = {}; fb = [2201]

    def fn(a, b):
        k = a + b
        if k not in fltNo:
            kr = b + a
            if kr in fltNo: fltNo[k] = 'EU' + str(int(fltNo[kr][2:]) + 1)
            else:
                fltNo[k] = 'EU' + str(fb[0]); fb[0] += 2 + 2 * math.floor(r() * 30)
                if fb[0] > 9900: fb[0] = 1101
        return fltNo[k]
    pairings = []; pid = 1; total = 0; target = opt.get('targetHours') or 1880
    nearC = {}

    def near(c, n):
        k = c + str(n)
        if k not in nearC:
            xs = [x for x in AIRPORTS if x != c and x != 'ZUUU' and _cat(x) != 'LHASA']
            nearC[k] = jsorted(xs, lambda x, y: blockMin(c, x) - blockMin(c, y))[:n]
        return nearC[k]

    def pickNear(c, n, excl):
        pool = [x for x in near(c, n) if x not in excl]
        sp = [x for x in pool if _cat(x)]; nm = [x for x in pool if not _cat(x)]
        return pick(sp) if (r() < 0.2 and sp) else pick(nm if nm else pool)
    while total < target:
        u = r(); nd = 1 if u < 0.06 else 2 if u < 0.18 else 3 if u < 0.6 else 4
        start = 1 + math.floor(r() * (DAYS - nd + 1))
        legs = []; ac = 'A321' if r() < 0.08 else 'A320'
        lhasa = r() < 0.04
        stations = ['ZUUU']
        for i in range(1, nd): stations.append(pickNear(stations[i - 1], 26 if i == 1 else 12, [stations[i - 1]]))
        stations.append('ZUUU')
        redeye = nd == 1 and not lhasa and r() < 0.3
        for k in range(nd):
            a, b = stations[k], stations[k + 1]
            if lhasa and k == 0:
                seq = ['ZUUU', 'ZULS', 'ZUUU'] if a == b else ['ZUUU', 'ZULS', 'ZUUU', b]
            else:
                v = r(); nl = 2 if redeye else 2 if v < 0.5 else 3 if v < 0.82 else 4
                for tries in range(6):
                    seq = [a]; cur = a
                    for i in range(nl - 1):
                        x = a if (i % 2 == 1 and cur != a and r() < 0.6 and a != b) else pickNear(cur, 10, [cur, b])
                        seq.append(x); cur = x
                    if cur != b: seq.append(b)
                    else: seq += [pickNear(cur, 8, [cur]), b]
                    seq = [s2 for i, s2 in enumerate(seq) if i == 0 or s2 != seq[i - 1]]
                    bt = sum(blockMin(seq[i], seq[i + 1]) for i in range(len(seq) - 1))
                    if bt <= 450: break
                    if tries == 5: seq = [a, pickNear(a, 6, [a]), b] if a == b else [a, b]
            t = (start - 1 + k) * DAY + (1230 + 5 * math.floor(r() * 18) if redeye else 400 + 5 * math.floor(r() * 66))
            for i in range(len(seq) - 1):
                bm = blockMin(seq[i], seq[i + 1])
                legs.append({'d': k + 1, 'flt': fn(seq[i], seq[i + 1]), 'from': seq[i], 'to': seq[i + 1], 'dep': t, 'arr': t + bm, 'ac': ac})
                t += bm + (95 if (pid % 7 == 3 and len(seq) >= 5) else 50)
        p = {'id': 'PR' + str(pid).zfill(3), 'start': start, 'ndays': nd, 'ac': ac, 'legs': legs, 'crew': {'C': None, 'F': None, 'T': None}}
        pid += 1
        total += pairingHours(p); pairings.append(p)
    pairings.sort(key=lambda p: p['legs'][0]['dep'])
    for i, p in enumerate(pairings): p['id'] = 'PR' + str(i + 1).zfill(3)
    return {'version': 1, 'sample': True, 'settings': S, 'pilots': pilots, 'pairings': pairings}
