"""常量、级别与座位规则、机场、随机数、派生量、合法性检查、FDP 计算（与 js/core.js 一一对应）。"""
import math
import re

from .jsutil import jround, jsort, includes_obj

YEAR, MONTH, DAYS, DAY = 2026, 11, 30, 1440

# ---------- 级别 ----------
RANK_VAL = {'F1': 1, 'F2': 2, 'F3': 3, 'F4': 4, 'F5': 5, 'F6': 6, 'F7': 7, 'F8': 8,
            'SPIC': 10, 'US': 11, 'J0': 12, '机长A': 12, '机长B': 12, 'J1': 13, 'J2': 14, 'J3': 15, 'TL': 20, 'TB': 21, 'TC': 22}
RANKS = list(RANK_VAL)
NEW_CAPT = ['SPIC', 'US', 'J0', '机长A', '机长B']
INSTR = ['TL', 'TB', 'TC']
GROUPS = ['教员', '机长', '新机长', '副驾驶']


def isFO(r): return RANK_VAL[r] <= 8
def isCaptClass(r): return RANK_VAL[r] >= 10
def isInstr(r): return r in INSTR
def isNew(r): return r in NEW_CAPT
def isJ2plus(r): return r in ('J2', 'J3') or isInstr(r)
def isJ3plus(r): return r == 'J3' or isInstr(r)
def isJ1plus(r): return r in ('J1', 'J2', 'J3') or isInstr(r)
def foLevel(r): return RANK_VAL[r] if isFO(r) else 9


def rankGroup(r):
    if isInstr(r): return '教员'
    if isNew(r): return '新机长'
    if isCaptClass(r): return '机长'
    return '副驾驶'


def seatOK(L, R):
    """RE12 巡航座位搭配：左座 L → 右座 R 是否允许"""
    if not isCaptClass(L): return False
    if L == 'SPIC': return isInstr(R)
    if isInstr(L): return True
    if L in ('US', 'J0', 'J1', '机长A', '机长B'): return isCaptClass(R) or (isFO(R) and RANK_VAL[R] >= 4)
    if L in ('J2', 'J3'): return isCaptClass(R) or (isFO(R) and RANK_VAL[R] >= 3)
    return False


# ---------- 机场 ----------
AIRPORTS = {
    'ZUUU': ['成都', 30.58, 103.95], 'ZBAA': ['北京', 40.08, 116.58], 'ZSPD': ['上海浦东', 31.14, 121.8],
    'ZGGG': ['广州', 23.39, 113.3], 'ZGSZ': ['深圳', 22.64, 113.81], 'ZGHA': ['长沙', 28.19, 113.22],
    'ZJSY': ['三亚', 18.3, 109.41], 'ZJHK': ['海口', 19.93, 110.46], 'ZSHC': ['杭州', 30.23, 120.43],
    'ZSNJ': ['南京', 31.74, 118.86], 'ZHHH': ['武汉', 30.78, 114.21], 'ZLXY': ['西安', 34.45, 108.75],
    'ZWWW': ['乌鲁木齐', 43.9, 87.47], 'ZYHB': ['哈尔滨', 45.62, 126.25], 'ZSQD': ['青岛', 36.36, 120.09],
    'ZSAM': ['厦门', 24.54, 118.13], 'ZPPP': ['昆明', 25.1, 102.93], 'ZGNN': ['南宁', 22.61, 108.17],
    'ZBYN': ['太原', 37.75, 112.63], 'ZHCC': ['郑州', 34.52, 113.84], 'ZSJN': ['济南', 36.86, 117.22],
    'ZGOW': ['揭阳', 23.55, 116.5], 'ZSFZ': ['福州', 25.93, 119.66], 'ZLLL': ['兰州', 36.52, 103.62],
    'ZBHH': ['呼和浩特', 40.85, 111.82], 'ZUGY': ['贵阳', 26.54, 106.8], 'ZYYJ': ['延吉', 42.88, 129.45],
    'ZSSS': ['上海虹桥', 31.2, 121.34], 'ZYTX': ['沈阳', 41.64, 123.48], 'ZSWX': ['无锡', 31.49, 120.43],
    'ZULS': ['拉萨', 29.3, 90.91, 'LHASA'], 'ZPLJ': ['丽江', 26.68, 100.25, 'HIGH'], 'ZPJH': ['西双版纳', 21.97, 100.76, 'HIGH'],
    'ZUXC': ['西昌', 27.99, 102.18, 'HIGH'], 'ZLXN': ['西宁', 36.53, 102.04, 'HIGH'], 'ZYTL': ['大连', 38.97, 121.54, 'HIGH'],
    'ZPDQ': ['迪庆', 27.79, 99.68, 'PLATEAU'], 'ZUDC': ['稻城亚丁', 29.32, 100.05, 'PLATEAU'], 'ZUJZ': ['九寨', 32.85, 103.68, 'PLATEAU'],
    'ZBCF': ['赤峰', 42.24, 118.91, 'ZBCF'], 'ZWKM': ['克拉玛依', 45.47, 84.95, 'J1'], 'ZUMT': ['茅台', 27.81, 106.33, 'US'],
    'ZBLL': ['吕梁', 37.68, 111.14, 'US'], 'ZBXZ': ['忻州', 38.6, 112.97, 'US'],
}
CAT_DESC = {
    'LHASA': '拉萨：两名飞行员均需 J3 及以上', 'HIGH': '高原/复杂机场：J2/J3+F6以上，或教员+F5以上',
    'PLATEAU': '一般高原机场：J2/J3+F5以上，或教员+F4以上', 'ZBCF': '赤峰：J2/J3/教员 + F4以上',
    'J1': '克拉玛依：左座 J1 及以上', 'US': '茅台/吕梁/忻州：左座 US 及以上', 'NONE': '无特殊要求'}
