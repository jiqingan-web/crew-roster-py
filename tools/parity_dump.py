"""用 Python 版生成与 tools/parity_dump.js 完全相同结构的对照数据。python tools/parity_dump.py > /tmp/py.json"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import roster as C  # noqa: E402
from roster.jsutil import jround, jsorted  # noqa: E402


def r4(x): return jround(x * 1e6) / 1e6


def solv(s):
    return {'name': s['name'], 'score': s['score'], 'sig': s['sig'], 'hard': s['hard'], 'unresolved': s['unresolved'], 'recommended': bool(s.get('recommended')),
            'fdpAfter': s.get('fdpAfter'), 'restAfterV': s.get('restAfterV'), 'giniD': r4(s.get('giniD') or 0)}


def dump():
    out = {}
    st = C.generateSample()
    th = 0
    for p in st['pairings']: th += C.pairingHours(p)
    out['sample'] = {'pilots': len(st['pilots']), 'pairings': len(st['pairings']), 'totalH': r4(th)}
    s = C.autoFill(st)
    out['autofill'] = {'coverage': s['coverage'], 'hard': s['hard'], 'soft': s['soft'], 'info': s['info'], 'byType': s['byType'], 'attempt': s['attempt'],
                       'all': {k: r4(v) for k, v in s['all'].items()},
                       'groups': {g: {'mean': r4(x['hours']['mean']), 'min': r4(x['hours']['min']), 'max': r4(x['hours']['max']), 'gini': r4(x['hours']['gini'])} for g, x in s['groups'].items()},
                       'prefOK': s['prefOK'], 'prefT': s['prefT'], 'gap23': r4(s['rhythm']['gap23']), 'gapDist': s['rhythm']['gapDist'], 'standbyTotal': s['rhythm']['standbyTotal'],
                       'crew': [[p['crew']['C'], p['crew']['F'], p['crew']['T']] for p in st['pairings']], 'standby': st['standby']}
    filled = json.dumps(st, ensure_ascii=False)
    w = json.loads(filled); idx = C.buildIndex(w)
    cap = jsorted([p for p in w['pilots'] if p['rank'] == 'J3'], lambda a, b: len(idx['sched'][b['id']]) - len(idx['sched'][a['id']]))[0]
    days = []
    for pr in idx['sched'][cap['id']][1:3]:
        for d in C.daysTouched(pr, w):
            if d not in days: days.append(d)
    r = C.applyLeave(w, cap['id'], days); s2 = C.summarize(w)
    out['applyLeave'] = {'pilot': cap['id'], 'days': days, 'affected': r['affected'], 'changes': [[c['pairing'], c['slot'], c['to']['id'], c['fromStandby']] for c in r['changes']],
                         'unresolved': len(r['unresolved']), 'hardAfter': s2['hard']}
    out['leaveOptions'] = {}
    w = json.loads(filled); ix = C.buildIndex(w)
    for lab, pred in [('机长', lambda p: p['rank'] == 'J3'), ('副驾驶', lambda p: C.isFO(p['rank'])), ('新机长', lambda p: C.isNew(p['rank'])), ('教员', lambda p: C.isInstr(p['rank']))]:
        p = jsorted([x for x in w['pilots'] if pred(x)], lambda a, b: len(ix['sched'][b['id']]) - len(ix['sched'][a['id']]))[0]
        a, b = ix['sched'][p['id']][1], ix['sched'][p['id']][2]
        days = list(range(a['start'], b['start'] + b['ndays']))
        r = C.leaveOptions(w, p['id'], days)
        out['leaveOptions'][lab] = {'pilot': p['id'], 'days': days, 'affected': len(r['affected']), 'solutions': [solv(x) for x in r['solutions']]}
    w = json.loads(filled); w['settings']['hardMaxHours'] = 40
    lh = next((pr for pr in w['pairings'] if any(l['to'] == 'ZULS' for l in pr['legs'])), w['pairings'][0])
    r = C.leaveOptions(w, lh['crew']['C'], C.daysTouched(lh, w)); blk = next(x for x in r['solutions'][0]['steps'] if x.get('block'))
    out['fallback'] = {'solutions': [solv(x) for x in r['solutions']], 'allManual': all(x['unresolved'] > 0 and x.get('manual') for x in r['solutions']),
                       'rules': blk['block']['rules'], 'top': blk['block']['top']}
    w = json.loads(filled); p = next(x for x in w['pilots'] if x['name'] == '毛华' and x['rank'] == 'J3')
    r = C.leaveOptions(w, p['id'], [9, 10, 11, 12, 13, 14]); ok = [x for x in r['solutions'] if not x['unresolved'] and x['hard'] == 0]
    out['maohua'] = {'solutions': [solv(x) for x in r['solutions']], 'maxH': r4(max(y['ha'] for x in ok for y in x['people']))}
    w = json.loads(filled); sm = C.fdpRiskSummary(w)
    out['fdpRisk'] = {'cnt': sm['cnt'], 'n': sm['n'], 'top': [[r['pr'], r['d'], r['buffer'], r['risk']] for r in sm['rows'][:8]], 'restShort': [r['pr'] + 'D' + str(r['d']) for r in sm['restShort']]}
    pr = next(p for p in w['pairings'] if p['id'] == 'PR140'); d1 = [l for l in pr['legs'] if l['d'] == pr['legs'][0]['d']]; K = C.legKey
    w['actuals'] = {K(d1[1]): {'dep': d1[1]['dep'] + 240, 'arr': d1[1]['arr'] + 240, 'kind': 'act'}, K(d1[3]): {'dep': d1[3]['dep'] + 120, 'arr': d1[3]['arr'] + 120, 'kind': 'est'}}
    dy = C.fdpDays(pr, w, w['actuals'])[0]; o = C.fdpOptions(w, 'PR140')
    out['fdp'] = {'exceed': dy['exceed'], 'fdp': dy['fdp'], 'limit': dy['limit'], 'restAfter': dy['restAfter'], 'solutions': [solv(x) for x in o['solutions']],
                  'reasons': o['solutions'][-1]['steps'][0]['block']['rules'],
                  'monitor': [[x['pr']['id'], x['day']['buffer'], x['exceed'], len(x['downstream'])] for x in C.dutyMonitor(w, dy['date'])[:5]]}
    return out


if __name__ == '__main__':
    sys.stdout.write(json.dumps(dump(), ensure_ascii=False, indent=1))
