"""机组智能排班助手 · Streamlit 界面（中文）。运行：streamlit run app.py"""
import datetime as dt
import json
import os
import re
import time

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import roster as C
from roster import io as rio

st.set_page_config(page_title='机组智能排班助手', page_icon='✈', layout='wide')
STATE_FILE = os.environ.get('ROSTER_STATE', os.path.join(os.path.expanduser('~'), '.roster_py', 'state.json'))
T0 = dt.datetime(C.YEAR, C.MONTH, 1)
WK = '一二三四五六日'
SLOT_TXT = {'C': '机长(机)', 'F': '副驾驶(副)', 'T': '第三人(三)'}
RISK_COLOR = {'over': '#ff1f3d', 'high': '#ff5a6a', 'med': '#ffb020', 'low': '#2ecc8f'}
RISK_ICON = {'over': '⛔', 'high': '⚠', 'med': '◔', 'low': ''}
TYPE_TXT = {'standby': '调用备份', 'rest': '休息人员', 'chain': '链式调换', 'manual': '人工处理', 'split': '拆分换组'}
GROUP_COLOR = {'教员': '#a970ff', '机长': '#3ea6ff', '新机长': '#00c2c7', '副驾驶': '#2ecc8f'}
VIEWS = ['人员视图', '任务视图', '校验报告', '手工调整', '请假调配', '执勤监控', '员工福利', '设置', '导入导出']

st.markdown("""<style>
.block-container{padding-top:3.2rem;padding-bottom:2rem}
.tag{display:inline-block;padding:1px 7px;border-radius:9px;font-size:12px;margin-right:4px}
.t-rec{background:#1f7a4d;color:#fff}.t-man{background:#7a1f2b;color:#fff}.t-sb{background:#5a4a00;color:#ffd75e}
.okc{color:#2ecc8f}.warnc{color:#ffb020}.red{color:#ff5a6a}.mut{color:#8aa0b8}
.small{font-size:12.5px;line-height:1.55}
.kpis{display:flex;gap:10px;margin-bottom:10px;flex-wrap:wrap}.kpi{background:rgba(62,166,255,.08);border:1px solid rgba(62,166,255,.25);border-radius:10px;padding:6px 14px;min-width:120px}
.kl{font-size:12px;color:#8aa0b8}.kv{font-size:20px;font-weight:700}.kpi.vt{margin-left:auto;font-size:18px;font-weight:700;border:none;background:none;align-self:center}
</style>""", unsafe_allow_html=True)


# ---------------- 状态 ----------------
def save():
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, 'w', encoding='utf-8') as f: f.write(rio.dumps(S()))
    st.session_state.summary = None


def S():
    return st.session_state.roster


def summ():
    if st.session_state.get('summary') is None: st.session_state.summary = C.summarize(S())
    return st.session_state.summary


def init():
    if 'roster' in st.session_state: return
    data = None
    if os.path.exists(STATE_FILE):
        try: data = rio.load(STATE_FILE)
        except Exception: data = None
    st.session_state.roster = data or rio.normalize(C.generateSample())
    st.session_state.hist = C.History()
    st.session_state.summary = None
    st.session_state.hl = None
    for k in ('leave_opts', 'duty_opts'): st.session_state[k] = None


def set_state(new, msg=None):
    st.session_state.roster = new; save()
    if msg: st.toast(msg)


