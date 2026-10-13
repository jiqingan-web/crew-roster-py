"""执勤监控：计划风险、按实际/预计时刻滚动监控、下游影响、拆分换组与处置方案卡片。"""
import time

from .rules import (SLOTS, DAY, buildIndex, fdpDays, legKey, report, release, apName, fmtT, fmtH, _num)
from .metrics import summarize
from .leave import fillVac, evaluate, STRATS
from .jsutil import clone, jsort, jsorted, jround, index_obj

RISK_ORDER = {'over': 0, 'high': 1, 'med': 2, 'low': 3}
RISK_TXT = {'over': '超限', 'high': '高', 'med': '中', 'low': '低'}


def migrateDelays(st):
    """旧版 st.delays {legKey: 分钟} → st.actuals（仅该段本身的预计起飞/落地，不级联）"""
    if not st.get('delays'):
        st.pop('delays', None); st['actuals'] = st.get('actuals') or {}; return st
    st['actuals'] = st.get('actuals') or {}
    legs = {legKey(l): l for p in st['pairings'] for l in p['legs']}
    for k, v in st['delays'].items():
        try: v = float(v) if not isinstance(v, (int, float)) else v
        except (TypeError, ValueError): v = 0
        l = legs.get(k)
        if l and v > 0 and k not in st['actuals']:
            st['actuals'][k] = {'dep': l['dep'] + v, 'arr': l['arr'] + v, 'kind': 'est'}
    del st['delays']
    return st


def pairingRisk(pr, st, acts=None):
    ds = fdpDays(pr, st, acts); rk = 'risk' if acts else 'planRisk'
    w = jsorted(ds, lambda a, b: (RISK_ORDER[a[rk]] - RISK_ORDER[b[rk]]) or (a['buffer'] - b['buffer']))
    w = w[0] if w else None
    return {'days': ds, 'worst': w, 'risk': w[rk] if w else 'low'}


def fdpRiskSummary(st):
    rows = []
    for pr in st['pairings']:
        for dy in fdpDays(pr, st):
            rows.append({'pr': pr['id'], 'd': dy['d'], 'date': dy['date'], 'legs': len(dy['legs']), 'fdp': dy['planFdp'], 'limit': dy['limit'],
                         'buffer': dy['planBuffer'], 'risk': dy['planRisk'], 'restAfter': dy['planRest'], 'restShort': dy['planRestShort']})
    cnt = {'over': 0, 'high': 0, 'med': 0, 'low': 0}
    for r in rows: cnt[r['risk']] += 1
    jsort(rows, lambda a, b: a['buffer'] - b['buffer'])
    return {'rows': rows, 'cnt': cnt, 'n': len(rows), 'restShort': [r for r in rows if r['restShort'] and r['restShort'] > 0]}


def downstream(st, pr, days, idx=None):
    """机组成员下一任务前休息是否被压缩，以及任务内过夜休息压缩"""
    idx = idx or buildIndex(st); S = st['settings']; rel = S.get('releaseMin') or 30; out = []
    end = days[-1]['end'] + rel
    for s in SLOTS:
        i = pr['crew'].get(s)
        if not i: continue
        rl = release(pr, st)
        nxs = jsorted([o for o in idx['sched'].get(i, []) if o is not pr and o['id'] != pr['id'] and report(o, st) >= rl], lambda a, b: report(a, st) - report(b, st))
        if not nxs: continue
        nx = nxs[0]; gap = report(nx, st) - end
        if gap < S['minRestH'] * 60:
            out.append({'pilot': i, 'slot': s, 'next': nx['id'], 'nextSlot': next((k for k in SLOTS if nx['crew'].get(k) == i), None), 'gap': gap, 'short': S['minRestH'] * 60 - gap})
    for dy in days:
        if dy['restShort'] and dy['restShort'] > 0: out.append({'overnight': True, 'd': dy['d'], 'short': dy['restShort'], 'restAfter': dy['restAfter']})
    return out


def dutyMonitor(st, date):
    acts = st.get('actuals') or {}; idx = buildIndex(st); res = []
    for pr in st['pairings']:
        ds = fdpDays(pr, st, acts); dy = next((x for x in ds if x['date'] == date), None)
        if not dy: continue
        dn = [x for x in downstream(st, pr, ds, idx) if not x.get('overnight') or x['d'] >= dy['d']]
        res.append({'pr': pr, 'day': dy, 'days': ds, 'downstream': dn, 'exceed': any(x['exceed'] > 0 and x['date'] >= date for x in ds)})
    return jsort(res, lambda a, b: (b['exceed'] - a['exceed']) or (a['day']['buffer'] - b['day']['buffer']))


