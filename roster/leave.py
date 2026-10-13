"""请假调配：单步 applyLeave 与多方案 leaveOptions（备份 / 节奏 / 工时 / 链式 / 备选 / 人工兜底），方案评估 evaluate。"""
import re
import time

from .rules import (SLOTS, buildIndex, daysTouched, candidates, slotRankOK, personCheck, crewIssue, pairingHours, hardCap,
                    restGaps, specialAirportsOf, apName, isNew, PR_RE)
from .metrics import summarize
from .jsutil import clone, jsort, jsorted, jround

_PAREN = re.compile(r'\(.*\)')
_COLON = re.compile(r'：.*')


def _sorted_ints(xs): return sorted(set(xs))


def applyLeave(st, pilotId, days):
    p = next((x for x in st['pilots'] if x['id'] == pilotId), None)
    if not p: return None
    before = clone([{'id': x['id'], 'crew': x['crew']} for x in st['pairings']])
    p['leave'] = _sorted_ints((p.get('leave') or []) + list(days))
    p['prefs'] = [d for d in (p.get('prefs') or []) if d not in p['leave']]
    if st.get('standby') and st['standby'].get(pilotId): st['standby'][pilotId] = [d for d in st['standby'][pilotId] if d not in p['leave']]
    affected = [pr for pr in st['pairings'] if pilotId in pr['crew'].values() and any(d in days for d in daysTouched(pr, st))]
    changes, unresolved = [], []
    for pr in affected:
        slot = next(s for s in SLOTS if pr['crew'].get(s) == pilotId); pr['crew'][slot] = None
        cands = [c for c in candidates(st, pr, slot) if c['ok']]
        noWarn = [c for c in cands if not c['warn']]
        if noWarn: cands = noWarn
        d0 = daysTouched(pr, st)[0]
        jsort(cands, lambda a, b: ((d0 in b['standby']) - (d0 in a['standby'])) or ((len(b['standby']) > 0) - (len(a['standby']) > 0)) or (a['hours'] - b['hours']))
        if cands:
            c0 = cands[0]; q = c0['p']; pr['crew'][slot] = q['id']
            if c0['standby'] and st.get('standby'): st['standby'][q['id']] = [d for d in st['standby'][q['id']] if d not in c0['standby']]
            changes.append({'pairing': pr['id'], 'slot': slot, 'from': p, 'to': q, 'fromStandby': len(c0['standby']) > 0,
                            'note': f"调用备份（{','.join(map(str, c0['standby']))}日备份）" if c0['standby'] else ('（占用其意向休息日）' if c0['warn'] else '')})
        else:
            alls = [c for c in candidates(st, pr, slot) if slotRankOK(slot, c['p']['rank'])]
            unresolved.append({'pairing': pr['id'], 'slot': slot, 'reason': '无合规替补；候选人主要不满足：' + '，'.join(_topReasons(alls))})
    return {'pilot': p, 'days': days, 'affected': [x['id'] for x in affected], 'changes': changes, 'unresolved': unresolved, 'before': before}


def _topReasons(alls):
    cnt = {}
    for c in alls:
        for r in c['reasons']:
            k = _COLON.sub('', _PAREN.sub('', r, count=1), count=1)
            cnt[k] = cnt.get(k, 0) + 1
    return [f"{k}×{n}" for k, n in sorted(cnt.items(), key=lambda kv: -kv[1])[:4]]


def prOf(w, i): return next((x for x in w['pairings'] if x['id'] == i), None)


def rhythmCost(p, lst, st):
    s = 0
    for g in restGaps(p, lst, st): s += 3 if g <= 1 else 1 if g == 4 else 2 if g >= 5 else 0
    return s


def addCost(w, p, pr, idx):
    sc = idx['sched'][p['id']]; return rhythmCost(p, sc + [pr], w) - rhythmCost(p, sc, w)


def takeStandby(w, pid, pr):
    if w.get('standby') and w['standby'].get(pid):
        td = daysTouched(pr, w); w['standby'][pid] = [d for d in w['standby'][pid] if d not in td]


