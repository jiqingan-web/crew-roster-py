"""JSON 备份导入/导出（与网页版「恢复备份 JSON / 导出 JSON」互通）与 CSV 导入导出（UTF-8 BOM，Excel 可直接打开）。"""
import csv
import io as _io
import json
import re

from .rules import (DAY, SLOTS, AIRPORTS, RANK_VAL, RANKS, defaultSettings, migrateSettings, fmtT, apName, isSpecial)
from .fdp import migrateDelays

PIL_H = ['员工号', '姓名', '级别', '授权机场(;分隔)', '意向休息日(;分隔)', '请假日(;分隔)']
PR_H = ['任务号', '日序(D)', '航班号', '起飞机场', '落地机场', '日期(11月几日)', '起飞时间', '落地时间(次日加+1)', '机型']


def normalize(st):
    """导入后补全设置并迁移旧字段（与网页版加载逻辑一致）"""
    if not isinstance(st, dict) or not st.get('pilots') or not st.get('pairings'):
        raise ValueError('不是有效备份（缺少 pilots / pairings）')
    S = defaultSettings(); S.update(st.get('settings') or {}); st['settings'] = migrateSettings(S)
    migrateDelays(st)
    for p in st['pairings']:
        p.setdefault('crew', {'C': None, 'F': None, 'T': None})
        for s in SLOTS: p['crew'].setdefault(s, None)
    for p in st['pilots']:
        for k in ('auth', 'prefs', 'leave'): p.setdefault(k, [])
    return st


def loads(text):
    return normalize(json.loads(text.lstrip('\ufeff')))


def load(path):
    with open(path, encoding='utf-8') as f: return loads(f.read())


def dumps(st):
    """紧凑 JSON（与网页 JSON.stringify(st) 相同结构，可直接在网页「恢复备份 JSON」导入）"""
    return json.dumps(st, ensure_ascii=False, separators=(',', ':'))


def save(st, path):
    with open(path, 'w', encoding='utf-8') as f: f.write(dumps(st))


# ---------- CSV ----------
def to_csv(rows):
    def cell(x):
        x = '' if x is None else str(x)
        return '"' + x.replace('"', '""') + '"' if re.search(r'[",\n]', x) else x
    return '\ufeff' + '\r\n'.join(','.join(cell(x) for x in r) for r in rows)


def parse_csv(t):
    t = t.lstrip('\ufeff')
    return [r for r in csv.reader(_io.StringIO(t)) if any(c.strip() for c in r)]


def _tm(m, base):
    dd = m // DAY - base
    return fmtT(m) + (f'+{dd}' if dd > 0 else '')


def roster_rows(st):
    pm = {p['id']: p for p in st['pilots']}
    rows = [['任务号', '日序', '日期', '航班号', '起飞', '落地', '起飞时间', '落地时间', '机型', '特殊机场', '需血压测试仪', '机长(机)', '级别', '副驾驶(副)', '级别', '第三人(三)', '级别']]
    bpa = st['settings'].get('bpTesterAirports') or []
    for pr in st['pairings']:
        for l in pr['legs']:
            day = l['dep'] // DAY; r = [pr['id'], 'D' + str(l['d']), f"2026-11-{day + 1:02d}", l['flt'], f"{l['from']} {apName(l['from'], st)}", f"{l['to']} {apName(l['to'], st)}",
                                       fmtT(l['dep']), _tm(l['arr'], day), l.get('ac'), ';'.join(apName(x, st) for x in (l['from'], l['to']) if isSpecial(x, st)), '是' if l['from'] in bpa else '']
            for s in SLOTS:
                c = pr['crew'].get(s) and pm.get(pr['crew'][s])
                r += [f"{c['name']}({c['id']})", c['rank']] if c else ['空缺', '']
            rows.append(r)
    return rows