def H(t):
    """把 **粗体** / ~~删除线~~ 转为 HTML（HTML 块内 Markdown 不生效）"""
    return re.sub(r'~~(.+?)~~', r'<s>\1</s>', re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', t))


def mdt(m): return T0 + dt.timedelta(minutes=float(m))
def dmin(d): return (d - T0).total_seconds() / 60
def date_txt(d): return f"11/{d:02d} 周{WK[(T0 + dt.timedelta(days=d - 1)).weekday()]}"


init()
pm = {p['id']: p for p in S()['pilots']}


def nm(i): return pm[i]['name'] if i and i in pm else '空缺'


# ---------------- 侧栏 ----------------
if st.session_state.get('_goto'):
    st.session_state.view = st.session_state.pop('_goto')
with st.sidebar:
    st.markdown('### ✈ 机组智能排班助手')
    st.caption(f"A320 机队 · 成都基地 · 2026年11月{' · 示例数据' if S().get('sample') else ''}")
    view = st.radio('视图', VIEWS, label_visibility='collapsed', key='view')
    st.divider()
    if st.button('⚡ 一键自动排班', type='primary', use_container_width=True):
        bar = st.progress(0.0, '正在排班…'); t = time.time()
        s = C.autoFill(S(), {'onProgress': lambda x: bar.progress(min(1.0, x), f'正在排班… {x * 100:.0f}%')})
        bar.empty(); save(); st.session_state.hl = None
        st.toast(f"自动填人完成（{time.time() - t:.1f} s）：满员 {s['full']}/{s['total']}，硬性违规 {s['hard']}，工时 {s['all']['min']:.1f}–{s['all']['max']:.1f}h")
    c1, c2 = st.columns(2)
    if c1.button('清空排班', use_container_width=True):
        for p in S()['pairings']: p['crew'] = {'C': None, 'F': None, 'T': None}
        S()['standby'] = None; save(); st.toast('已清空排班')
    if c2.button('重置示例', use_container_width=True):
        st.session_state.roster = rio.normalize(C.generateSample()); st.session_state.hist = C.History(); st.session_state.hl = None
        st.session_state.leave_opts = st.session_state.duty_opts = None; save(); st.toast('已重置示例数据')
    h = st.session_state.hist
    if len(h):
        if st.button(f'↶ 撤销（{len(h)}）：{h.items[-1]["label"][:18]}', use_container_width=True):
            back, lab = h.undo(); st.session_state.hl = None; set_state(rio.normalize(back), '已撤销：' + lab)
    st.caption(f'数据自动保存在 {STATE_FILE}')

pm = {p['id']: p for p in S()['pilots']}
sm = summ()
_k = [('任务', sm['total'], ''), ('满员率', f"{sm['coverage'] * 100:.1f}%", 'okc' if sm['coverage'] == 1 else 'warnc'), ('硬性违规', sm['hard'], 'okc' if sm['hard'] == 0 else 'red'),
      ('工时区间', f"{sm['all']['min']:.1f}–{sm['all']['max']:.1f}h" if sm['all']['n'] else '—', ''), ('基尼系数', f"{sm['all']['gini']:.3f}", ''), ('意向休息满足', f"{sm['prefRate'] * 100:.1f}%", 'okc')]
st.markdown("<div class='kpis'>" + ''.join(f"<div class='kpi'><div class='kl'>{a}</div><div class='kv {c}'>{b}</div></div>" for a, b, c in _k) + f"<div class='kpi vt'>{view}</div></div>", unsafe_allow_html=True)


# ---------------- 通用：甘特 ----------------
def gantt(pilots, days=(1, C.DAYS), height_per=24, hl=None, acts=None, title=None):
    st_ = S(); idx = C.buildIndex(st_); sb = st_.get('standby') or {}
    hl = hl or {}; hlP = set(hl.get('pairings', [])); hlPeople = set(hl.get('people', []))
    fig = go.Figure(); ys = [f"{p['name']} {p['rank']} · {idx['hours'][p['id']]:.0f}h" for p in pilots]
    ymap = {p['id']: y for p, y in zip(pilots, ys)}

    def bars(xs, base, y, color, text, hover, line=None, opacity=1.0, pattern=None):
        if not xs: return
        fig.add_trace(go.Bar(x=xs, base=base, y=y, orientation='h', marker=dict(color=color, line=line or dict(width=0), pattern=pattern), opacity=opacity,
                             text=text, textposition='inside', insidetextanchor='middle', hovertext=hover, hoverinfo='text', showlegend=False, width=0.72,
                             textfont=dict(size=10, color='white')))
    # 请假 / 意向休息 / 备份
    for kind, color, key in (('请假', '#59616e', 'leave'), ('意向休息', '#7a5cff', 'prefs')):
        xs, base, y, tx = [], [], [], []
        for p in pilots:
            for d in (p.get(key) or []):
                if days[0] <= d <= days[1]: xs.append(86400000); base.append(mdt((d - 1) * C.DAY)); y.append(ymap[p['id']]); tx.append(f"{p['name']} {d}日 {kind}")
        bars(xs, base, y, color, ['假' if key == 'leave' else '休'] * len(xs), tx, opacity=0.45, pattern=dict(shape='/' if key == 'leave' else '.'))
    xs, base, y, tx = [], [], [], []
    for p in pilots:
        for d in (sb.get(p['id']) or []):
            if days[0] <= d <= days[1]: xs.append(86400000); base.append(mdt((d - 1) * C.DAY)); y.append(ymap[p['id']]); tx.append(f"{p['name']} {d}日 备份（Standby）")
    bars(xs, base, y, '#d4a017', ['备'] * len(xs), tx, opacity=0.6)
    # 任务
    rows = {}
    for p in pilots:
        for pr in idx['sched'][p['id']]:
            a, b = C.report(pr, st_), C.release(pr, st_)
            if b < (days[0] - 1) * C.DAY or a > days[1] * C.DAY: continue
            rk = C.pairingRisk(pr, st_, acts if acts else None)['risk']
            slot = next(s for s in C.SLOTS if pr['crew'][s] == p['id'])
            color = GROUP_COLOR[C.rankGroup(p['rank'])]
            hit = pr['id'] in hlP or (pr.get('splitFrom') in hlP if pr.get('splitFrom') else False)
            line = dict(color='#ffffff', width=2.5) if hit else (dict(color=RISK_COLOR[rk], width=2) if rk in ('over', 'high', 'med') else dict(width=0))
            route = '-'.join([C.apName(pr['legs'][0]['from'], st_)] + [C.apName(l['to'], st_) for l in pr['legs']])
            r = rows.setdefault(id(line) if hit or rk != 'low' else color, {'x': [], 'b': [], 'y': [], 't': [], 'h': [], 'c': color, 'line': line})
            r['x'].append((b - a) * 60000); r['b'].append(mdt(a)); r['y'].append(ymap[p['id']])
            r['t'].append(f"{RISK_ICON[rk]}{pr['id']}"); r['h'].append(f"{pr['id']} · {C.SLOT_NAME[slot]}位 · {C.pairingHours(pr):.1f}h · {pr['ndays']} 天<br>{route}<br>报到 {C.fmtT(a)} · 释放 {C.fmtT(b)}<br>执勤风险：{C.RISK_TXT[rk]}")
    for r in rows.values(): bars(r['x'], r['b'], r['y'], r['c'], r['t'], r['h'], line=r['line'])
    for p in pilots:
        if p['id'] in hlPeople:
            fig.add_hrect(y0=ys.index(ymap[p['id']]) - 0.5, y1=ys.index(ymap[p['id']]) + 0.5, fillcolor='rgba(255,255,255,0.07)', line_width=0)
    fig.update_layout(barmode='overlay', height=max(260, 70 + height_per * len(pilots)), margin=dict(l=10, r=10, t=60, b=10), title=title,
                      xaxis=dict(type='date', range=[mdt((days[0] - 1) * C.DAY), mdt(days[1] * C.DAY)], dtick=86400000, tickformat='%d<br>%a', side='top', gridcolor='rgba(128,128,128,0.25)',
                                 rangeslider=dict(visible=False)),
                      yaxis=dict(categoryorder='array', categoryarray=list(reversed(ys)), autorange=True, tickfont=dict(size=11)),
                      dragmode='pan', hoverlabel=dict(font_size=12), plot_bgcolor='rgba(0,0,0,0)')
    return fig


def show_gantt(fig, key):
    st.plotly_chart(fig, use_container_width=True, key=key, config={'scrollZoom': True, 'displaylogo': False, 'modeBarButtonsToAdd': ['zoomIn2d', 'zoomOut2d', 'resetScale2d']})


# ---------------- 通用：方案卡片 ----------------
def step_lines(sol):
    out = []
    for x in sol['steps']:
        if x['type'] == 'split':
            out.append(f"**{x['pairing']}** <span class='tag t-sb'>拆分</span> 原机组飞至 {C.apName(x['station'])} 下机；自 {C.fmtT(x['time'])} 起由新机组执行 **{x['newPairing']}**（{x['legsB']} 段）" if not x['whole']
                       else f"**{x['pairing']}** 整组更换机组")
        elif x['type'] == 'manual':
            b = x.get('block') or {}
            out.append(f"**{x['pairing']}** <span class='tag t-man'>人工处理</span>" + ''.join(f"<br><span class='red'>✖ {r}</span>" for r in b.get('rules', [])) +
                       (f"<br><span class='mut'>候选人主要不满足：{'，'.join(b['top'])}</span>" if b.get('top') else ''))
        else:
            s = f"**{x['pairing']}** {C.SLOT_NAME[x['slot']]}位：~~{nm(x.get('from'))}~~ → **{nm(x['to'])}** <span class='tag t-sb'>{TYPE_TXT.get(x['type'], x['type'])}</span>"
            if x.get('why'): s += f" <span class='mut'>（{x['why']}）</span>"
            if x.get('prefWarn'): s += f" <span class='warnc'>⚠ {x['prefWarn']}</span>"
            if x.get('chain'):
                c = x['chain']; s += f"<br>&nbsp;&nbsp;↳ **{c['pairing']}** {C.SLOT_NAME[c['slot']]}位：~~{nm(c['from'])}~~ → **{nm(c['to'])}**" + (' （备份）' if c['fromStandby'] else '')
            out.append(s)
    return out


def sol_card(sol, i, prefix, label_fn, on_apply=None):
    with st.container(border=True):
        tags = ("<span class='tag t-rec'>推荐</span>" if sol.get('recommended') else '') + ("<span class='tag t-man'>人工处理</span>" if sol.get('manual') or sol.get('unresolved') else '')
        st.markdown(f"**方案 {chr(65 + i)} · {sol['name']}** {tags}<br><span class='mut small'>{sol.get('desc', '')} · 评分 {sol['score']}</span>", unsafe_allow_html=True)
        st.markdown("<div class='small'>" + H('<br>'.join(step_lines(sol))) + '</div>', unsafe_allow_html=True)
        hc = C.hardCap(S()) if sol.get('state') else 90
        lines = []
        if sol['people']:
            lines.append('**工时变化**：' + '；'.join(f"{p['name']} {p['hb']:.1f}→<span class='{'red' if p['overHard'] else 'okc'}'>{p['ha']:.1f}h</span>" for p in sol['people']))
        lines.append(f"**公平（基尼）**：{sol['giniB']:.4f}→{sol['giniA']:.4f}（{sol['giniD']:+.4f}）")
        if sol.get('state'):
            pf = sum(len(p['prefHit']) for p in sol['people']); rh = sol.get('rhy', 0)
            lines.append(f"**意向休息 / 节奏**：{'<span class=warnc>占意向休息 ' + str(pf) + ' 天</span>' if pf else '<span class=okc>不占意向休息</span>'} · 节奏扰动 {'+' + str(rh) if rh else '无'}")
            if sol.get('sbLeft'): lines.append('**当日剩余备份**：' + ' '.join(f"{x['d']}日:{x['n']}" for x in sol['sbLeft']))
        if sol.get('fdpAfter') is not None:
            lines.append(f"**执勤 / 休息**：{'<span class=red>✖ 仍有 ' + str(sol['fdpAfter']) + ' 个值勤日超限</span>' if sol['fdpAfter'] else '<span class=okc>✔ 预计 FDP 不超限</span>'} · "
                         f"{'<span class=warnc>休息问题 ' + str(sol['restAfterV']) + ' 项</span>' if sol.get('restAfterV') else '<span class=okc>休息满足</span>'}")
        if sol.get('state'):
            lines.append(f"**合规检查**：{'<span class=okc>✔ 座位搭配 ✔ 特殊机场 ✔ 休息/工时（≤' + str(hc) + 'h）· 硬性违规 0</span>' if sol['hard'] == 0 else '<span class=red>硬性违规 ' + str(sol['hard']) + '</span>'}")
            if sol.get('bp'): lines.append(f"<span class='warnc'>血压测试仪：{'、'.join(dict.fromkeys(sol['bp']))} 始发站须配备</span>")
        st.markdown("<div class='small'>" + H('<br>'.join(lines)) + '</div>', unsafe_allow_html=True)
        if st.button('一键应用' if sol.get('state') else '需运控人工处理', key=f'{prefix}_apply_{i}', disabled=not sol.get('state'), type='primary' if sol.get('recommended') else 'secondary'):
            new = C.apply_solution(S(), sol, st.session_state.hist, label_fn(sol))
            ids = set()
            for x in sol['steps']:
                for kk in ('from', 'to'):
                    if x.get(kk): ids.add(x[kk])
                if x.get('chain'): ids.update([x['chain']['from'], x['chain']['to']])
            st.session_state.hl = {'people': list(ids), 'pairings': [x['pairing'] for x in sol['steps']] + [x['chain']['pairing'] for x in sol['steps'] if x.get('chain')] + [x['newPairing'] for x in sol['steps'] if x.get('newPairing')]}
            if on_apply: on_apply()
            set_state(rio.normalize(new), '已应用：' + label_fn(sol))
            st.session_state._goto = '人员视图'
            st.rerun()


def preview(sols, prefix, days):
    if not sols: return
    names = [f"方案 {chr(65 + i)} · {s['name']}" for i, s in enumerate(sols)]
    i = st.selectbox('影响预览（白框 = 新增/调整的任务，浅色行 = 涉及人员）', range(len(sols)), format_func=lambda j: names[j], key=f'{prefix}_pv',
                     index=next((j for j, s in enumerate(sols) if s.get('recommended')), 0))
    sol = sols[i]
    if not sol.get('state'): st.info('该方案为人工处理，无排班变更。'); return
    ids = []
    for x in sol['steps']:
        for kk in ('from', 'to'):
            if x.get(kk) and x[kk] not in ids: ids.append(x[kk])
        if x.get('chain'):
            for kk in ('from', 'to'):
                if x['chain'][kk] not in ids: ids.append(x['chain'][kk])
    hl = {'people': ids, 'pairings': [x['pairing'] for x in sol['steps']] + [x.get('newPairing') for x in sol['steps'] if x.get('newPairing')] + [x['chain']['pairing'] for x in sol['steps'] if x.get('chain')]}
    cur = st.session_state.roster; st.session_state.roster = sol['state']
    try:
        ps = [p for p in sol['state']['pilots'] if p['id'] in ids]
        d0, d1 = max(1, min(days) - 3), min(C.DAYS, max(days) + 3)
        show_gantt(gantt(ps, (d0, d1), 30, hl, acts=cur.get('actuals')), f'{prefix}_mg_{i}')
    finally:
        st.session_state.roster = cur


# ---------------- 视图 ----------------
def v_people():
    st_ = S(); hl = st.session_state.hl
    c1, c2, c3, c4 = st.columns([2, 2, 2, 3])
    grp = c1.selectbox('组别', ['全部'] + C.GROUPS, key='g_grp')
    q = c2.text_input('搜索姓名 / 员工号', key='g_q')
    rng_ = c3.slider('日期范围', 1, C.DAYS, (1, C.DAYS), key='g_rng')
    only = c4.checkbox('只看最近一次调整涉及的人员', value=bool(hl), key='g_hl', disabled=not hl)
    ps = [p for p in st_['pilots'] if (grp == '全部' or C.rankGroup(p['rank']) == grp) and (not q or q in p['name'] or q in p['id'])]
    if only and hl: ps = [p for p in ps if p['id'] in hl['people']]
    ps.sort(key=lambda p: (C.GROUPS.index(C.rankGroup(p['rank'])), -C.RANK_VAL[p['rank']], p['id']))
    st.caption('滚轮缩放、拖动平移、双击复位；条带颜色 = 组别，红/橙描边 = 执勤风险高/中（⚠/◔），⛔ = 超限；黄 = 备份，紫 = 意向休息，灰 = 请假。' + (' 白框 = 最近一次应用方案调整的任务。' if hl else ''))
    acts = st_.get('actuals') or None
    show_gantt(gantt(ps, rng_, hl=hl, acts=acts if acts else None), 'gantt_main')


def v_tasks():
    st_ = S(); s = summ(); V = {}
    for v in s['violations']:
        if v.get('pairing') and v['level'] != 'info': V.setdefault(v['pairing'], []).append(v['type'])
    f = st.radio('筛选', ['全部', '未满员', '已满员', '有违规', '特殊机场', '执勤高/中风险'], horizontal=True, key='t_f')
    rows = []
    for pr in st_['pairings']:
        full = all(pr['crew'].values()); rk = C.pairingRisk(pr, st_)
        if f == '未满员' and full: continue
        if f == '已满员' and not full: continue
        if f == '有违规' and pr['id'] not in V: continue
        if f == '特殊机场' and not C.specialAirportsOf(pr, st_): continue
        if f == '执勤高/中风险' and rk['risk'] not in ('over', 'high', 'med'): continue
        days = []
        for d in range(1, pr['ndays'] + 1):
            ls = [l for l in pr['legs'] if l['d'] == d]
            if ls: days.append(f"D{d} " + '-'.join([C.apName(ls[0]['from'], st_)] + [C.apName(l['to'], st_) for l in ls]) + f" {C.fmtT(ls[0]['dep'])}-{C.fmtT(ls[-1]['arr'])}")
        fd = ' | '.join(f"D{dy['d']} {C.fmtH(dy['planFdp'])}/{C.fmtH(dy['limit'])} 余{dy['planBuffer']}分{RISK_ICON[dy['planRisk']]}" for dy in rk['days'])
        rows.append({'任务号': pr['id'], '日期': f"11/{pr['start']:02d}", '天数': pr['ndays'], '机型': pr['ac'], '小时': round(C.pairingHours(pr), 1), '行程': '\n'.join(days),
                     '机': nm(pr['crew']['C']), '副': nm(pr['crew']['F']), '三': nm(pr['crew']['T']), '执勤风险': C.RISK_TXT[rk['risk']], 'FDP（计划/限制·余量）': fd,
                     '状态': '、'.join(sorted(set(V.get(pr['id'], [])))) or ('✔ 合规' if full else '未满员'),
                     '血压测试仪': '是' if any(l['from'] in (st_['settings'].get('bpTesterAirports') or []) for l in pr['legs']) else ''})
    st.caption(f'{len(rows)} 个任务')
    st.dataframe(pd.DataFrame(rows), use_container_width=True, height=640, hide_index=True)


def v_report():
    st_ = S(); s = summ(); S_ = st_['settings']
    c = st.columns(4)
    c[0].metric('硬性违规', s['hard']); c[1].metric('软性提示', s['soft']); c[2].metric('信息提示', s['info']); c[3].metric('全员基尼系数', f"{s['all']['gini']:.3f}")
    a, b = st.columns(2)
    with a:
        st.markdown('#### 各组月飞行小时（法规硬上限 %sh）' % C.rules._num(C.hardCap(st_)))
        fig = go.Figure()
        for g in C.GROUPS:
            h = s['groups'][g]['hours']
            fig.add_trace(go.Box(y=[x['hours'] for x in s['per'] if x['group'] == g], name=f"{g}（{h['n']}人）", marker_color=GROUP_COLOR[g], boxmean=True))
        fig.add_hline(y=C.hardCap(st_), line_dash='dash', line_color='#ff5a6a', annotation_text='90h 硬上限')
        fig.update_layout(height=330, margin=dict(l=10, r=10, t=10, b=10), yaxis=dict(range=[20, 100], title='小时'), showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
    with b:
        st.markdown('#### 节奏：任务间休息天数分布')
        gd = s['rhythm']['gapDist']
        fig = go.Figure(go.Bar(x=list(gd), y=list(gd.values()), marker_color=['#ff5a6a', '#2ecc8f', '#2ecc8f', '#ffb020', '#ff8c42']))
        fig.update_layout(height=330, margin=dict(l=10, r=10, t=10, b=10), xaxis=dict(type='category', title='休息天数'), yaxis_title='次数')
        st.plotly_chart(fig, use_container_width=True)
        st.caption(f"休 2–3 天占比 {s['rhythm']['gap23'] * 100:.1f}% · 平均 {s['rhythm']['gapMean']:.2f} 天 · 备份 {s['rhythm']['standbyTotal']} 人次 · 意向休息 {s['prefOK']}/{s['prefT']}")
    r = C.fdpRiskSummary(st_)
    st.markdown(f"#### 执勤风险（计划 FDP 与延误余量） <span class='mut small'>{r['n']} 个值勤日 · 限制表为默认值（参考 CCAR-121），可在设置中修改</span>", unsafe_allow_html=True)
    c = st.columns(4)
    for col, (kk, lab) in zip(c, [('over', '超限'), ('high', f"高（余量<{S_['fdpRiskHigh']}分）"), ('med', f"中（<{S_['fdpRiskMed']}分）"), ('low', '低')]): col.metric(lab, r['cnt'][kk])
    rows = [x for x in r['rows'] if x['risk'] != 'low'] + [x for x in r['rows'] if x['risk'] == 'low'][:5]
    st.dataframe(pd.DataFrame([{'任务': x['pr'], '值勤日': f"D{x['d']}", '日期': f"11/{x['date']:02d}", '段数': x['legs'], '计划 FDP': C.fmtH(x['fdp']), '限制': C.fmtH(x['limit']),
                                '延误余量(分)': x['buffer'], '风险': C.RISK_TXT[x['risk']], '次日过夜休息': (C.fmtH(x['restAfter']) + (' 偏短' if x['restShort'] else '')) if x['restAfter'] is not None else '—'} for x in rows]),
                 hide_index=True, use_container_width=True)
    if r['restShort']: st.caption(f"计划过夜休息低于 {S_['minOvernightRestH']}h：" + '、'.join(f"{x['pr']} D{x['d']}" for x in r['restShort']) + '（任务编排数据，提醒航线部门确认）')
    st.markdown('#### 问题明细')
    lv = st.multiselect('级别', ['hard', 'soft', 'info'], default=['hard', 'soft', 'info'], key='r_lv')
    st.dataframe(pd.DataFrame([{'级别': {'hard': '硬性', 'soft': '软性', 'info': '提示'}[v['level']], '类型': v['type'], '任务': v.get('pairing') or '', '说明': v['msg']} for v in s['violations'] if v['level'] in lv]),
                 hide_index=True, use_container_width=True, height=360)


def v_manual():
    st_ = S()
    ids = [p['id'] for p in st_['pairings']]
    pid = st.selectbox('选择任务', ids, key='m_pr', format_func=lambda i: f"{i} · " + ('✔' if all(next(p for p in st_['pairings'] if p['id'] == i)['crew'].values()) else '缺人'))
    pr = next(p for p in st_['pairings'] if p['id'] == pid)
    st.dataframe(pd.DataFrame([{'日序': f"D{l['d']}", '航班': l['flt'], '航段': f"{C.apName(l['from'], st_)}-{C.apName(l['to'], st_)}", '起飞': C.fmtT(l['dep']), '落地': C.fmtT(l['arr']),
                                '机型': l['ac'], '特殊机场': '、'.join(C.apName(x, st_) for x in (l['from'], l['to']) if C.isSpecial(x, st_))} for l in pr['legs']]), hide_index=True, use_container_width=True)
    cols = st.columns(3); choice = {}
    for col, slot in zip(cols, C.SLOTS):
        with col:
            cands = C.candidates(st_, pr, slot)
            ok = [c for c in cands if c['ok']]
            opts = [None] + [c['p']['id'] for c in ok]
            cur = pr['crew'][slot]
            if cur and cur not in opts: opts.insert(1, cur)
            lab = {c['p']['id']: f"{c['p']['name']} {c['p']['rank']} · {c['hours']:.1f}h" + (f" ⚠{c['warn']}" if c['warn'] else '') + (' · 备份' if c['standby'] else '') for c in cands}
            choice[slot] = st.selectbox(SLOT_TXT[slot], opts, index=opts.index(cur) if cur in opts else 0, format_func=lambda i: '— 空缺 —' if not i else lab.get(i, i), key=f'm_{pid}_{slot}')
            with st.expander(f'不合规人员（{len(cands) - len(ok)}）'):
                st.markdown("<div class='small'>" + '<br>'.join(f"{c['p']['name']} {c['p']['rank']}：<span class='mut'>{'；'.join(c['reasons'])}</span>" for c in cands if not c['ok'] and C.slotRankOK(slot, c['p']['rank'])) + '</div>', unsafe_allow_html=True)
    if st.button('保存调整', type='primary'):
        old = dict(pr['crew']); pr['crew'] = choice
        iss = C.crewIssue(pr, [pm.get(choice[s]) for s in C.SLOTS], st_)
        if iss:
            pr['crew'] = old; st.error('组合不合规：' + iss)
        else:
            st.session_state.hist.push({**st_, 'pairings': [{**p, 'crew': old} if p is pr else p for p in st_['pairings']]}, f'手工调整 {pid}')
            save(); st.success('已保存'); st.rerun()


def v_leave():
    st_ = S(); idx = C.buildIndex(st_)
    c1, c2, c3 = st.columns([3, 2, 1])
    ps = sorted(st_['pilots'], key=lambda p: (C.GROUPS.index(C.rankGroup(p['rank'])), p['id']))
    pid = c1.selectbox('请假人员', [p['id'] for p in ps], format_func=lambda i: f"{pm[i]['name']} {pm[i]['rank']} · {idx['hours'][i]:.1f}h · 任务 {len(idx['sched'][i])}", key='l_p')
    sched = idx['sched'][pid]
    c1.caption('本月任务：' + '；'.join(f"{pr['id']} {pr['start']}–{pr['start'] + pr['ndays'] - 1}日" for pr in sched))
    d = c2.slider('请假日期', 1, C.DAYS, (sched[1]['start'] if len(sched) > 1 else 9, (sched[2]['start'] + sched[2]['ndays'] - 1) if len(sched) > 2 else 14), key='l_d')
    if c3.button('生成调配方案', type='primary', use_container_width=True):
        with st.spinner('正在生成方案…'):
            st.session_state.leave_opts = C.leaveOptions(st_, pid, list(range(d[0], d[1] + 1)))
    o = st.session_state.leave_opts
    if not o: st.info('选择人员与日期后点击「生成调配方案」：将给出 调用备份 / 节奏最优 / 工时均衡 / 链式调换 / 备选 等 3–5 个方案，不可行时给出人工处理及受阻规则。'); return
    p = o['pilot']
    st.markdown(f"**{p['name']}（{p['rank']}）请假 {o['days'][0]}–{o['days'][-1]} 日** · 受影响任务 {len(o['affected'])} 个 · 生成 {len(o['solutions'])} 个方案 · 用时 {o['ms']} ms")
    cols = st.columns(min(3, len(o['solutions'])))
    for i, sol in enumerate(o['solutions']):
        with cols[i % len(cols)]:
            sol_card(sol, i, 'lv', lambda s: f"{p['name']} 请假 {o['days'][0]}–{o['days'][-1]} 日 · {s['name']}", on_apply=lambda: st.session_state.update(leave_opts=None))
    preview(o['solutions'], 'lv', o['days'])


def v_duty():
    st_ = S(); S_ = st_['settings']; acts = st_.setdefault('actuals', {})
    c1, c2, c3 = st.columns([2, 3, 3])
    r0 = C.fdpRiskSummary(st_)['rows']
    date = c1.selectbox('日期', list(range(1, C.DAYS + 1)), index=(r0[0]['date'] - 1) if r0 else 0, format_func=date_txt, key='d_date')
    mon = C.dutyMonitor(st_, date)
    c2.markdown(f"<div class='small' style='padding-top:30px'>当日执行任务 {len(mon)} 个 · 预计超限 <b class='{'red' if any(x['exceed'] for x in mon) else 'okc'}'>{sum(1 for x in mon if x['exceed'])}</b> · "
                f"下游休息受影响 {sum(1 for x in mon if x['downstream'])} · 已录入时刻 {len(acts)} 段</div>", unsafe_allow_html=True)
    b1, b2 = c3.columns(2)
    if b1.button('模拟：风险最高任务第 2 段预计晚 120 分', use_container_width=True) and mon:
        x = sorted(mon, key=lambda x: x['day']['buffer'])[0]; l = x['day']['legs'][min(1, len(x['day']['legs']) - 1)]
        acts[C.legKey(l['leg'])] = {'dep': l['dep'] + 120, 'arr': l['arr'] + 120, 'kind': 'est'}; st.session_state.duty_opts = None; save(); st.rerun()
    if b2.button('清除当日录入', use_container_width=True):
        for x in mon:
            for l in x['day']['legs']: acts.pop(C.legKey(l['leg']), None)
        st.session_state.duty_opts = None; save(); st.rerun()
    st.caption(f"FDP = 报到（首段计划起飞前 {S_['reportMin']} 分钟）→ 当日最晚的实际/预计落地。未录入航段按计划时刻，前段延误不会自动顺延到后续航段；若不追回会超限仅提示（不计入超限）。限制表为默认值（参考 CCAR-121），可在设置中修改。")
    for x in mon:
        dy = x['day']; pr = x['pr']
        head = (f"{RISK_ICON[dy['risk']] or '●'} {pr['id']} D{dy['d']}/{pr['ndays']} · 机 {nm(pr['crew']['C'])} / 副 {nm(pr['crew']['F'])} / 三 {nm(pr['crew']['T'])} · "
                + (f"已落地 {dy['nLanded']}/{len(dy['legs'])} · " if dy['nLanded'] else '') + f"预计 FDP {C.fmtH(dy['fdp'])} / {C.fmtH(dy['limit'])} · "
                + (f"超 {dy['exceed']} 分钟" if dy['exceed'] else f"剩余余量 {dy['buffer']} 分钟"))
        with st.expander(head, expanded=bool(x['exceed'] or dy['cascExceed'] or x['downstream'] or dy['nKnown'])):
            st.progress(min(1.0, dy['fdp'] / dy['limit'] / 1.3), text=f"FDP {dy['fdp'] / dy['limit'] * 100:.0f}% of limit")
            rows = []
            for l in dy['legs']:
                a = acts.get(C.legKey(l['leg'])) or {}
                rows.append({'航班': l['leg']['flt'], '航段': f"{C.apName(l['leg']['from'], st_)}-{C.apName(l['leg']['to'], st_)}", '计划': f"{C.fmtT(l['leg']['dep'])}-{C.fmtT(l['leg']['arr'])}",
                             '实际/预计起飞': mdt(a['dep']) if a.get('dep') is not None else None, '实际/预计落地': mdt(a['arr']) if a.get('arr') is not None else None,
                             '状态': '实际' if a.get('kind') == 'act' else '预计', '偏差': (('✔' if l['landed'] else '') + f"落地 {l['lateArr']:+d} 分") if l['known'] else ('按计划' + (f"（前段晚到 {l['conflict']} 分）" if l['conflict'] else ''))})
            df = pd.DataFrame(rows)
            ed = st.data_editor(df, key=f"ed_{pr['id']}_{date}", hide_index=True, use_container_width=True, disabled=['航班', '航段', '计划', '偏差'],
                                column_config={'实际/预计起飞': st.column_config.DatetimeColumn(format='MM-DD HH:mm', step=60),
                                               '实际/预计落地': st.column_config.DatetimeColumn(format='MM-DD HH:mm', step=60),
                                               '状态': st.column_config.SelectboxColumn(options=['预计', '实际'])})
            changed = False
            for l, (_, r) in zip(dy['legs'], ed.iterrows()):
                kk = C.legKey(l['leg']); a = dict(acts.get(kk) or {})
                for col, f in (('实际/预计起飞', 'dep'), ('实际/预计落地', 'arr')):
                    v = r[col]; v = None if v is None or pd.isna(v) else int(round(dmin(pd.Timestamp(v).to_pydatetime())))
                    if v is None: a.pop(f, None)
                    else: a[f] = v
                a['kind'] = 'act' if r['状态'] == '实际' else 'est'
                new = a if (a.get('dep') is not None or a.get('arr') is not None) else None
                if new != (acts.get(kk) or None) and not (new is None and kk not in acts):
                    if new: acts[kk] = new
                    else: acts.pop(kk, None)
                    changed = True
            if changed: st.session_state.duty_opts = None; save(); st.rerun()
            if dy['exLeg']: st.markdown(f"<span class='red'>✖ 自 {dy['exLeg']['leg']['flt']} {C.apName(dy['exLeg']['leg']['from'], st_)}-{C.apName(dy['exLeg']['leg']['to'], st_)} 起超出 FDP 限制 {dy['exceed']} 分钟（报到 {C.fmtT(dy['start'])}，限制至 {C.fmtT(dy['start'] + dy['limit'])}）</span>", unsafe_allow_html=True)
            if dy['cascExceed']: st.markdown(f"<span class='mut'>ⓘ 若不追回将超限：前段延误按最短过站顺延，预计 {dy['cascLeg']['leg']['flt']} 落地 {C.fmtT(dy['cascLeg']['carr'])}，超 {dy['cascExceed']} 分钟（提示，不计入超限）</span>", unsafe_allow_html=True)
            for dd in x['downstream']:
                st.markdown("<span class='warnc'>↳ " + (f"D{dd['d']} 过夜休息压缩至 {C.fmtH(dd['restAfter'])}（低于 {S_['minOvernightRestH']}h，差 {dd['short']} 分钟）" if dd.get('overnight')
                            else f"{nm(dd['pilot'])} 下一任务 {dd['next']} 前休息仅 {C.fmtH(dd['gap'])}（低于 {S_['minRestH']}h，差 {dd['short']} 分钟）") + '</span>', unsafe_allow_html=True)
            if x['exceed'] or x['downstream']:
                if st.button('生成处置方案', key=f"go_{pr['id']}", type='primary' if x['exceed'] else 'secondary'):
                    with st.spinner('正在生成方案…'): st.session_state.duty_opts = C.fdpOptions(st_, pr['id'])
    o = st.session_state.duty_opts
    if o:
        st.markdown(f"### {o['pairing']['id']} 处置方案 <span class='mut small'>{'D' + str(o['exceed']['d']) + ' 预计超 FDP ' + str(o['exceed']['exceed']) + ' 分钟' if o['exceed'] else '下游休息不足'} · {len(o['solutions'])} 个方案 · {o['ms']} ms</span>", unsafe_allow_html=True)
        cols = st.columns(min(3, len(o['solutions'])))
        for i, sol in enumerate(o['solutions']):
            with cols[i % len(cols)]:
                sol_card(sol, i, 'dt', lambda s: f"{o['pairing']['id']} {'超执勤' if o['exceed'] else '休息不足'}处置 · {s['name']}", on_apply=lambda: st.session_state.update(duty_opts=None))
        preview(o['solutions'], 'dt', [d['date'] for d in o['days']])


def v_welfare():
    st_ = S(); S_ = st_['settings']; s = summ()
    off = {'C': [0] * (C.DAYS + 1), 'F': [0] * (C.DAYS + 1)}
    for p in st_['pilots']:
        kk = 'F' if C.isFO(p['rank']) else 'C'
        for d in set((p.get('prefs') or []) + (p.get('leave') or [])): off[kk][d] += 1
    a, b = st.columns(2)
    for col, kk, lab, lim, color in ((a, 'C', '机长类', S_['maxOffCapt'], '#3ea6ff'), (b, 'F', '副驾驶', S_['maxOffFO'], '#2ecc8f')):
        with col:
            st.markdown(f'#### 每日休息/请假人数 · {lab}（上限 {lim} 人/天）')
            ys = off[kk][1:]
            fig = go.Figure(go.Bar(x=list(range(1, C.DAYS + 1)), y=ys, marker_color=['#ff5a6a' if v > lim else color for v in ys]))
            fig.add_hline(y=lim, line_dash='dash', line_color='#ff5a6a'); fig.update_layout(height=230, margin=dict(l=10, r=10, t=10, b=10), xaxis=dict(dtick=1))
            st.plotly_chart(fig, use_container_width=True)
    st.markdown(f"#### 意向休息日申报 <span class='mut small'>每人可申报 2 个意向休息日；满足率 {s['prefRate'] * 100:.1f}%（{s['prefOK']}/{s['prefT']}）</span>", unsafe_allow_html=True)
    per = {x['id']: x for x in s['per']}
    df = pd.DataFrame([{'员工号': p['id'], '姓名': p['name'], '级别': p['rank'], '意向休息日 1': (p.get('prefs') or [None, None])[0] if p.get('prefs') else None,
                        '意向休息日 2': p['prefs'][1] if len(p.get('prefs') or []) > 1 else None, '请假日': ','.join(map(str, p.get('leave') or [])) or '—',
                        '满足情况': ('✔ 全部满足' if per[p['id']]['prefOK'] == per[p['id']]['prefTotal'] else f"{per[p['id']]['prefOK']}/{per[p['id']]['prefTotal']}") if per[p['id']]['prefTotal'] else '—',
                        '本月小时': round(per[p['id']]['hours'], 1), '夜航段': per[p['id']]['night'], '过夜': per[p['id']]['overnights'], '备份天数': per[p['id']]['standby'],
                        '任务间休息天数': ' '.join(map(str, per[p['id']]['gaps']))} for p in st_['pilots']])
    ed = st.data_editor(df, hide_index=True, use_container_width=True, height=480, key='w_ed',
                        disabled=[c for c in df.columns if not c.startswith('意向休息日')],
                        column_config={c: st.column_config.SelectboxColumn(options=list(range(1, C.DAYS + 1))) for c in ('意向休息日 1', '意向休息日 2')})
    msgs = []; changed = False
    for p, (_, r) in zip(st_['pilots'], ed.iterrows()):
        new = sorted({int(v) for v in (r['意向休息日 1'], r['意向休息日 2']) if v is not None and not pd.isna(v)})
        if new != sorted(p.get('prefs') or []):
            kk = 'F' if C.isFO(p['rank']) else 'C'; lim = S_['maxOffFO'] if kk == 'F' else S_['maxOffCapt']
            bad = [d for d in new if d not in (p.get('prefs') or []) and d not in (p.get('leave') or []) and off[kk][d] >= lim]
            if bad: msgs.append(f"{p['name']}：{bad} 日休息人数已达上限 {lim}")
            else: p['prefs'] = new; changed = True
    for m in msgs: st.warning(m)
    if changed: save(); st.rerun()


def v_settings():
    st_ = S(); S_ = st_['settings']
    a, b = st.columns(2)
    with a:
        st.markdown('#### 排班参数')
        vals = {}
        for kk, lab, step in [('minRestH', '两任务间最短休息（小时）', 0.5), ('hardMaxHours', '月飞行小时法规硬上限（CAAC，小时）', 1.0), ('maxOffCapt', '同日最多休息/请假（机长类）', 1.0),
                              ('maxOffFO', '同日最多休息/请假（副驾驶）', 1.0), ('standbyPerDay', '每日备份人数', 1.0), ('maxStandbyPerPilot', '每人每月最多备份（天）', 1.0),
                              ('gapWeight', '休息 2–3 天偏好权重', 0.05), ('reportMin', '报到：首段起飞前（分钟）', 5.0), ('releaseMin', '释放：末段落地后（分钟）', 5.0)]:
            vals[kk] = st.number_input(lab, value=float(S_[kk]), step=step, key=f's_{kk}')
        hp = st.checkbox('自动排班优先保障意向休息日（无法满员时才放宽）', value=bool(S_.get('honorPrefs')), key='s_hp')
        st.caption('月飞行小时仅设 CAAC 法规硬上限；自动排班按可用天数折算份额做公平均衡（基尼系数），不设目标上下限。')
        aps = {**C.AIRPORTS, **(st_.get('airports') or {})}
        bpt = st.multiselect('血压测试仪机场（作为始发站出港时须配备，清单待确认，可随时调整）', list(aps), default=S_.get('bpTesterAirports') or [], format_func=lambda c: f"{c} {aps[c][0]}", key='s_bpt')
    with b:
        st.markdown("#### 飞行值勤期（FDP）限制 <span class='warnc small'>默认值，参考 CCAR-121 部非扩编机组表，可按公司规定修改</span>", unsafe_allow_html=True)
        fdf = pd.DataFrame([{'报到时间（本地）': r['label'], **{c: r['lim'][i] for i, c in enumerate(C.LEG_COLS)}} for r in S_['fdpTable']])
        fed = st.data_editor(fdf, hide_index=True, use_container_width=True, disabled=['报到时间（本地）'], key='s_fdp',
                             column_config={c: st.column_config.NumberColumn(c + '（h）', step=0.5, min_value=1.0, max_value=24.0) for c in C.LEG_COLS})
        st.caption(f"FDP = 当日首段计划起飞前报到 → 末段落地（挡轮挡）；按报到时刻与当日航段数查表。")
        aug = st.checkbox('三人机组按扩编机组计算（须具备符合要求的机上休息设施）', value=bool(S_.get('fdpAugmented')), key='s_aug')
        v2 = {}
        for kk, lab, step in [('fdpAugLimitH', '扩编机组 FDP 限制（小时）', 0.5), ('fdpRiskHigh', '高风险：延误余量 <（分钟）', 5.0), ('fdpRiskMed', '中风险：延误余量 <（分钟）', 5.0),
                              ('minTurnMin', '「若不追回」推算最短过站（分钟）', 5.0), ('minOvernightRestH', '任务内过夜最低休息（小时）', 0.5)]:
            v2[kk] = st.number_input(lab, value=float(S_[kk]), step=step, key=f's_{kk}')
        if st.button('恢复默认 FDP 表'):
            S_['fdpTable'] = C.defaultFdpTable(); save(); st.rerun()
    st.markdown('#### 机场与特殊机场类别')
    st.caption('类别：' + '；'.join(f"{kk}={v}" for kk, v in C.CAT_DESC.items()) + f"。需授权类别：{'/'.join(C.AUTH_CATS)}")
    adf = pd.DataFrame([{'ICAO': c, '名称': v[0], '类别': (v[3] if len(v) > 3 and v[3] else 'NONE')} for c, v in aps.items()])
    aed = st.data_editor(adf, hide_index=True, use_container_width=True, height=300, disabled=['ICAO', '名称'], key='s_ap',
                         column_config={'类别': st.column_config.SelectboxColumn(options=['NONE', 'LHASA', 'HIGH', 'PLATEAU', 'ZBCF', 'J1', 'US'])})
    if st.button('保存设置并重新校验', type='primary'):
        def num(v): return int(v) if float(v).is_integer() else float(v)
        for kk, v in {**vals, **v2}.items(): S_[kk] = num(v)
        S_['honorPrefs'] = hp; S_['fdpAugmented'] = aug; S_['bpTesterAirports'] = bpt
        for i, (_, r) in enumerate(fed.iterrows()): S_['fdpTable'][i]['lim'] = [num(r[c]) for c in C.LEG_COLS]
        st_['airports'] = {}
        for _, r in aed.iterrows():
            if r['ICAO'] == 'ZUUU': continue
            arr = C.AIRPORTS[r['ICAO']][:3]
            if r['类别'] != 'NONE': arr = arr + [r['类别']]
            st_['airports'][r['ICAO']] = arr
        save(); st.success('设置已保存，校验结果已更新'); st.rerun()


def v_io():
    st_ = S(); s = summ()
    a, b = st.columns(2)
    with a:
        st.markdown('#### 导出')
        st.caption('CSV 为 UTF-8 BOM 格式，可直接用 Excel 打开；JSON 备份与网页版互通（网页「恢复备份 JSON」可直接导入）。')
        for lab, name, rows in [('排班表（按航段，含机组）', '排班表_2026-11.csv', rio.roster_rows(st_)), ('人员工时统计', '人员工时_2026-11.csv', rio.hours_rows(st_, s)),
                                ('校验问题清单', '校验问题_2026-11.csv', rio.violation_rows(s)), ('人员数据', '人员数据.csv', rio.pilot_rows(st_)), ('任务数据', '任务数据.csv', rio.pairing_rows(st_))]:
            st.download_button(lab, rio.to_csv(rows).encode('utf-8'), file_name=name, mime='text/csv', use_container_width=True)
        st.download_button('完整备份 JSON', rio.dumps(st_).encode('utf-8'), file_name='排班备份.json', mime='application/json', use_container_width=True, type='primary')
        st.download_button('人员模板 CSV', rio.to_csv([rio.PIL_H, ['E10001', '张三', 'J3', 'ZULS;ZPLJ', '5;18', ''], ['E10002', '李四', 'F5', 'ZUJZ', '7;21', '12;13;14']]).encode('utf-8'), file_name='人员模板.csv', use_container_width=True)
        st.download_button('任务模板 CSV', rio.to_csv([rio.PR_H, ['PR901', 1, 'EU2201', 'ZUUU', 'ZWWW', 3, '08:00', '12:20', 'A320'], ['PR901', 1, 'EU2202', 'ZWWW', 'ZUUU', 3, '13:20', '17:30', 'A320'],
                                                       ['PR902', 1, 'EU6683', 'ZUUU', 'ZGHA', 5, '21:00', '22:50', 'A320'], ['PR902', 2, 'EU6684', 'ZGHA', 'ZUUU', 6, '07:30', '09:20', 'A320']]).encode('utf-8'),
                           file_name='任务模板.csv', use_container_width=True)
    with b:
        st.markdown('#### 导入')
        for lab, kind, typ in [('导入人员 CSV（替换全部人员并清空排班）', 'pil', 'csv'), ('导入任务 CSV（替换全部任务）', 'pr', 'csv'), ('恢复备份 JSON（网页版或本程序导出）', 'json', 'json')]:
            f = st.file_uploader(lab, type=[typ], key=f'up_{kind}')
            if f is not None and st.button('确认导入', key=f'upb_{kind}'):
                try:
                    text = f.getvalue().decode('utf-8-sig')
                    st.session_state.hist.push(st_, '导入前')
                    if kind == 'pil': n = rio.import_pilots(st_, text); msg = f'已导入 {n} 名人员'
                    elif kind == 'pr': n = rio.import_pairings(st_, text); msg = f'已导入 {n} 个任务'
                    else: st.session_state.roster = rio.loads(text); msg = '备份已恢复'
                    save(); st.success(msg); st.rerun()
                except Exception as e:
                    st.error(f'导入失败：{e}')
        st.markdown('#### 格式说明')
        st.caption(f"人员 CSV 列：{'，'.join(rio.PIL_H)}；级别取值：{' / '.join(C.RANKS)}。任务 CSV 列：{'，'.join(rio.PR_H)}；同一任务号的多行即该任务的各航段，任务须从 ZUUU 出发并回到 ZUUU。")


{'人员视图': v_people, '任务视图': v_tasks, '校验报告': v_report, '手工调整': v_manual, '请假调配': v_leave, '执勤监控': v_duty,
 '员工福利': v_welfare, '设置': v_settings, '导入导出': v_io}[view]()