AUTH_CATS = ['LHASA', 'HIGH', 'PLATEAU', 'ZBCF']

def defaultHealth():
    return {'noFly': False, 'noPlateau': False, 'noNight': False, 'bpNote': '', 'medExamExpiry': '', 'note': ''}

def authAirports(st=None):
    A = (st or {}).get('airports') or AIRPORTS
    return sorted([c for c, v in A.items() if (v[3] if len(v) > 3 else 'NONE') in AUTH_CATS], key=lambda c: apName(c, st))

def hasHealthRestriction(h):
    h = h or {}
    return bool(h.get('noFly') or h.get('noPlateau') or h.get('noNight') or (h.get('bpNote') or '').strip() or (h.get('medExamExpiry') or '').strip() or (h.get('note') or '').strip())

def isPlateauAirport(c, st=None):
    return apCat(c, st) in ('LHASA', 'HIGH', 'PLATEAU')

def migratePilots(st):
    if not st or not st.get('pilots'): return st
    squads = ['一大队', '二大队', '三大队', '教学中队']
    for i, p in enumerate(st['pilots']):
        h = defaultHealth(); h.update(p.get('health') or {}); p['health'] = h
        if not p.get('squad'):
            p['squad'] = '教学中队' if isInstr(p['rank']) else squads[i % 3]
        if not isinstance(p.get('auth'), list): p['auth'] = []
    return st

def healthBlocks(p, pr, st):
    h = p.get('health') or {}; rs = []
    if h.get('noFly'): rs.append('暂时不适飞')
    if h.get('noPlateau') and any(isPlateauAirport(l['from'], st) or isPlateauAirport(l['to'], st) for l in pr['legs']):
        rs.append('限制高原（任务含高原/拉萨类机场）')
    if h.get('noNight') and any(isNightLeg(l) for l in pr['legs']):
        rs.append('限制夜间（任务含夜航段）')
    exp = h.get('medExamExpiry') or ''
    if exp:
        try:
            from datetime import datetime
            ed = datetime.strptime(exp, '%Y-%m-%d')
            for d in daysTouched(pr, st):
                if datetime(YEAR, MONTH, d) > ed:
                    rs.append('体检已过期(' + exp + ')'); break
        except ValueError:
            pass
    return rs



def _ap(c, st):
    a = None
    if st and st.get('airports'):
        a = st['airports'].get(c)
    return a or AIRPORTS.get(c)


def apName(c, st=None):
    a = _ap(c, st)
    return a[0] if a else c


def apCat(c, st=None):
    a = _ap(c, st)
    return (a[3] if a and len(a) > 3 and a[3] else None) or 'NONE'


def needsAuth(c, st=None): return apCat(c, st) in AUTH_CATS
def isSpecial(c, st=None): return apCat(c, st) != 'NONE'