def hours_rows(st, summary):
    rows = [['员工号', '姓名', '级别', '组别', '本月飞行小时', '任务数', '执勤天数', '过夜次数', '特殊机场任务', '夜航段', '意向休息日满足', '备份天数', '备份日期', '任务间休息天数']]
    sb = st.get('standby') or {}
    for x in summary['per']:
        rows.append([x['id'], x['name'], x['rank'], x['group'], f"{x['hours']:.2f}", x['pairings'], x['dutyDays'], x['overnights'], x['special'], x['night'],
                     f"{x['prefOK']}/{x['prefTotal']}", x['standby'], ';'.join(map(str, sb.get(x['id']) or [])), ';'.join(map(str, x['gaps']))])
    return rows


def violation_rows(summary):
    return [['级别', '类型', '任务', '说明']] + [[v['level'], v['type'], v.get('pairing') or '', v['msg']] for v in summary['violations']]


def pilot_rows(st):
    return [PIL_H] + [[p['id'], p['name'], p['rank'], ';'.join(p.get('auth') or []), ';'.join(map(str, p.get('prefs') or [])), ';'.join(map(str, p.get('leave') or []))] for p in st['pilots']]


def pairing_rows(st):
    rows = [PR_H]
    for pr in st['pairings']:
        for l in pr['legs']:
            day = l['dep'] // DAY
            rows.append([pr['id'], l['d'], l['flt'], l['from'], l['to'], day + 1, fmtT(l['dep']), _tm(l['arr'], day), l.get('ac')])
    return rows


def import_pilots(st, text):
    rows = parse_csv(text)[1:]; ps = []

    def ls(x): return [v for v in re.split(r'[;；\s]+', x or '') if v]
    for i, r in enumerate(rows):
        r = r + [''] * (6 - len(r))
        if r[2].strip() not in RANK_VAL: raise ValueError(f'第{i + 2}行级别无效：{r[2]}')
        ps.append({'id': r[0].strip(), 'name': r[1].strip(), 'rank': r[2].strip(), 'auth': ls(r[3]), 'prefs': [int(x) for x in ls(r[4])], 'leave': [int(x) for x in ls(r[5])]})
    st['pilots'] = ps; st['sample'] = False; st['standby'] = None
    for p in st['pairings']: p['crew'] = {'C': None, 'F': None, 'T': None}
    return len(ps)


def import_pairings(st, text):
    rows = parse_csv(text)[1:]; g = {}
    for i, r in enumerate(rows):
        r = [x.strip() for x in r] + [''] * (9 - len(r))
        pid, d, flt, fr, to, day, dep, arr, ac = r[:9]
        if fr not in AIRPORTS and fr not in (st.get('airports') or {}): raise ValueError(f'第{i + 2}行机场未知：{fr}')

        def pt(s):
            m = re.match(r'^(\d{1,2}):(\d{2})(?:\+(\d))?$', s)
            if not m: raise ValueError(f'第{i + 2}行时间格式错误：{s}')
            return int(m.group(3) or 0) * DAY + int(m.group(1)) * 60 + int(m.group(2))
        base = (int(day) - 1) * DAY
        g.setdefault(pid, []).append({'d': int(re.sub(r'\D', '', d)), 'flt': flt, 'from': fr, 'to': to, 'dep': base + pt(dep), 'arr': base + pt(arr), 'ac': ac or 'A320'})
    prs = []
    for pid, legs in g.items():
        legs.sort(key=lambda l: l['dep']); start = legs[0]['dep'] // DAY + 1
        nd = max(legs[-1]['arr'] // DAY + 1 - start, *[l['d'] for l in legs])
        prs.append({'id': pid, 'start': start, 'ndays': nd, 'ac': 'A321' if any(l['ac'] == 'A321' for l in legs) else 'A320', 'legs': legs, 'crew': {'C': None, 'F': None, 'T': None}})
    prs.sort(key=lambda p: p['legs'][0]['dep'])
    st['pairings'] = prs; st['sample'] = False
    return len(prs)
