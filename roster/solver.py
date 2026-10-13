"""求解器：贪心 + 局部改进 + 交换 + 修复（置换链 / 意向休息 / 削峰）+ 备份分配。与 JS autoFill 同算法同随机序列。"""
import json
import math
import re

from .rules import (SLOTS, GROUPS, DAYS, RANK_VAL, rng, buildIndex, shareFor, pairingHours, apCat, gapCost, personCheck,
                    crewIssue, isCaptClass, isFO, isNew, isInstr, rankGroup, hardCap, candidates, daysTouched, dayStatus,
                    sbOK, PR_RE)
from .metrics import summarize
from .jsutil import jsort, jsorted, index_obj

_RE_TR = re.compile(r'^(时间冲突|休息不足)')


def autoFill(st, opts=None):
    """多次随机扰动求解，取最优（硬违规最少 → 软违规最少 → 节奏/工时更均衡）"""
    opts = opts or {}; K = opts.get('attempts') or 5; best = None

    def score(s): return s['hard'] * 1e6 + s['soft'] * 1e3 + (1 - s['rhythm']['gap23']) * 100 + s['all']['std']
    prog = opts.get('onProgress')
    for k in range(K):
        o2 = dict(opts); o2['noise'] = rng(9173 * k + 7) if k else None
        o2['onProgress'] = (lambda x, k=k: prog((k + x) / K)) if prog else None
        res = autoFillOnce(st, o2)
        sc = score(res)
        if not best or sc < best['sc']:
            best = {'sc': sc, 'crew': [dict(p['crew']) for p in st['pairings']], 'sb': json.dumps(st.get('standby')), 'k': k}
        if res['hard'] == 0 and (res['soft'] <= 3 or k >= 1): break
    for i, p in enumerate(st['pairings']): p['crew'] = best['crew'][i]
    st['standby'] = json.loads(best['sb'])
    out = summarize(st); out['attempt'] = best['k'] + 1
    return out