def catOK(cat, L, R):
    if cat == 'LHASA': return isJ3plus(L) and isJ3plus(R)
    if cat == 'HIGH': return (isJ2plus(L) and not isInstr(L) and foLevel(R) >= 6) or (isInstr(L) and foLevel(R) >= 5)
    if cat == 'PLATEAU': return (isJ2plus(L) and not isInstr(L) and foLevel(R) >= 5) or (isInstr(L) and foLevel(R) >= 4)
    if cat == 'ZBCF': return isJ2plus(L) and foLevel(R) >= 4
    if cat == 'J1': return isJ1plus(L)
    if cat == 'US': return isCaptClass(L) and L != 'SPIC'
    return True


# ---------- 随机（mulberry32，与 JS 完全一致） ----------
def _i32(x):
    x &= 0xFFFFFFFF
    return x - 0x100000000 if x & 0x80000000 else x


def _imul(a, b):
    return _i32((a & 0xFFFFFFFF) * (b & 0xFFFFFFFF))


def _urs(x, n):
    return (x & 0xFFFFFFFF) >> n


def rng(seed):
    s = [_i32(seed)]

    def r():
        seed = _i32(s[0] + 0x6D2B79F5)
        s[0] = seed
        t = _imul(seed ^ _urs(seed, 15), 1 | seed)
        t = _i32(t + _imul(t ^ _urs(t, 7), 61 | t)) ^ t
        return ((t ^ _urs(t, 14)) & 0xFFFFFFFF) / 4294967296
    return r


_BM = {}


def blockMin(a, b):
    k = (a, b)
    if k in _BM: return _BM[k]
    A, B = AIRPORTS[a], AIRPORTS[b]
    R, toR = 6371, math.pi / 180
    d = 2 * R * math.asin(math.sqrt(math.sin((B[1] - A[1]) * toR / 2) ** 2 + math.cos(A[1] * toR) * math.cos(B[1] * toR) * math.sin((B[2] - A[2]) * toR / 2) ** 2))
    v = jround((d * 1.1 / 12.5 + 28) / 5) * 5
    _BM[k] = v
    return v


# ---------- 设置 ----------
LEG_COLS = ['1–4 段', '5 段', '6 段', '7 段及以上']


def defaultFdpTable():
    return [{'from': 0, 'to': 5, 'label': '00:00–04:59', 'lim': [12, 11, 10, 9]},
            {'from': 5, 'to': 12, 'label': '05:00–11:59', 'lim': [14, 13, 12, 11]},
            {'from': 12, 'to': 24, 'label': '12:00–23:59', 'lim': [13, 12, 11, 10]}]


def defaultSettings():
    return {'minRestH': 12, 'hardMaxHours': 90, 'maxOffCapt': 4, 'maxOffFO': 7,
            'bpTesterAirports': ['ZLXY', 'ZWWW'], 'reportMin': 60, 'releaseMin': 30, 'honorPrefs': True,
            'standbyPerDay': 1, 'maxStandbyPerPilot': 1, 'gapWeight': 0.35,
            'fdpTable': defaultFdpTable(), 'fdpAugmented': False, 'fdpAugLimitH': 16, 'fdpRiskHigh': 60, 'fdpRiskMed': 120,
            'minTurnMin': 35, 'minOvernightRestH': 10}


def migrateSettings(S):
    if S and S.get('testerAirports'):
        S['bpTesterAirports'] = S.pop('testerAirports')
    if S and ('standbyCapt' in S or 'standbyFO' in S or 'maxFreeRun' in S):
        for k in ('standbyCapt', 'standbyFO', 'maxFreeRun'): S.pop(k, None)
        S['standbyPerDay'] = 1; S['maxStandbyPerPilot'] = 1
    if S is not None:
        S.pop('minHours', None); S.pop('maxHours', None)
        if not S.get('fdpTable'): S['fdpTable'] = defaultFdpTable()
    return S


# ---------- 任务派生量 ----------
def pairingHours(p):
    s = 0
    for l in p['legs']: s += l['arr'] - l['dep']
    return s / 60


def _rep(st): return (st and st['settings'].get('reportMin')) or 60
def _rel(st): return (st and st['settings'].get('releaseMin')) or 30


def report(p, st=None): return p['legs'][0]['dep'] - _rep(st)
def release(p, st=None): return p['legs'][-1]['arr'] + _rel(st)


_DT = {}


