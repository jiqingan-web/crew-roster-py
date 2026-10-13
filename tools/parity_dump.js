// 用网页版 js/core.js 生成对照数据：node tools/parity_dump.js <roster-app 路径> > tests/golden_js.json
const path = require('path');
const C = require(path.resolve(process.argv[2] || '../roster-app', 'js/core.js'));
const r4 = x => Math.round(x * 1e6) / 1e6;
const solv = s => ({ name: s.name, score: s.score, sig: s.sig, hard: s.hard, unresolved: s.unresolved, recommended: !!s.recommended, fdpAfter: s.fdpAfter, restAfterV: s.restAfterV, giniD: r4(s.giniD || 0) });
const out = {};
const st = C.generateSample(); out.sample = { pilots: st.pilots.length, pairings: st.pairings.length, totalH: r4(st.pairings.reduce((a, p) => a + C.pairingHours(p), 0)) };
const s = C.autoFill(st);
out.autofill = { coverage: s.coverage, hard: s.hard, soft: s.soft, info: s.info, byType: s.byType, attempt: s.attempt,
  all: Object.fromEntries(Object.entries(s.all).map(([k, v]) => [k, r4(v)])), groups: Object.fromEntries(Object.entries(s.groups).map(([g, x]) => [g, { mean: r4(x.hours.mean), min: r4(x.hours.min), max: r4(x.hours.max), gini: r4(x.hours.gini) }])),
  prefOK: s.prefOK, prefT: s.prefT, gap23: r4(s.rhythm.gap23), gapDist: s.rhythm.gapDist, standbyTotal: s.rhythm.standbyTotal,
  crew: st.pairings.map(p => [p.crew.C, p.crew.F, p.crew.T]), standby: st.standby };
const filled = JSON.stringify(st);
{ const w = JSON.parse(filled); const idx = C.buildIndex(w);
  const cap = w.pilots.filter(p => p.rank === 'J3').sort((a, b) => idx.sched[b.id].length - idx.sched[a.id].length)[0];
  const days = [...new Set(idx.sched[cap.id].slice(1, 3).flatMap(pr => C.daysTouched(pr, w)))];
  const r = C.applyLeave(w, cap.id, days); const s2 = C.summarize(w);
  out.applyLeave = { pilot: cap.id, days, affected: r.affected, changes: r.changes.map(c => [c.pairing, c.slot, c.to.id, c.fromStandby]), unresolved: r.unresolved.length, hardAfter: s2.hard }; }
out.leaveOptions = {};
{ const w = JSON.parse(filled); const ix = C.buildIndex(w);
  for (const [lab, pred] of [['机长', p => p.rank === 'J3'], ['副驾驶', p => C.isFO(p.rank)], ['新机长', p => C.isNew(p.rank)], ['教员', p => C.isInstr(p.rank)]]) {
    const p = w.pilots.filter(pred).sort((a, b) => ix.sched[b.id].length - ix.sched[a.id].length)[0];
    const a = ix.sched[p.id][1], b = ix.sched[p.id][2]; const days = []; for (let d = a.start; d < b.start + b.ndays; d++) days.push(d);
    const r = C.leaveOptions(w, p.id, days); out.leaveOptions[lab] = { pilot: p.id, days, affected: r.affected.length, solutions: r.solutions.map(solv) }; } }
{ const w = JSON.parse(filled); w.settings.hardMaxHours = 40; const lh = w.pairings.find(pr => pr.legs.some(l => l.to === 'ZULS')) || w.pairings[0];
  const r = C.leaveOptions(w, lh.crew.C, C.daysTouched(lh, w)); const blk = r.solutions[0].steps.find(x => x.block);
  out.fallback = { solutions: r.solutions.map(solv), allManual: r.solutions.every(s => s.unresolved > 0 && s.manual), rules: blk.block.rules, top: blk.block.top }; }
{ const w = JSON.parse(filled); const p = w.pilots.find(x => x.name === '毛华' && x.rank === 'J3'); const r = C.leaveOptions(w, p.id, [9, 10, 11, 12, 13, 14]);
  const ok = r.solutions.filter(s => !s.unresolved && s.hard === 0); out.maohua = { solutions: r.solutions.map(solv), maxH: r4(Math.max(...ok.flatMap(s => s.people.map(x => x.ha)))) }; }
{ const w = JSON.parse(filled); const sm = C.fdpRiskSummary(w); out.fdpRisk = { cnt: sm.cnt, n: sm.n, top: sm.rows.slice(0, 8).map(r => [r.pr, r.d, r.buffer, r.risk]), restShort: sm.restShort.map(r => r.pr + 'D' + r.d) };
  const pr = w.pairings.find(p => p.id === 'PR140'); const d1 = pr.legs.filter(l => l.d === pr.legs[0].d); const K = C.legKey;
  w.actuals = { [K(d1[1])]: { dep: d1[1].dep + 240, arr: d1[1].arr + 240, kind: 'act' }, [K(d1[3])]: { dep: d1[3].dep + 120, arr: d1[3].arr + 120, kind: 'est' } };
  const dy = C.fdpDays(pr, w, w.actuals)[0]; const o = C.fdpOptions(w, 'PR140');
  out.fdp = { exceed: dy.exceed, fdp: dy.fdp, limit: dy.limit, restAfter: dy.restAfter, solutions: o.solutions.map(solv), reasons: o.solutions[o.solutions.length - 1].steps[0].block.rules,
    monitor: C.dutyMonitor(w, dy.date).slice(0, 5).map(x => [x.pr.id, x.day.buffer, x.exceed, x.downstream.length]) }; }
process.stdout.write(JSON.stringify(out, null, 1));