def autoFillOnce(st, opts=None):
    opts = opts or {}; nz = opts.get('noise'); S = st['settings']; keep = bool(opts.get('keepExisting'))
    prog = opts.get('onProgress')
    if not keep:
        for p in st['pairings']: p['crew'] = {'C': None, 'F': None, 'T': None}
        st['standby'] = None
    idx = buildIndex(st); sched = idx['sched']; hours = idx['hours']; pm = idx['pm']
    target = {p['id']: 60 * shareFor(p) for p in st['pilots']}

    def ratio(i): return hours[i] / target[i]

    def assign(pr, s, i):
        old = pr['crew'].get(s); h = pairingHours(pr)
        if old:
            sched[old] = [x for x in sched[old] if x is not pr]; hours[old] -= h
        pr['crew'][s] = i
        if i:
            sched[i].append(pr); hours[i] += h
    pilots = st['pilots']

    def hard(pr):
        w = 0
        for l in pr['legs']:
            for c in (l['from'], l['to']):
                cat = apCat(c, st)
                if cat == 'LHASA': w += 100
                elif cat != 'NONE': w += 10
        if pr['ac'] == 'A321': w += 5
        return w
    order = jsorted(st['pairings'], lambda a, b: ((hard(b) > 0) - (hard(a) > 0)) or (a['legs'][0]['dep'] - b['legs'][0]['dep']))
    gw = 0.35 if S.get('gapWeight') is None else S['gapWeight']

    def full(pr): return pr['crew'].get('C') and pr['crew'].get('F') and pr['crew'].get('T')

    def fillOne(pr, ignorePrefs):
        gdc = {}

        def gd(p):
            if p['id'] not in gdc:
                gdc[p['id']] = gw * (gapCost(p, sched[p['id']] + [pr], st) - gapCost(p, sched[p['id']], st))
            return gdc[p['id']]

        def free(s): return not pr['crew'].get(s)

        def ok(p): return personCheck(p, pr, st, idx, {'ignorePrefs': ignorePrefs})[0]
        cur = {s: (pr['crew'].get(s) and pm[pr['crew'][s]]) for s in SLOTS}
        crewv = list(pr['crew'].values())

        def sortR(arr): return jsort(arr, lambda a, b: ratio(a['id']) - ratio(b['id']))
        capt = sortR([p for p in pilots if isCaptClass(p['rank']) and p['id'] not in crewv and ok(p)])[:12] if free('C') else [cur['C']]
        fos = sortR([p for p in pilots if isFO(p['rank']) and p['id'] not in crewv and ok(p)])
        capT = sortR([p for p in pilots if isCaptClass(p['rank']) and p['id'] not in crewv and ok(p)])
        best = None
        for c in capt:
            Fl = [x for x in fos if x is not c][:10] if free('F') else [cur['F']]
            if not free('T'): Tl = [cur['T']]
            elif isNew(c['rank']): Tl = [x for x in capT if isInstr(x['rank']) and x is not c][:8]
            else: Tl = fos[:12] + [x for x in capT if x is not c][:6]
            for f in Fl:
                for t in Tl:
                    if not f or not t or f is t or t is c: continue
                    if crewIssue(pr, [c, f, t], st): continue
                    sc = ((ratio(c['id']) + gd(c)) if free('C') else 0) + ((ratio(f['id']) + gd(f)) if free('F') else 0) + ((ratio(t['id']) + gd(t)) if free('T') else 0)
                    if isFO(f['rank']) and isFO(t['rank']):
                        a, b = RANK_VAL[f['rank']], RANK_VAL[t['rank']]
                        if (a >= 6 and b >= 6) or (a <= 4 and b <= 4): sc += 0.15
                    if free('T') and isCaptClass(t['rank']) and not isNew(c['rank']): sc += 1.0
                    if nz: sc += nz() * 0.25
                    if not best or sc < best['sc']: best = {'sc': sc, 'c': c, 'f': f, 't': t}
            if best and index_obj(capt, c) >= 3: break
        if not best: return False
        if free('C'): assign(pr, 'C', best['c']['id'])
        if free('F'): assign(pr, 'F', best['f']['id'])
        if free('T'): assign(pr, 'T', best['t']['id'])
        return True

    n = 0
    for pr in order:
        if full(pr): continue
        fillOne(pr, not S.get('honorPrefs')); n += 1
        if prog: prog(n / len(order) * 0.6)

    def recomputeHours():
        for i in hours:
            s = 0
            for x in sched[i]: s += pairingHours(x)
            hours[i] = s
    for pr in order:
        if full(pr): continue
        pr['crew'] = {'C': None, 'F': None, 'T': None}
        for i in list(sched): sched[i] = [x for x in sched[i] if x is not pr]
        recomputeHours()
        if not fillOne(pr, True): fillOne(pr, True)
    recomputeHours()

    def slotCls(s, rank): return isCaptClass(rank) if s == 'C' else isFO(rank) if s == 'F' else True
    ip = not S.get('honorPrefs')
    passes = opts.get('passes') or 6
    for phase, gwX in ((0, gw), (1, gw * 0.3)):
        for it in range(passes):
            improved = 0
            for pr in st['pairings']:
                h = pairingHours(pr)
                for s in SLOTS:
                    curId = pr['crew'].get(s)
                    if not curId: continue
                    cp = pm[curId]; grp = rankGroup(cp['rank'])
                    bestQ = None; bestGain = 0
                    for q in pilots:
                        if q['id'] == curId or q['id'] in pr['crew'].values(): continue
                        if not slotCls(s, q['rank']): continue
                        if s != 'T' and rankGroup(q['rank']) != grp and not (s == 'C'): continue
                        before = (ratio(curId) - 1) ** 2 + (ratio(q['id']) - 1) ** 2
                        hc = (hours[curId] - h) / target[curId]; hq = (hours[q['id']] + h) / target[q['id']]
                        after = (hc - 1) ** 2 + (hq - 1) ** 2
                        gain = before - after
                        if gain + gwX * 3 <= bestGain + 1e-6: continue
                        sc0 = sched[curId]; sq0 = sched[q['id']]
                        gain -= gwX * (gapCost(cp, [x for x in sc0 if x is not pr], st) - gapCost(cp, sc0, st) + gapCost(q, sq0 + [pr], st) - gapCost(q, sq0, st))
                        if gain <= bestGain + 1e-6: continue
                        if not personCheck(q, pr, st, idx, {'ignorePrefs': ip})[0]: continue
                        crew = [q if x == s else pm.get(pr['crew'].get(x)) for x in SLOTS]
                        if crewIssue(pr, crew, st): continue
                        bestQ = q; bestGain = gain
                    if bestQ:
                        assign(pr, s, bestQ['id']); improved += 1
            if prog: prog(0.6 + 0.2 * phase + 0.2 * (it + 1) / passes)
            if not improved: break

    def slotOf(pr, i): return next((k for k in SLOTS if pr['crew'].get(k) == i), None)
    for it in range(4):
        sw = 0
        for g in GROUPS:
            mem = jsorted([p for p in pilots if rankGroup(p['rank']) == g], lambda a, b: hours[b['id']] - hours[a['id']])
            q = max(2, math.ceil(len(mem) / 4)); hi = mem[:q]; lo = list(reversed(mem[-q:]))
            for a in hi:
                for b in lo:
                    diff = hours[a['id']] - hours[b['id']]
                    if diff < 3: continue
                    done = False
                    for X in list(sched[a['id']]):
                        if done: break
                        sx = slotOf(X, a['id'])
                        if not slotCls(sx, b['rank']) or b['id'] in X['crew'].values(): continue
                        for Y in [None] + list(sched[b['id']]):
                            dh = pairingHours(X) - (pairingHours(Y) if Y else 0)
                            if dh <= 0.4 or dh >= diff: continue
                            if Y:
                                if Y is X or a['id'] in Y['crew'].values(): continue
                                if not slotCls(slotOf(Y, b['id']), a['rank']): continue
                            g0 = gapCost(a, sched[a['id']], st) + gapCost(b, sched[b['id']], st)
                            sy = Y and slotOf(Y, b['id'])
                            assign(X, sx, b['id'])
                            if Y: assign(Y, sy, a['id'])
                            okk = (personCheck(b, X, st, idx, {'ignorePrefs': ip})[0] and hours[b['id']] <= hardCap(st) + 1e-9 and
                                   (not Y or personCheck(a, Y, st, idx, {'ignorePrefs': ip})[0]) and
                                   not crewIssue(X, [pm.get(X['crew'].get(k)) for k in SLOTS], st) and
                                   (not Y or not crewIssue(Y, [pm.get(Y['crew'].get(k)) for k in SLOTS], st)) and
                                   gapCost(a, sched[a['id']], st) + gapCost(b, sched[b['id']], st) - g0 <= 0.6)
                            if okk:
                                done = True; sw += 1; break
                            if Y: assign(Y, sy, b['id'])
                            assign(X, sx, a['id'])
        if not sw: break
    if any(not full(pr) for pr in st['pairings']):
        for pr in st['pairings']:
            t = pr['crew'].get('T') and pm[pr['crew']['T']]
            if not t or not isCaptClass(t['rank']): continue
            fos = jsorted([q for q in pilots if isFO(q['rank']) and q['id'] not in pr['crew'].values()], lambda a, b: ratio(a['id']) - ratio(b['id']))
            for q in fos:
                if not personCheck(q, pr, st, idx, {'ignorePrefs': ip})[0]: continue
                if crewIssue(pr, [pm.get(pr['crew'].get('C')), pm.get(pr['crew'].get('F')), q], st): continue
                assign(pr, 'T', q['id']); break
    for pr in order:
        if not full(pr):
            if not fillOne(pr, ip): fillOne(pr, True)
    repairUnfilled(st)
    repairPrefs(st)
    trimPeaks(st)
    assignStandby(st)
    return summarize(st)