def chainOpts(w, pr, slot, ban, mx=3):
    """链式调换：从另一任务 Q 调来 q 顶替 pr，再为 Q 找替补"""
    idx = buildIndex(w); out = []; td = daysTouched(pr, w); tries = 0
    qs = [q for q in w['pilots'] if slotRankOK(slot, q['rank']) and q['id'] not in ban and q['id'] not in pr['crew'].values()
          and not any(d in (q.get('leave') or []) or d in (q.get('prefs') or []) for d in td)]
    qs = jsorted(qs, lambda a, b: idx['hours'][a['id']] - idx['hours'][b['id']])
    for q in qs:
        if len(out) >= (mx or 3) or tries > 80: break
        _, rs = personCheck(q, pr, w, idx, {'ignorePrefs': True})
        if not rs: continue
        ids = []
        for r in rs:
            m = PR_RE.search(r); v = m.group(1) if m else None
            if v not in ids: ids.append(v)
        if len(ids) != 1 or not ids[0] or any(not PR_RE.search(r) and '超出月上限' not in r for r in rs): continue
        Q = prOf(w, ids[0]); sQ = next((x for x in SLOTS if Q['crew'].get(x) == q['id']), None)
        if not sQ or ('PR:' + Q['id']) in ban: continue
        tries += 1
        Q['crew'][sQ] = None; idx2 = buildIndex(w)
        ok2, _ = personCheck(q, pr, w, idx2, {'ignorePrefs': True})
        crew = [q if x == slot else (pr['crew'].get(x) and idx2['pm'].get(pr['crew'][x])) for x in SLOTS]
        if ok2 and not crewIssue(pr, crew, w) and not (idx2['hours'][q['id']] + pairingHours(pr) > hardCap(w)):
            pr['crew'][slot] = q['id']
            bfs = [c for c in candidates(w, Q, sQ) if c['ok'] and c['p']['id'] not in ban and c['p']['id'] != q['id']]
            bfs = jsorted(bfs, lambda a, b: (bool(a['warn']) - bool(b['warn'])) or ((len(b['standby']) > 0) - (len(a['standby']) > 0)) or (a['hours'] - b['hours']))
            pr['crew'][slot] = None
            if bfs: out.append({'q': q, 'Q': Q, 'sQ': sQ, 'bf': bfs[0]})
        Q['crew'][sQ] = q['id']
    return out


def blockReason(w, pr, slot):
    alls = [c for c in candidates(w, pr, slot) if slotRankOK(slot, c['p']['rank'])]
    rules = []; sp = specialAirportsOf(pr, w)
    if any(l['to'] == 'ZULS' or l['from'] == 'ZULS' for l in pr['legs']): rules.append('拉萨航段须两名 J3 及以上')
    if sp: rules.append('特殊机场 ' + '、'.join(apName(c, w) for c in sp) + ' 须授权/级别搭配')
    crew = [next((p for p in w['pilots'] if p['id'] == pr['crew'].get(x)), None) for x in SLOTS if pr['crew'].get(x)]
    crew = [c for c in crew if c]
    if any(isNew(x['rank']) for x in crew) and slot != 'F': rules.append('新机长所在机组须有 TL 及以上教员')
    bpa = w['settings'].get('bpTesterAirports') or []
    bp = [l for l in pr['legs'] if l['from'] in bpa]
    if bp:
        names = []
        for l in bp:
            n = apName(l['from'], w)
            if n not in names: names.append(n)
        rules.append('始发站 ' + '、'.join(names) + ' 须配备血压测试仪（提醒）')
    return {'top': _topReasons(alls), 'rules': rules}


STRATS = {
    'standby': {'name': '调用当日备份', 'desc': '优先使用备份（Standby）人员'},
    'rhythm': {'name': '休息人员 · 节奏最优', 'desc': '空闲且合格，尽量不打乱 3–4 天飞 / 2–3 天休节奏'},
    'hours': {'name': '休息人员 · 工时均衡', 'desc': '空闲且合格，优先本月小时较少者'},
    'alt': {'name': '休息人员 · 备选', 'desc': '与其他方案不同的另一批候选人'},
    'chain': {'name': '链式调换', 'desc': '从其他任务调人顶替，再为该任务补位（≤2 层）'}}