def _span(p, st):
    legs = p['legs']; k = (legs[0]['dep'], legs[-1]['arr'], _rep(st), _rel(st))
    v = _DT.get(k)
    if v is None:
        a = int((k[0] - k[2]) // DAY) + 1; b = int((k[1] + k[3] - 1) // DAY) + 1
        v = _DT[k] = (a, b, tuple(range(a, b + 1)))
    return v


def daysTouched(p, st=None):
    return list(_span(p, st)[2])


def isNightLeg(l):
    a = l['dep'] % DAY; b = l['arr'] % DAY
    return a < 360 or b < 360 or l['arr'] - (l['dep'] // DAY) * DAY >= DAY


def fmtT(m):
    m = int(m) % DAY
    return f"{m // 60:02d}:{m % 60:02d}"


def fmtH(m):
    from .jsutil import jmod
    return f"{math.floor(m / 60)}h{str(jround(jmod(m, 60))).zfill(2)}"


def specialAirportsOf(p, st=None):
    out = []
    for l in p['legs']:
        for c in (l['from'], l['to']):
            if isSpecial(c, st) and c not in out: out.append(c)
    return out


# ---------- 机组合法性 ----------
def legSeatedOK(L, R, leg, st):
    if not seatOK(L['rank'], R['rank']): return False
    for c in (leg['from'], leg['to']):
        cat = apCat(c, st)
        if cat == 'NONE': continue
        if cat in AUTH_CATS and (c not in L['auth'] or c not in R['auth']): return False
        if not catOK(cat, L['rank'], R['rank']): return False
    if leg.get('ac') == 'A321' and not isJ2plus(L['rank']): return False
    return True


def crewIssue(p, crewPilots, st):
    cs = [x for x in crewPilots if x]
    if len(cs) < 3: return None
    if any(isNew(x['rank']) for x in cs) and not any(isInstr(x['rank']) for x in cs): return '新机长所在机组须有 TL 及以上教员'
    if len([x for x in cs if isCaptClass(x['rank'])]) < 1: return '机组无机长'
    for leg in p['legs']:
        ok = False
        for i in range(3):
            if ok: break
            for j in range(3):
                if i != j and legSeatedOK(cs[i], cs[j], leg, st):
                    ok = True; break
        if not ok:
            c = next((x for x in (leg['from'], leg['to']) if isSpecial(x, st)), None)
            return f"D{leg['d']} {leg['flt']} {apName(leg['from'], st)}-{apName(leg['to'], st)}：无满足{'特殊机场(' + apName(c, st) + ')授权/' if c else ''}座位搭配规则的左右座组合"
    if any(x['rank'] in ('F1', 'F2') for x in cs) and not any(isInstr(x['rank']) for x in cs): return 'F1/F2 须与教员同组'
    return None


SLOT_NAME = {'C': '机', 'F': '副', 'T': '三'}
SLOTS = ('C', 'F', 'T')


def slotRankOK(slot, rank):
    if slot == 'C': return isCaptClass(rank)
    if slot == 'F': return isFO(rank)
    return True


# ---------- 索引 ----------
def buildIndex(st):
    pm = {p['id']: p for p in st['pilots']}
    sched = {p['id']: [] for p in st['pilots']}
    hours = {p['id']: 0 for p in st['pilots']}
    for pr in st['pairings']:
        h = pairingHours(pr)
        for s in SLOTS:
            i = pr['crew'].get(s)
            if i and i in sched:
                sched[i].append(pr); hours[i] += h
    return {'pm': pm, 'sched': sched, 'hours': hours}


def shareFor(p): return max(0.05, (DAYS - len(p.get('leave') or [])) / DAYS)
def hardCap(st): return st['settings'].get('hardMaxHours') or 90


def personCheck(p, pr, st, idx, opt=None):
    opt = opt or {}
    rs = []; S = st['settings']
    dt = _span(pr, st)[2]
    leave = p.get('leave') or []
    lv = [d for d in dt if d in leave]
    if lv: rs.append('请假(' + ','.join(map(str, lv)) + '日)')
    if not opt.get('ignorePrefs'):
        prefs = p.get('prefs') or []
        pf = [d for d in dt if d in prefs]
        if pf: rs.append('意向休息日(' + ','.join(map(str, pf)) + '日)')
    a = report(pr, st); b = release(pr, st); rest = S['minRestH'] * 60
    ex = opt.get('excludeId') or ''
    for o in idx['sched'][p['id']]:
        if o is pr or o['id'] == ex: continue
        oa = report(o, st); ob = release(o, st)
        if oa < b and a < ob:
            rs.append('时间冲突(' + o['id'] + ')'); continue
        if (oa >= b and oa - b < rest) or (a >= ob and a - ob < rest):
            rs.append('休息不足' + _num(S['minRestH']) + 'h(' + o['id'] + ')')
    h = pairingHours(pr); already = includes_obj(idx['sched'][p['id']], pr)
    cap = hardCap(st)
    if not already and idx['hours'][p['id']] + h > cap + 1e-9: rs.append('超出法规硬上限' + _num(cap) + 'h')
    rs.extend(healthBlocks(p, pr, st))
    return [len(rs) == 0, rs]


def _num(v):
    """JS 数字转字符串（12.0 → '12'）"""
    if isinstance(v, float) and v.is_integer(): return str(int(v))
    return str(v)


# ---------- 节奏 ----------
def pDays(pr, st):
    v = _span(pr, st); return [v[0], v[1]]


def restGaps(p, lst, st):
    if len(lst) < 2: return []
    rep = _rep(st); rel = _rel(st); ds = []
    for pr in lst:
        legs = pr['legs']; k = (legs[0]['dep'], legs[-1]['arr'], rep, rel)
        v = _DT.get(k)
        ds.append(v if v is not None else _span(pr, st))
    ds.sort(key=lambda x: x[0])
    g = []
    ex = set((p.get('leave') or []) + (p.get('prefs') or []))
    for i in range(1, len(ds)):
        n = 0
        for d in range(ds[i - 1][1] + 1, ds[i][0]):
            if d not in ex: n += 1
        g.append(n)
    return g


def gapCostOne(g):
    return 1.0 if g <= 0 else 0.6 if g == 1 else 0 if g <= 3 else 0.25 if g == 4 else 0.5 + 0.1 * (g - 5)


def gapCost(p, lst, st):
    s = 0
    for g in restGaps(p, lst, st): s += gapCostOne(g)
    return s


# ---------- 候选人 ----------
def candidates(st, pr, slot):
    idx = buildIndex(st); res = []
    dt = daysTouched(pr, st); sb = st.get('standby') or {}
    for p in st['pilots']:
        rs = []
        if not slotRankOK(slot, p['rank']): rs.append('级别不适合' + SLOT_NAME[slot] + '位')
        other = [pr['crew'].get(s) for s in SLOTS if s != slot]
        if p['id'] in other: rs.append('已在本任务')
        if not rs:
            _, r2 = personCheck(p, pr, st, idx, {'ignorePrefs': True}); rs.extend(r2)
            crew = [p if s == slot else (pr['crew'].get(s) and idx['pm'].get(pr['crew'][s])) for s in SLOTS]
            iss = crewIssue(pr, crew, st)
            if iss: rs.append(iss)
        prefs = p.get('prefs') or []
        pf = [d for d in dt if d in prefs]
        mysb = sb.get(p['id']) or []
        sbd = [d for d in dt if d in mysb]
        res.append({'p': p, 'ok': len(rs) == 0, 'reasons': rs, 'warn': ('意向休息日' + ','.join(map(str, pf)) + '日') if pf else '', 'standby': sbd, 'hours': idx['hours'][p['id']]})
    return jsort(res, lambda a, b: (b['ok'] - a['ok']) or (a['hours'] - b['hours']))


# ---------- 日状态 / 备份 ----------
def dayStatus(st, idx=None):
    idx = idx or buildIndex(st); sb = st.get('standby') or {}; out = {}
    for p in st['pilots']:
        a = [''] * (DAYS + 2)
        for d in (p.get('prefs') or []): a[d] = 'P'
        for d in (p.get('leave') or []): a[d] = 'L'
        for d in (sb.get(p['id']) or []):
            if not a[d]: a[d] = 'S'
        for pr in idx['sched'][p['id']]:
            for d in daysTouched(pr, st):
                if 1 <= d <= DAYS: a[d] = 'D'
        out[p['id']] = a
    return out


def sbOK(a, d): return a[d] == '' and a[d - 1] != 'D' and a[d + 1] != 'D'


def freeRuns(a):
    r = []; s = 0
    for d in range(1, DAYS + 2):
        if d <= DAYS and a[d] == '':
            if not s: s = d
        elif s:
            r.append([s, d - 1]); s = 0
    return r


# ---------- FDP ----------
def legKey(l): return f"{l['flt']}@{_num(l['dep'])}"


def fdpLimit(st, reportMin, nLegs):
    S = st['settings']
    if S.get('fdpAugmented'): return (S.get('fdpAugLimitH') or 16) * 60
    h = (reportMin % DAY) / 60; T = S.get('fdpTable') or defaultFdpTable()
    row = next((r for r in T if r['from'] <= h < r['to']), T[-1])
    c = 0 if nLegs <= 4 else 1 if nLegs == 5 else 2 if nLegs == 6 else 3
    return row['lim'][c] * 60


def _risk(buf, S):
    return 'over' if buf < 0 else 'high' if buf < (S.get('fdpRiskHigh') or 60) else 'med' if buf < (S.get('fdpRiskMed') or 120) else 'low'


def fdpDays(pr, st, acts=None):
    """逐日 FDP（按实际/预计时刻，不级联）。acts: {legKey: {dep?, arr?, kind}}"""
    acts = acts or {}; S = st['settings']
    rep = S.get('reportMin') or 60; rel = S.get('releaseMin') or 30; turn = S.get('minTurnMin') or 35
    out = []; prevC = None
    for i, l in enumerate(pr['legs']):
        a = acts.get(legKey(l)) or {}; blk = l['arr'] - l['dep']
        ad, aa = a.get('dep'), a.get('arr')
        dep = ad if ad is not None else l['dep']
        arr = aa if aa is not None else (ad + blk if ad is not None else l['arr'])
        known = ad is not None or aa is not None
        cdep = dep if known else l['dep']
        if not known and prevC and prevC['leg']['d'] == l['d']:
            cdep = max(cdep, prevC['carr'] + min(turn, l['dep'] - prevC['leg']['arr']))
        carr = arr if known else cdep + blk
        x = {'i': i, 'leg': l, 'dep': dep, 'arr': arr, 'known': known, 'kind': (a.get('kind') or 'est') if known else 'plan',
             'landed': aa is not None and a.get('kind') == 'act', 'departed': ad is not None and a.get('kind') == 'act',
             'late': dep - l['dep'], 'lateArr': arr - l['arr'], 'cdep': cdep, 'carr': carr,
             'conflict': (prevC['arr'] - dep) if (prevC and prevC['leg']['d'] == l['d'] and dep < prevC['arr'] and not known) else 0}
        x['dly'] = max(0, x['late'])
        if not out or out[-1]['d'] != l['d']: out.append({'d': l['d'], 'legs': []})
        out[-1]['legs'].append(x); prevC = x
    for k, dy in enumerate(out):
        f = dy['legs'][0]
        dy['date'] = f['leg']['dep'] // DAY + 1
        dy['start'] = f['dep'] - rep if (pr.get('freshAt') and pr['freshAt'] == legKey(f['leg'])) else f['leg']['dep'] - rep
        dy['end'] = max(x['arr'] for x in dy['legs']); dy['planEnd'] = dy['legs'][-1]['leg']['arr']
        dy['cascEnd'] = max(x['carr'] for x in dy['legs'])
        dy['fdp'] = dy['end'] - dy['start']; dy['planFdp'] = dy['planEnd'] - (f['leg']['dep'] - rep)
        dy['limit'] = fdpLimit(st, f['leg']['dep'] - rep, len(dy['legs']))
        dy['buffer'] = dy['limit'] - dy['fdp']; dy['planBuffer'] = dy['limit'] - dy['planFdp']
        dy['exceed'] = max(0, -dy['buffer'])
        dy['cascExceed'] = 0 if dy['exceed'] else max(0, dy['cascEnd'] - dy['start'] - dy['limit'])
        dy['cascLeg'] = next((x for x in dy['legs'] if x['carr'] > dy['start'] + dy['limit']), None) if dy['cascExceed'] else None
        dy['exLeg'] = next((x for x in dy['legs'] if x['arr'] > dy['start'] + dy['limit']), None) if dy['exceed'] else None
        dy['nLanded'] = sum(1 for x in dy['legs'] if x['landed']); dy['nKnown'] = sum(1 for x in dy['legs'] if x['known'])
        dy['risk'] = _risk(dy['buffer'], S); dy['planRisk'] = _risk(dy['planBuffer'], S)
        dy['restAfter'] = dy['planRest'] = None; dy['restShort'] = dy['planRestShort'] = 0
        if k + 1 < len(out):
            nx = out[k + 1]; req = (S.get('minOvernightRestH') or 10) * 60
            dy['restAfter'] = (nx['legs'][0]['dep'] - rep) - (dy['end'] + rel)
            dy['planRest'] = (nx['legs'][0]['leg']['dep'] - rep) - (dy['planEnd'] + rel)
            dy['restShort'] = max(0, req - dy['restAfter']) if dy['restAfter'] < dy['planRest'] else 0
            dy['planRestShort'] = max(0, req - dy['planRest'])
    return out


PR_RE = re.compile(r'\((PR\d+)\)')