def trimPeaks(st):
    """削峰：工时明显高于本组（按份额折算）均值者，把任务转给合规且工时更低者"""
    for it in range(4):
        moved = 0; idx = buildIndex(st)
        gm = {}
        for g in GROUPS:
            xs = [idx['hours'][p['id']] / shareFor(p) for p in st['pilots'] if rankGroup(p['rank']) == g]
            s = 0
            for x in xs: s += x
            gm[g] = s / (len(xs) or 1)
        for p in st['pilots']:
            hp = idx['hours'][p['id']]
            if hp / shareFor(p) < gm[rankGroup(p['rank'])] + 5: continue
            for pr in jsorted(idx['sched'][p['id']], lambda a, b: pairingHours(a) - pairingHours(b)):
                slot = next(k for k in SLOTS if pr['crew'].get(k) == p['id']); h = pairingHours(pr)
                pr['crew'][slot] = None
                c = next((z for z in candidates(st, pr, slot) if z['ok'] and not z['warn'] and z['p']['id'] != p['id'] and z['hours'] + h < hp - 1), None)
                if c:
                    pr['crew'][slot] = c['p']['id']; moved += 1; break
                pr['crew'][slot] = p['id']
        if not moved: break


def repairPrefs(st):
    """被迫占用意向休息日的岗位，换成不占意向休息日的合规人员（或一步置换链）"""
    for pr in st['pairings']:
        for slot in SLOTS:
            i = pr['crew'].get(slot)
            if not i: continue
            p = next(x for x in st['pilots'] if x['id'] == i)
            prefs = p.get('prefs') or []
            if not any(d in prefs for d in daysTouched(pr, st)): continue
            pr['crew'][slot] = None
            c = next((z for z in candidates(st, pr, slot) if z['ok'] and not z['warn'] and z['p']['id'] != i), None)
            if c:
                pr['crew'][slot] = c['p']['id']; continue
            pr['crew'][slot] = i; keep = json.dumps([x['crew'] for x in st['pairings']]); pr['crew'][slot] = None
            repairUnfilled(st, True)
            if not pr['crew'].get(slot):
                back = json.loads(keep)
                for j, x in enumerate(st['pairings']): x['crew'] = back[j]