def fillVac(w, vac, key, ban, usedRest):
    steps = []
    for v in vac:
        pr = prOf(w, v['id']); idx = buildIndex(w)
        cands = [c for c in candidates(w, pr, v['slot']) if c['ok'] and c['p']['id'] not in ban]
        sb = jsorted([c for c in cands if c['standby']], lambda a, b: a['hours'] - b['hours'])
        rest = [c for c in cands if not c['standby']]
        noPref = [c for c in rest if not c['warn']]
        if noPref: rest = noPref
        for c in rest: c['rc'] = addCost(w, c['p'], pr, idx)
        byRhythm = jsorted(rest, lambda a, b: (a['rc'] - b['rc']) or (a['hours'] - b['hours']))
        byHours = jsorted(rest, lambda a, b: (a['hours'] - b['hours']) or (a['rc'] - b['rc']))
        pick = None; chain = None

        def restPick(lst): return {'c': lst[0], 'type': 'rest'} if lst else None
        sb0 = {'c': sb[0], 'type': 'standby'} if sb else None
        if key == 'standby': pick = sb0 or restPick(byRhythm)
        elif key == 'rhythm': pick = restPick(byRhythm)
        elif key == 'hours': pick = restPick(byHours)
        elif key == 'alt': pick = restPick([c for c in byRhythm if c['p']['id'] not in usedRest]) or restPick(byRhythm)
        elif key == 'chain':
            co = chainOpts(w, pr, v['slot'], ban, 1); chain = co[0] if co else None
            if not chain: pick = sb0 or restPick(byRhythm)
        if not pick and not chain and key != 'chain':
            co = chainOpts(w, pr, v['slot'], ban, 1); chain = co[0] if co else None
        if not pick and not chain and sb0: pick = sb0
        base = {'pairing': pr['id'], 'slot': v['slot'], 'from': v.get('from'), 'why': v.get('why')}
        if chain:
            q, Q, sQ, bf = chain['q'], chain['Q'], chain['sQ'], chain['bf']
            Q['crew'][sQ] = bf['p']['id']; pr['crew'][v['slot']] = q['id']; takeStandby(w, bf['p']['id'], Q); takeStandby(w, q['id'], pr)
            ban.add(q['id']); ban.add(bf['p']['id'])
            steps.append({**base, 'type': 'chain', 'to': q['id'], 'chain': {'pairing': Q['id'], 'slot': sQ, 'from': q['id'], 'to': bf['p']['id'], 'fromStandby': len(bf['standby']) > 0}})
        elif pick:
            q = pick['c']['p']; pr['crew'][v['slot']] = q['id']; takeStandby(w, q['id'], pr); ban.add(q['id'])
            if pick['type'] == 'rest': usedRest.add(q['id'])
            steps.append({**base, 'type': pick['type'], 'to': q['id'], 'prefWarn': pick['c']['warn'] or ''})
        else:
            steps.append({**base, 'type': 'manual', 'block': blockReason(w, pr, v['slot'])})
    return steps


def leaveOptions(st, pilotId, days, opt=None):
    opt = opt or {}; t0 = time.time()
    base = clone(st); p = next((x for x in base['pilots'] if x['id'] == pilotId), None)
    if not p: return None
    p['leave'] = _sorted_ints((p.get('leave') or []) + list(days)); p['prefs'] = [d for d in (p.get('prefs') or []) if d not in p['leave']]
    if base.get('standby') and base['standby'].get(pilotId): base['standby'][pilotId] = [d for d in base['standby'][pilotId] if d not in p['leave']]
    affected = [pr for pr in base['pairings'] if pilotId in pr['crew'].values() and any(d in days for d in daysTouched(pr, base))]
    affected = jsorted(affected, lambda a, b: a['start'] - b['start'])
    vac = []
    for pr in affected:
        slot = next(x for x in SLOTS if pr['crew'].get(x) == pilotId); pr['crew'][slot] = None; vac.append({'id': pr['id'], 'slot': slot})
    before = summarize(st); bIdx = buildIndex(st)
    if not vac:
        sol = evaluate(st, base, [], 'none', before, bIdx); sol['name'] = '仅登记请假'; sol['desc'] = '所选日期内无任务，无需调配'
        return {'pilot': p, 'days': days, 'affected': [], 'solutions': [sol], 'ms': int((time.time() - t0) * 1000)}
    sols = []; usedRest = set(); keys = ['standby', 'rhythm', 'hours', 'chain', 'alt', 'alt', 'alt', 'alt']; uniq = set()
    for ki, key in enumerate(keys):
        if ki >= 5 and len(uniq) >= 3: break
        w = clone(base); ban = {pilotId}
        steps = fillVac(w, [{'from': pilotId, **v} for v in vac], key, ban, usedRest)
        sol = evaluate(st, w, steps, key, before, bIdx)
        sol['name'] = STRATS[key]['name'] + (' ' + str(ki - 3) if ki > 4 else ''); sol['desc'] = STRATS[key]['desc']
        sols.append(sol); uniq.add(sol['sig'])
    seen = set(); out = []
    for x in sols:
        if x['sig'] in seen: continue
        seen.add(x['sig']); out.append(x)
    jsort(out, lambda a, b: a['score'] - b['score'])
    ok = [x for x in out if not x['unresolved']]
    if ok: ok[0]['recommended'] = True
    if not ok:
        for x in out: x['manual'] = True
    return {'pilot': p, 'days': days, 'affected': vac, 'solutions': out[:opt.get('max') or 5], 'ms': int((time.time() - t0) * 1000)}