def splitPairing(w, pr, j):
    """legs[:j] 留在原任务，legs[j:] 成为新任务 PRxxx-B（新机组接手）；j 为当日首段时即整组替换"""
    A, B = pr['legs'][:j], pr['legs'][j:]; d0 = B[0]['d']; rep = w['settings'].get('reportMin') or 60

    def mk(i, legs): return {'id': i, 'start': int((legs[0]['dep'] - rep) // DAY) + 1, 'ndays': 0, 'ac': 'A321' if any(l.get('ac') == 'A321' for l in legs) else 'A320', 'legs': legs, 'crew': {'C': None, 'F': None, 'T': None}}
    nb = mk(pr['id'] + '-B', [{**l, 'd': l['d'] - d0 + 1} for l in B]); nb['ndays'] = nb['legs'][-1]['d']; nb['freshAt'] = legKey(B[0]); nb['splitFrom'] = pr['id']
    if A:
        pr['legs'] = A; pr['ndays'] = A[-1]['d']; w['pairings'].insert(index_obj(w['pairings'], pr) + 1, nb)
        return {'A': pr, 'B': nb}
    pr['freshAt'] = legKey(pr['legs'][0])
    return {'A': None, 'B': pr}


def fdpEval(sol, w, acts, ids):
    ex = 0; rv = 0; idx = buildIndex(w)
    for i in ids:
        p = next((x for x in w['pairings'] if x['id'] == i), None)
        if not p or not p['legs']: continue
        ds = fdpDays(p, w, acts)
        ex += sum(1 for x in ds if x['exceed'] > 0); rv += len(downstream(w, p, ds, idx))
    sol['fdpAfter'] = ex; sol['restAfterV'] = rv; sol['score'] = jround((sol['score'] + ex * 800 + rv * 300) * 10) / 10


def fdpOptions(st, prId, opt=None):
    opt = opt or {}; t0 = time.time(); acts = st.get('actuals') or {}
    pr0 = next((p for p in st['pairings'] if p['id'] == prId), None)
    if not pr0: return None
    ds0 = fdpDays(pr0, st, acts); idx0 = buildIndex(st)
    ex = next((x for x in ds0 if x['exceed'] > 0), None); dn0 = downstream(st, pr0, ds0, idx0)
    crew0 = dict(pr0['crew']); before = summarize(st); bIdx = idx0
    sols = []; usedRest = set(); splits = []
    if ex:
        exI = ex['exLeg']['i']
        cand = [x['i'] for x in ex['legs'] if x['i'] <= exI and pr0['legs'][x['i']]['from'] == 'ZUUU']
        if cand:
            splits.append(cand[-1])
            if cand[0] != cand[-1]: splits.append(cand[0])

    def mkBase(j):
        w = clone(st); pr = next(p for p in w['pairings'] if p['id'] == prId); sp = splitPairing(w, pr, j)
        vac = [{'id': sp['B']['id'], 'slot': s, 'from': crew0.get(s)} for s in SLOTS]
        if not sp['A']:
            for s in SLOTS: sp['B']['crew'][s] = None
        return w, sp, vac
    for j in splits:
        for key in ['standby', 'rhythm', 'hours', 'chain', 'alt']:
            w, sp, vac = mkBase(j); ban = {x for x in crew0.values() if x}
            st0 = pr0['legs'][j]
            head = {'pairing': prId, 'type': 'split', 'at': j, 'station': st0['from'], 'time': st0['dep'], 'newPairing': sp['B']['id'], 'whole': not sp['A'], 'legsB': len(sp['B']['legs'])}
            steps = [head] + fillVac(w, vac, key, ban, usedRest)
            if sp['A']:
                dA = fdpDays(sp['A'], w, acts)
                for x in downstream(w, sp['A'], dA):
                    if x.get('overnight'): continue
                    q = next(p for p in w['pairings'] if p['id'] == x['next'])
                    if q['crew'].get(x['nextSlot']) == x['pilot']:
                        q['crew'][x['nextSlot']] = None
                        steps += fillVac(w, [{'id': q['id'], 'slot': x['nextSlot'], 'from': x['pilot'], 'why': '休息不足'}], key, ban, usedRest)
            sol = evaluate(st, w, steps, key, before, bIdx); fdpEval(sol, w, acts, [prId, sp['B']['id']])
            sname = STRATS[key]['name'].replace('休息人员 · ', '')
            sol['name'] = (f"拆分换组@{apName(st0['from'], st)}" if sp['A'] else '整组替换') + ' · ' + sname
            sol['desc'] = (f"原机组飞至 {apName(st0['from'], st)}（D{st0['d']} {fmtT(st0['dep'])} 前）下机，新机组在成都基地接手 {len(sp['B']['legs'])} 段"
                           if sp['A'] else f"当日从成都出发前更换整组机组（{len(pr0['legs']) - j} 段）")
            sols.append(sol)
    seen = set(); out = []
    for x in sols:
        if x['sig'] in seen: continue
        seen.add(x['sig']); out.append(x)
    if not ex and any(not x.get('overnight') for x in dn0):
        for key in ['standby', 'rhythm', 'hours', 'chain']:
            w = clone(st); ban = {x for x in crew0.values() if x}; steps = []
            for x in dn0:
                if x.get('overnight'): continue
                q = next(p for p in w['pairings'] if p['id'] == x['next']); q['crew'][x['nextSlot']] = None
                steps += fillVac(w, [{'id': q['id'], 'slot': x['nextSlot'], 'from': x['pilot'], 'why': '休息不足'}], key, ban, usedRest)
            sol = evaluate(st, w, steps, key, before, bIdx); fdpEval(sol, w, acts, [prId])
            sol['name'] = '后续任务换人 · ' + STRATS[key]['name'].replace('休息人员 · ', ''); sol['desc'] = '延误压缩了机组下一任务前的休息，替换受影响成员'
            if sol['sig'] not in seen:
                seen.add(sol['sig']); out.append(sol)
    reasons = []
    S = st['settings']
    if ex and not splits: reasons.append(f"D{ex['d']} 超限前无从成都出发的航段，无法在基地换组；需从成都摆渡（DH）新机组至 {apName(ex['legs'][0]['leg']['from'], st)} 或调整/取消航段")
    if ex:
        el = ex['exLeg']['leg']
        reasons.append(f"D{ex['d']} 预计 FDP {fmtH(ex['fdp'])} 超过限制 {fmtH(ex['limit'])}（{len(ex['legs'])} 段，报到 {fmtT(ex['start'])}），超 {_num(ex['exceed'])} 分钟，自 {el['flt']} {apName(el['from'], st)}-{apName(el['to'], st)} 起")
    for x in dn0:
        reasons.append(f"D{x['d']} 过夜休息仅 {fmtH(x['restAfter'])}，少于 {_num(S.get('minOvernightRestH') or 10)}h（差 {_num(x['short'])} 分钟）：可延后次日报到或换组" if x.get('overnight')
                       else f"{idx0['pm'][x['pilot']]['name']} 下一任务 {x['next']} 前休息仅 {fmtH(x['gap'])}（差 {_num(x['short'])} 分钟）")
    man = {'key': 'manual', 'name': '取消/调整超限航段（人工处理）' if ex else '人工处理', 'desc': '由运控协调：取消或延后航段、摆渡机组、申请延长等',
           'steps': [{'pairing': prId, 'type': 'manual', 'block': {'rules': reasons, 'top': []}}], 'people': [], 'giniB': before['all']['gini'], 'giniA': before['all']['gini'],
           'giniD': 0, 'sbLeft': [], 'unresolved': 1, 'hard': before['hard'], 'bp': [], 'prefN': 0, 'rhy': 0, 'score': 5000, 'state': None, 'manual': True,
           'fdpAfter': 1 if ex else 0, 'restAfterV': len(dn0), 'sig': 'manual'}
    jsort(out, lambda a, b: a['score'] - b['score']); out = out[:(opt.get('max') or 5) - 1]; out.append(man)
    ok = [x for x in out if not x['unresolved'] and not x['fdpAfter']]
    if ok: ok[0]['recommended'] = True
    return {'pairing': pr0, 'days': ds0, 'exceed': ex, 'downstream': dn0, 'solutions': out, 'ms': int((time.time() - t0) * 1000)}
