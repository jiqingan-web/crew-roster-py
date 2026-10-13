"""校验（validate）与指标（stats / summarize，含基尼系数）。"""
import math

from .rules import (SLOTS, SLOT_NAME, GROUPS, DAYS, buildIndex, slotRankOK, personCheck, daysTouched, crewIssue,
                    fdpDays, fmtH, apName, dayStatus, hardCap, rankGroup, specialAirportsOf, isNightLeg, restGaps,
                    isCaptClass, isFO, pairingHours, PR_RE, _num)
from .jsutil import fmt1


def validate(st):
    idx = buildIndex(st); S = st['settings']; out = []

    def add(type_, level, msg, pr=None, pid=None):
        out.append({'type': type_, 'level': level, 'msg': msg, 'pairing': pr and pr['id'], 'pilot': pid})
    for pr in st['pairings']:
        crew = [pr['crew'].get(s) and idx['pm'].get(pr['crew'][s]) for s in SLOTS]
        if any(not x for x in crew):
            add('未满员', 'hard', f"{pr['id']} 缺 {'/'.join(SLOT_NAME[s] for i, s in enumerate(SLOTS) if not crew[i])}", pr)
        for i, s in enumerate(SLOTS):
            p = crew[i]
            if not p: continue
            if not slotRankOK(s, p['rank']): add('岗位级别不符', 'hard', f"{pr['id']} {SLOT_NAME[s]}位 {p['name']}({p['rank']}) 级别不符", pr, p['id'])
            _, rs = personCheck(p, pr, st, idx, {'ignorePrefs': True})
            for r in rs:
                t = '请假冲突' if r.startswith('请假') else '时间重叠' if r.startswith('时间') else '休息不足' if r.startswith('休息') else None
                if t: add(t, 'hard', f"{pr['id']} {p['name']}：{r}", pr, p['id'])
            prefs = p.get('prefs') or []
            pf = [d for d in daysTouched(pr, st) if d in prefs]
            if pf: add('意向休息日未满足', 'soft', f"{pr['id']} {p['name']} 意向休息日 {','.join(map(str, pf))} 日被排班", pr, p['id'])
        if all(crew):
            iss = crewIssue(pr, crew, st)
            if iss:
                t = '新机长无教员' if '新机长' in iss else '特殊机场授权/搭配' if '特殊机场' in iss else '座位搭配规则'
                add(t, 'hard', f"{pr['id']} {iss}", pr)
        for dy in fdpDays(pr, st):
            if dy['planBuffer'] < 0: add('执勤期超限', 'hard', f"{pr['id']} D{dy['d']} 计划 FDP {fmtH(dy['planFdp'])} > 限制 {fmtH(dy['limit'])}", pr)
            if dy['planRestShort'] > 0: add('过夜休息偏短', 'info', f"{pr['id']} D{dy['d']}→D{dy['d'] + 1} 计划过夜休息 {fmtH(dy['planRest'])} < {_num(S.get('minOvernightRestH') or 10)}h（任务编排数据，需航线部门确认）", pr)
        bpa = S.get('bpTesterAirports') or []
        tl = [l for l in pr['legs'] if l['from'] in bpa]
        if tl and any(crew):
            names = []
            for l in tl:
                n = apName(l['from'], st)
                if n not in names: names.append(n)
            add('需血压测试仪', 'info', f"{pr['id']} 自 {'、'.join(names)} 出港（{'，'.join('D' + str(l['d']) + ' ' + l['flt'] for l in tl)}），始发站须配备血压测试仪", pr)
    seen = set(); ded = []
    for v in out:
        if v['type'] not in ('时间重叠', '休息不足'):
            ded.append(v); continue
        m = PR_RE.search(v['msg'])
        k = v['type'] + str(v['pilot']) + ','.join(sorted([v['pairing'], m.group(1) if m else '']))
        if k in seen: continue
        seen.add(k); ded.append(v)
    dsv = dayStatus(st, idx); sb = st.get('standby')
    cap1 = 1 if S.get('maxStandbyPerPilot') is None else S['maxStandbyPerPilot']
    for p in st['pilots']:
        for d in ((sb or {}).get(p['id']) or []):
            if dsv[p['id']][d] == 'D': ded.append({'type': '备份冲突', 'level': 'hard', 'msg': f"{p['name']} {d}日备份与飞行任务冲突", 'pilot': p['id']})
        if sb and len(sb.get(p['id']) or []) > cap1:
            ded.append({'type': '备份超限', 'level': 'soft', 'msg': f"{p['name']} 本月备份{len(sb[p['id']])}天，超过每人上限", 'pilot': p['id']})
    if sb:
        need = 1 if S.get('standbyPerDay') is None else S['standbyPerDay']
        for d in range(1, DAYS + 1):
            n = sum(1 for p in st['pilots'] if d in (sb.get(p['id']) or []) and dsv[p['id']][d] == 'S')
            if n < need: ded.append({'type': '备份人数不足', 'level': 'soft', 'msg': f"{d}日备份 {n}/{_num(need)} 人"})
    for p in st['pilots']:
        h = idx['hours'][p['id']]
        if h > hardCap(st) + 1e-9:
            ded.append({'type': '月小时超法规上限', 'level': 'hard', 'msg': f"{p['name']}({p['rank']}) {fmt1(h)}h > {_num(hardCap(st))}h（CAAC 月度硬上限）", 'pilot': p['id']})
    return ded


