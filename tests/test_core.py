"""与网页版 test/test.js 一一对应的断言。"""
import json
import time

import roster as C
from roster.jsutil import jsorted


def test_sample_shape():
    st = C.generateSample()
    assert len(st['pilots']) == 100 and len(st['pairings']) == 148
    assert round(sum(C.pairingHours(p) for p in st['pairings'])) == 1895


def test_autofill_quality(summ):
    s = summ
    assert s['coverage'] == 1.0 and s['hard'] == 0 and s['soft'] == 0
    assert all(x['hours'] <= 90 for x in s['per']), 'over 90h'
    assert s['all']['gini'] < 0.05
    assert s['prefOK'] == s['prefT'] == 200
    assert s['rhythm']['standbyTotal'] == 30


def test_apply_leave(st):
    idx = C.buildIndex(st)
    cap = jsorted([p for p in st['pilots'] if p['rank'] == 'J3'], lambda a, b: len(idx['sched'][b['id']]) - len(idx['sched'][a['id']]))[0]
    days = []
    for pr in idx['sched'][cap['id']][1:3]:
        for d in C.daysTouched(pr, st):
            if d not in days: days.append(d)
    r = C.applyLeave(st, cap['id'], days)
    assert len(r['affected']) == 2 and not r['unresolved']
    assert C.summarize(st)['hard'] == 0


def test_bp_tester_migration():
    S = C.defaultSettings(); S['testerAirports'] = ['ZUUU']; C.migrateSettings(S)
    assert 'testerAirports' not in S and S['bpTesterAirports'] == ['ZUUU']


def test_standby_cap(st):
    per = [len(v) for v in st['standby'].values()]
    assert max(per) <= st['settings']['maxStandbyPerPilot'] and sum(per) == 30
    assert C.summarize(st)['hard'] == 0


def test_leave_options_groups(st):
    ix = C.buildIndex(st)
    for lab, pred in [('机长', lambda p: p['rank'] == 'J3'), ('副驾驶', lambda p: C.isFO(p['rank'])), ('新机长', lambda p: C.isNew(p['rank'])), ('教员', lambda p: C.isInstr(p['rank']))]:
        p = jsorted([x for x in st['pilots'] if pred(x)], lambda a, b: len(ix['sched'][b['id']]) - len(ix['sched'][a['id']]))[0]
        a, b = ix['sched'][p['id']][1], ix['sched'][p['id']][2]
        days = list(range(a['start'], b['start'] + b['ndays']))
        t = time.time(); r = C.leaveOptions(st, p['id'], days); el = time.time() - t
        rec = next((s for s in r['solutions'] if s.get('recommended')), None)
        assert rec, lab
        assert el < 20, f'{lab} {el:.1f}s'
        assert rec['hard'] == 0 and all(not x['overHard'] for x in rec['people'])
        assert all(s['unresolved'] or s['hard'] == 0 for s in r['solutions'])
        assert not any(x['type'] == 'seat' for s in r['solutions'] for x in s['steps'])
        assert not any(p['id'] in pr['crew'].values() and any(d in days for d in C.daysTouched(pr, rec['state'])) for pr in rec['state']['pairings'])
        assert C.summarize(rec['state'])['hard'] == 0
    assert C.summarize(st)['hard'] == 0  # 原状态不变


def test_fallback_manual(st):
    st['settings']['hardMaxHours'] = 40
    lh = next((pr for pr in st['pairings'] if any(l['to'] == 'ZULS' for l in pr['legs'])), st['pairings'][0])
    r = C.leaveOptions(st, lh['crew']['C'], C.daysTouched(lh, st))
    assert all(s['unresolved'] > 0 and s.get('manual') for s in r['solutions'])
    blk = next(x for x in r['solutions'][0]['steps'] if x.get('block'))
    assert any('拉萨' in x for x in blk['block']['rules'])


def test_maohua_90h(st):
    p = next(x for x in st['pilots'] if x['name'] == '毛华' and x['rank'] == 'J3')
    r = C.leaveOptions(st, p['id'], [9, 10, 11, 12, 13, 14])
    ok = [s for s in r['solutions'] if not s['unresolved'] and s['hard'] == 0]
    assert ok and max(y['ha'] for s in ok for y in s['people']) <= 90


def test_hours_no_target_warnings(st):
    v = C.summarize(st)
    assert not any('目标' in k for k in v['byType'])
    st['settings']['hardMaxHours'] = 60
    v2 = C.summarize(st)
    assert v2['byType']['月小时超法规上限']['level'] == 'hard'


# ===== 执勤监控（FDP） =====
def test_fdp_planned_risk(st):
    sm = C.fdpRiskSummary(st)
    assert sm['cnt'] == {'over': 0, 'high': 1, 'med': 6, 'low': 446}
    assert C.fdpLimit(st, 9 * 60, 4) == 840 and C.fdpLimit(st, 2 * 60, 7) == 540 and C.fdpLimit(st, 13 * 60, 5) == 720
    assert 'minHours' not in st['settings'] and 'maxHours' not in st['settings']