def evaluate(st0, w, steps, key, before, bIdx):
    s = summarize(w); idx = buildIndex(w); pm = {p['id']: p for p in w['pilots']}
    ids = []

    def addId(i):
        if i not in ids: ids.append(i)
    for x in steps:
        if x.get('from') and x.get('type') != 'manual': addId(x['from'])
        if x.get('to'): addId(x['to'])
        if x.get('chain'): addId(x['chain']['from']); addId(x['chain']['to'])
    hc = hardCap(w); people = []
    for i in ids:
        p = pm[i]; hb = bIdx['hours'].get(i, 0); ha = idx['hours'][i]
        bids = {o['id'] for o in bIdx['sched'].get(i, [])}
        newPr = [pr for pr in idx['sched'][i] if pr['id'] not in bids]
        prefs = p.get('prefs') or []; ph = []
        for pr in newPr:
            for d in daysTouched(pr, w):
                if d in prefs and d not in ph: ph.append(d)
        rb = rhythmCost(p, bIdx['sched'].get(i, []), w); ra = rhythmCost(p, idx['sched'][i], w)
        people.append({'id': i, 'name': p['name'], 'rank': p['rank'], 'hb': hb, 'ha': ha, 'overHard': ha > hc + 1e-9, 'prefHit': ph, 'rhythm': ra - rb})
    days = sorted({d for x in steps for d in daysTouched(prOf(w, x['pairing']), w)})
    sbm = w.get('standby') or {}
    sbLeft = [{'d': d, 'n': sum(1 for p in w['pilots'] if d in (sbm.get(p['id']) or []))} for d in days]
    unresolved = sum(1 for x in steps if x.get('type') == 'manual')
    hardNew = s['hard'] - (unresolved if unresolved else 0)
    bpa = w['settings'].get('bpTesterAirports') or []
    bp = [pr['id'] for pr in (prOf(w, x['pairing']) for x in steps if x.get('type') != 'manual') if any(l['from'] in bpa for l in pr['legs'])]
    giniD = s['all']['gini'] - before['all']['gini']
    prefN = sum(len(x['prefHit']) for x in people)
    rhy = 0
    for x in people: rhy += max(0, x['rhythm'])
    nSb = sum(1 for x in steps if x.get('type') == 'standby' or (x.get('chain') and x['chain']['fromStandby']))
    nChain = sum(1 for x in steps if x.get('type') == 'chain')
    outR = sum(1 for x in people if x['overHard'])
    score = unresolved * 1000 + max(0, hardNew) * 500 + outR * 200 + prefN * 25 + rhy * 4 + max(0, giniD) * 2000 + nChain * 6 + len(people) * 2 - nSb * 5 \
        + sum(1 for x in sbLeft if x['n'] == 0) * 3
    return {'key': key, 'steps': steps, 'state': w, 'people': people, 'giniB': before['all']['gini'], 'giniA': s['all']['gini'], 'giniD': giniD,
            'sbLeft': sbLeft, 'unresolved': unresolved, 'hard': s['hard'], 'hardNew': max(0, hardNew), 'bp': bp, 'prefN': prefN, 'rhy': rhy,
            'score': jround(score * 10) / 10, 'gap23B': before['rhythm']['gap23'], 'gap23A': s['rhythm']['gap23'],
            'sig': '|'.join(x['pairing'] + str(x.get('slot', 'undefined')) + (x.get('to') or 'x') + ((x['chain']['pairing'] + x['chain']['to']) if x.get('chain') else '') for x in steps)}
