"""命令行：python -m roster <命令> ...

  sample   -o out.json                         生成示例数据（148 任务 / 100 人）
  autofill in.json -o out.json                 一键自动排班
  report   in.json [--csv 目录]               校验报告（可导出 CSV）
  leave    in.json --pilot E10421 --days 9-14 [--apply 方案序号] [-o out.json]   请假调配多方案
  fdp      in.json [--date 27] [--pr PR140] [--leg 航班号=起飞,落地[,act]] [--apply 序号] [-o out.json]   执勤监控与处置方案
"""
import argparse
import os
import sys

from . import (generateSample, autoFill, summarize, leaveOptions, fdpRiskSummary, dutyMonitor, fdpOptions, fdpDays, legKey,
               fmtH, fmtT, DAY, SLOT_NAME, RISK_TXT, apName, io)


def _days(s):
    out = []
    for part in s.replace('，', ',').split(','):
        if '-' in part:
            a, b = part.split('-'); out += list(range(int(a), int(b) + 1))
        elif part.strip(): out.append(int(part))
    return out


def _out(st, path):
    if path:
        io.save(st, path); print(f'已保存：{path}')


def _print_summary(s):
    a = s['all']
    print(f"任务 {s['total']} · 满员率 {s['coverage'] * 100:.1f}% · 硬性 {s['hard']} · 软性 {s['soft']} · 提示 {s['info']}")
    print(f"工时 {a['min']:.1f}–{a['max']:.1f}h，均值 {a['mean']:.1f}h，基尼 {a['gini']:.3f} · 意向休息 {s['prefOK']}/{s['prefT']} · "
          f"休 2–3 天占比 {s['rhythm']['gap23'] * 100:.1f}% · 备份 {s['rhythm']['standbyTotal']} 人次")
    for g, x in s['groups'].items():
        h = x['hours']; print(f"  {g}: {h['n']} 人 {h['min']:.1f}–{h['max']:.1f}h 均 {h['mean']:.1f} 基尼 {h['gini']:.3f}")


def _print_solutions(sols, pm):
    for i, s in enumerate(sols):
        tag = ' ★推荐' if s.get('recommended') else (' 人工处理' if s.get('manual') or s.get('unresolved') else '')
        extra = f" · 超限 {s['fdpAfter']} · 休息问题 {s['restAfterV']}" if s.get('fdpAfter') is not None else ''
        print(f"[{i}] {s['name']}{tag} · 评分 {s['score']}{extra} · 硬性 {s['hard']} · 基尼 {s['giniB']:.4f}→{s['giniA']:.4f}")
        for x in s['steps']:
            if x['type'] == 'split': print(f"     拆分：{x['pairing']} 自 {apName(x['station'])} {fmtT(x['time'])} 起由新机组执行 {x['newPairing']}（{x['legsB']} 段）")
            elif x['type'] == 'manual':
                for r in (x.get('block') or {}).get('rules', []): print(f"     ✖ {r}")
                top = (x.get('block') or {}).get('top') or []
                if top: print(f"     候选人主要不满足：{'，'.join(top)}")
            else:
                fr = pm.get(x.get('from'), {}).get('name', '空缺'); to = pm.get(x.get('to'), {}).get('name', '?')
                line = f"     {x['pairing']} {SLOT_NAME[x['slot']]}位：{fr} → {to}（{ {'standby': '备份', 'rest': '休息人员', 'chain': '链式'}.get(x['type'], x['type']) }）"
                if x.get('chain'): line += f"；↳ {x['chain']['pairing']} {SLOT_NAME[x['chain']['slot']]}位：{pm[x['chain']['from']]['name']} → {pm[x['chain']['to']]['name']}"
                print(line)
        for p in s['people']: print(f"     · {p['name']}({p['rank']}) {p['hb']:.1f}→{p['ha']:.1f}h" + (f" 占意向休息 {p['prefHit']}" if p['prefHit'] else ''))