def repairUnfilled(st, strict=False):
    """对仍有空缺的任务做一步置换链：把某人从冲突任务中换出，由他人顶替"""
    for pr in st['pairings']:
        for slot in SLOTS:
            if pr['crew'].get(slot): continue
            direct = next((c for c in candidates(st, pr, slot) if c['ok'] and not c['warn']), None)
            if direct:
                pr['crew'][slot] = direct['p']['id']; continue
            cl = [c for c in candidates(st, pr, slot) if c['reasons'] and all(_RE_TR.match(r) for r in c['reasons'])]
            done = False
            for c in cl:
                ids = []
                for r in c['reasons']:
                    m = PR_RE.search(r); v = m.group(1) if m else None
                    if v not in ids: ids.append(v)
                others = [next((x for x in st['pairings'] if x['id'] == i), None) for i in ids]
                saved = [{'o': o, 's': next((k for k in SLOTS if o['crew'].get(k) == c['p']['id']), None)} for o in others]
                for x in saved: x['o']['crew'][x['s']] = None
                if not next((z for z in candidates(st, pr, slot) if z['p']['id'] == c['p']['id'] and z['ok']), None):
                    for x in saved: x['o']['crew'][x['s']] = c['p']['id']
                    continue
                pr['crew'][slot] = c['p']['id']; okAll = True
                for x in saved:
                    rep = next((z for z in candidates(st, x['o'], x['s']) if z['ok'] and not z['warn']), None)
                    if rep: x['o']['crew'][x['s']] = rep['p']['id']
                    else:
                        okAll = False; break
                if okAll:
                    done = True; break
                pr['crew'][slot] = None
                for x in saved: x['o']['crew'][x['s']] = c['p']['id']
            if not done and not strict:
                w = next((c for c in candidates(st, pr, slot) if c['ok']), None)
                if w: pr['crew'][slot] = w['p']['id']


def assignStandby(st):
    """每日 standbyPerDay 人备份（机长类/副驾驶交替），每人每月至多 maxStandbyPerPilot 天"""
    S = st['settings']; idx = buildIndex(st); st['standby'] = {p['id']: [] for p in st['pilots']}
    ds = dayStatus(st, idx)
    per = 1 if S.get('standbyPerDay') is None else S['standbyPerDay']
    cap = 1 if S.get('maxStandbyPerPilot') is None else S['maxStandbyPerPilot']

    def cnt(i): return len(st['standby'][i])
    for d in range(1, DAYS + 1):
        for k in range(int(per)):
            isC = (d + k) % 2 == 1

            def pick(c):
                xs = [p for p in st['pilots'] if isCaptClass(p['rank']) == c and not (c and isNew(p['rank'])) and cnt(p['id']) < cap and sbOK(ds[p['id']], d)]
                xs = jsorted(xs, lambda a, b: (cnt(a['id']) - cnt(b['id'])) or (idx['hours'][a['id']] - idx['hours'][b['id']]) or ((a['id'] > b['id']) - (a['id'] < b['id'])))
                return xs[0] if xs else None
            p = pick(isC) or pick(not isC)
            if p:
                ds[p['id']][d] = 'S'; st['standby'][p['id']].append(d)
    for p in st['pilots']: st['standby'][p['id']].sort()