def _pr140(st):
    pr = next(p for p in st['pairings'] if p['id'] == 'PR140')
    return pr, [l for l in pr['legs'] if l['d'] == pr['legs'][0]['d']]


def test_fdp_rolling(st):
    pr, d1 = _pr140(st); K = C.legKey
    st['actuals'] = {K(d1[1]): {'dep': d1[1]['dep'] + 240, 'arr': d1[1]['arr'] + 240, 'kind': 'est'}}
    dy = C.fdpDays(pr, st, st['actuals'])[0]
    assert dy['exceed'] == 0 and dy['legs'][2]['dep'] == d1[2]['dep'] and dy['cascExceed'] == 20  # 不级联，仅提示
    assert not next(x for x in C.dutyMonitor(st, dy['date']) if x['pr']['id'] == 'PR140')['exceed']
    st['actuals'][K(d1[1])] = {'dep': d1[1]['dep'] + 30, 'arr': d1[1]['arr'] + 10, 'kind': 'act'}
    dy = C.fdpDays(pr, st, st['actuals'])[0]
    assert dy['exceed'] == 0 and dy['cascExceed'] == 0 and dy['nLanded'] == 1
    st['actuals'][K(d1[1])] = {'dep': d1[1]['dep'] + 240, 'arr': d1[1]['arr'] + 240, 'kind': 'act'}
    st['actuals'][K(d1[3])] = {'dep': d1[3]['dep'] + 120, 'arr': d1[3]['arr'] + 120, 'kind': 'est'}
    dy = C.fdpDays(pr, st, st['actuals'])[0]
    assert dy['exceed'] == 20 and dy['exLeg']['i'] == 3 and C.fmtH(dy['restAfter']) == '9h25'
    w0 = json.loads(json.dumps(st)); w0['actuals'][K(d1[3])] = {'arr': dy['date'] * 1440 + 30, 'kind': 'est'}
    dz = C.fdpDays(pr, w0, w0['actuals'])[0]
    assert dz['exceed'] == 105 and dz['end'] == dy['date'] * 1440 + 30
    mon = C.dutyMonitor(st, dy['date'])
    assert mon[0]['pr']['id'] == 'PR140' and mon[0]['exceed'] and any(x.get('overnight') for x in mon[0]['downstream'])


def test_migrate_delays(st):
    pr, d1 = _pr140(st)
    wm = {'pairings': st['pairings'], 'delays': {C.legKey(d1[1]): 240}}; C.migrateDelays(wm)
    assert 'delays' not in wm and wm['actuals'][C.legKey(d1[1])]['dep'] == d1[1]['dep'] + 240 and len(wm['actuals']) == 1


def test_fdp_options(st):
    pr, d1 = _pr140(st); K = C.legKey
    st['actuals'] = {K(d1[1]): {'dep': d1[1]['dep'] + 240, 'arr': d1[1]['arr'] + 240, 'kind': 'act'},
                     K(d1[3]): {'dep': d1[3]['dep'] + 120, 'arr': d1[3]['arr'] + 120, 'kind': 'est'}}
    o = C.fdpOptions(st, 'PR140')
    rec = next(s for s in o['solutions'] if s.get('recommended'))
    assert 3 <= len(o['solutions']) <= 6
    assert rec['fdpAfter'] == 0 and rec['hard'] == 0 and any(x['type'] == 'split' for x in rec['steps'])
    assert any(s['key'] == 'manual' and not s['state'] and s['steps'][0]['block']['rules'] for s in o['solutions'])
    nb = next(p for p in rec['state']['pairings'] if p['id'] == 'PR140-B')
    assert nb['freshAt'] and all(nb['crew'].values()) and C.summarize(rec['state'])['hard'] == 0
    w = json.loads(json.dumps(st)); p2 = next(p for p in w['pairings'] if p['id'] == 'PR140')
    j = next(i for i, l in enumerate(p2['legs']) if l['d'] == p2['legs'][0]['d'] and l['from'] == 'ZUUU' and l['dep'] > p2['legs'][0]['dep'])
    C.splitPairing(w, p2, j)
    assert all(not x['exceed'] for x in C.fdpDays(p2, w, w['actuals']))


def test_undo_history(st):
    h = C.History(); before = json.dumps(st, ensure_ascii=False)
    p = next(x for x in st['pilots'] if x['name'] == '毛华')
    r = C.leaveOptions(st, p['id'], [9, 10])
    rec = next(s for s in r['solutions'] if s.get('recommended'))
    st2 = C.apply_solution(st, rec, h, '毛华请假')
    assert len(h) == 1 and st2 != st
    back, lab = h.undo()
    assert lab == '毛华请假' and json.dumps(back, ensure_ascii=False) == before