def main(argv=None):
    ap = argparse.ArgumentParser(prog='python -m roster', description='机组智能排班助手（命令行）')
    sub = ap.add_subparsers(dest='cmd', required=True)
    a = sub.add_parser('sample', help='生成示例数据'); a.add_argument('-o', '--out', default='sample.json'); a.add_argument('--seed', type=int)
    a = sub.add_parser('autofill', help='一键自动排班'); a.add_argument('file'); a.add_argument('-o', '--out')
    a = sub.add_parser('report', help='校验报告'); a.add_argument('file'); a.add_argument('--csv', help='导出 CSV 的目录'); a.add_argument('--all', action='store_true', help='列出全部问题')
    a = sub.add_parser('leave', help='请假调配多方案'); a.add_argument('file'); a.add_argument('--pilot', required=True, help='员工号或姓名'); a.add_argument('--days', required=True, help='如 9-14 或 9,10,12')
    a.add_argument('--apply', type=int); a.add_argument('-o', '--out')
    a = sub.add_parser('fdp', help='执勤监控 / 超执勤处置'); a.add_argument('file'); a.add_argument('--date', type=int); a.add_argument('--pr')
    a.add_argument('--leg', action='append', default=[], help='录入实际/预计时刻：航班号=起飞HH:MM,落地HH:MM[+1][,act]（留空用 - ）')
    a.add_argument('--apply', type=int); a.add_argument('-o', '--out')
    ns = ap.parse_args(argv)

    if ns.cmd == 'sample':
        st = generateSample(ns.seed); _out(st, ns.out); return 0
    st = io.load(ns.file); pm = {p['id']: p for p in st['pilots']}
    if ns.cmd == 'autofill':
        s = autoFill(st, {'onProgress': None}); _print_summary(s); _out(st, ns.out or ns.file); return 0 if s['hard'] == 0 else 1
    if ns.cmd == 'report':
        s = summarize(st); _print_summary(s)
        for t, x in s['byType'].items(): print(f"  [{x['level']}] {t} × {x['n']}")
        vs = [v for v in s['violations'] if ns.all or v['level'] != 'info']
        for v in vs[:200]: print(f"    {v['level']:5s} {v['type']} · {v['msg']}")
        r = fdpRiskSummary(st); c = r['cnt']
        print(f"执勤风险：超限 {c['over']} · 高 {c['high']} · 中 {c['med']} · 低 {c['low']}（共 {r['n']} 个值勤日）")
        for x in [x for x in r['rows'] if x['risk'] != 'low']: print(f"    {x['pr']} D{x['d']} 11/{x['date']:02d} 计划 FDP {fmtH(x['fdp'])} / {fmtH(x['limit'])} 余量 {x['buffer']} 分 · {RISK_TXT[x['risk']]}")
        if ns.csv:
            os.makedirs(ns.csv, exist_ok=True)
            for name, rows in [('排班表_2026-11.csv', io.roster_rows(st)), ('人员工时_2026-11.csv', io.hours_rows(st, s)), ('校验问题_2026-11.csv', io.violation_rows(s)),
                               ('人员数据.csv', io.pilot_rows(st)), ('任务数据.csv', io.pairing_rows(st))]:
                with open(os.path.join(ns.csv, name), 'w', encoding='utf-8', newline='') as f: f.write(io.to_csv(rows))
            print(f'CSV 已导出到 {ns.csv}')
        return 0 if s['hard'] == 0 else 1
    if ns.cmd == 'leave':
        p = pm.get(ns.pilot) or next((x for x in st['pilots'] if x['name'] == ns.pilot), None)
        if not p: print('找不到该人员', file=sys.stderr); return 2
        days = _days(ns.days); r = leaveOptions(st, p['id'], days)
        print(f"{p['name']}({p['rank']}) 请假 {days[0]}–{days[-1]} 日 · 受影响任务 {len(r['affected'])} · 方案 {len(r['solutions'])} · {r['ms']} ms")
        _print_solutions(r['solutions'], pm)
        if ns.apply is not None:
            sol = r['solutions'][ns.apply]
            if not sol.get('state'): print('该方案需人工处理，无法应用', file=sys.stderr); return 2
            _out(sol['state'], ns.out or ns.file)
        return 0
    if ns.cmd == 'fdp':
        acts = st.setdefault('actuals', {})
        for spec in ns.leg:
            flt, _, val = spec.partition('='); parts = [x.strip() for x in val.split(',')]
            kind = 'act' if len(parts) > 2 and parts[2] == 'act' else 'est'
            for pr in st['pairings']:
                for l in pr['legs']:
                    if l['flt'] != flt or (ns.date and l['dep'] // DAY + 1 != ns.date) or (ns.pr and pr['id'] != ns.pr): continue
                    base = (l['dep'] // DAY) * DAY; a = acts.setdefault(legKey(l), {'kind': kind}); a['kind'] = kind

                    def pt(s):
                        hh, mm = s.split('+')[0].split(':'); return base + int(s.split('+')[1] if '+' in s else 0) * DAY + int(hh) * 60 + int(mm)
                    if parts[0] and parts[0] != '-': a['dep'] = pt(parts[0])
                    if len(parts) > 1 and parts[1] and parts[1] != '-': a['arr'] = pt(parts[1])
        date = ns.date or (fdpRiskSummary(st)['rows'][0]['date'])
        mon = dutyMonitor(st, date)
        print(f"11/{date:02d} 执行任务 {len(mon)} 个 · 预计超限 {sum(1 for x in mon if x['exceed'])}")
        for x in mon[:10]:
            dy = x['day']
            st_ = f"超 {dy['exceed']} 分钟" if dy['exceed'] else f"剩余余量 {dy['buffer']} 分钟"
            print(f"  {x['pr']['id']} D{dy['d']} 已落地 {dy['nLanded']}/{len(dy['legs'])} · 预计 FDP {fmtH(dy['fdp'])} / {fmtH(dy['limit'])} · {st_}" +
                  (f" · ⓘ 若不追回将超 {dy['cascExceed']} 分钟" if dy['cascExceed'] else ''))
            for d in x['downstream']:
                print('     ↳ ' + (f"D{d['d']} 过夜休息 {fmtH(d['restAfter'])}（差 {d['short']} 分钟）" if d.get('overnight') else f"{pm[d['pilot']]['name']} 下一任务 {d['next']} 前休息 {fmtH(d['gap'])}"))
        target = ns.pr or next((x['pr']['id'] for x in mon if x['exceed'] or x['downstream']), None)
        if target:
            o = fdpOptions(st, target); print(f"\n{target} 处置方案（{o['ms']} ms）：")
            _print_solutions(o['solutions'], pm)
            if ns.apply is not None:
                sol = o['solutions'][ns.apply]
                if not sol.get('state'): print('该方案需人工处理，无法应用', file=sys.stderr); return 2
                _out(sol['state'], ns.out or ns.file)
        elif ns.out: _out(st, ns.out)
        return 0


if __name__ == '__main__':
    sys.exit(main())