def stats(arr):
    n = len(arr)
    if not n: return {'n': 0, 'mean': 0, 'std': 0, 'min': 0, 'max': 0, 'gini': 0}
    s0 = 0
    for x in arr: s0 += x
    mean = s0 / n
    v = 0
    for x in arr: v += (x - mean) ** 2
    std = math.sqrt(v / n)
    s = sorted(arr); g = 0
    for i, x in enumerate(s): g += (2 * (i + 1) - n - 1) * x
    return {'n': n, 'mean': mean, 'std': std, 'min': s[0], 'max': s[-1], 'gini': g / (n * n * mean) if mean else 0, 'cv': std / mean if mean else 0}


def summarize(st):
    idx = buildIndex(st); v = validate(st); sbm = st.get('standby') or {}
    per = []
    for p in st['pilots']:
        sc = idx['sched'][p['id']]; touched = set()
        for pr in sc: touched.update(daysTouched(pr, st))
        per.append({'id': p['id'], 'name': p['name'], 'rank': p['rank'], 'group': rankGroup(p['rank']), 'hours': idx['hours'][p['id']], 'pairings': len(sc),
                    'overnights': sum(pr['ndays'] - 1 for pr in sc), 'special': sum(1 for pr in sc if specialAirportsOf(pr, st)),
                    'night': sum(sum(1 for l in pr['legs'] if isNightLeg(l)) for pr in sc), 'dutyDays': len(touched),
                    'gaps': restGaps(p, sc, st), 'standby': len(sbm.get(p['id']) or []),
                    'prefTotal': len(p.get('prefs') or []), 'prefOK': sum(1 for d in (p.get('prefs') or []) if d not in touched)})
    groups = {}
    for g in GROUPS:
        xs = [x for x in per if x['group'] == g]
        groups[g] = {'hours': stats([x['hours'] for x in xs]), 'overnights': stats([x['overnights'] for x in xs]),
                     'special': stats([x['special'] for x in xs]), 'night': stats([x['night'] for x in xs])}
    full = sum(1 for p in st['pairings'] if p['crew'].get('C') and p['crew'].get('F') and p['crew'].get('T'))
    byType = {}
    for x in v:
        byType.setdefault(x['type'], {'level': x['level'], 'n': 0}); byType[x['type']]['n'] += 1
    prefT = sum(x['prefTotal'] for x in per); prefOK = sum(x['prefOK'] for x in per)
    allG = [g for x in per for g in x['gaps']]
    gapDist = {'0-1': 0, '2': 0, '3': 0, '4': 0, '5+': 0}
    for g in allG: gapDist['0-1' if g <= 1 else '5+' if g >= 5 else str(g)] += 1
    lenDist = {}
    for p in st['pairings']: lenDist[str(p['ndays'])] = lenDist.get(str(p['ndays']), 0) + 1
    sbC = [x['standby'] for x in per if isCaptClass(x['rank'])]; sbF = [x['standby'] for x in per if isFO(x['rank'])]
    rhythm = {'gapDist': gapDist, 'gapN': len(allG), 'gap23': (sum(1 for g in allG if g in (2, 3)) / len(allG)) if allG else 0,
              'gapMean': (sum(allG) / len(allG)) if allG else 0, 'lenDist': lenDist,
              'standbyC': stats(sbC), 'standbyF': stats(sbF), 'standbyTotal': sum(x['standby'] for x in per)}
    for g in GROUPS: groups[g]['standby'] = stats([x['standby'] for x in per if x['group'] == g])
    th = 0
    for p in st['pairings']: th += pairingHours(p)
    return {'rhythm': rhythm, 'per': per, 'groups': groups, 'all': stats([x['hours'] for x in per]),
            'coverage': full / len(st['pairings']) if st['pairings'] else 0, 'full': full, 'total': len(st['pairings']),
            'violations': v, 'byType': byType, 'hard': sum(1 for x in v if x['level'] == 'hard'), 'soft': sum(1 for x in v if x['level'] == 'soft'),
            'info': sum(1 for x in v if x['level'] == 'info'), 'prefRate': prefOK / prefT if prefT else 1, 'prefOK': prefOK, 'prefT': prefT, 'totalHours': th}
