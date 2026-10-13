import json

import roster as C
from roster import io


def test_json_roundtrip_web_compatible(st, tmp_path):
    st['actuals'] = {}
    p = tmp_path / 'b.json'; io.save(st, p)
    back = io.load(p)
    assert back['pairings'] == st['pairings'] and back['pilots'] == st['pilots']


def test_import_web_export_with_old_fields(st):
    st['settings']['minHours'] = 30; st['settings']['maxHours'] = 70; st['settings']['testerAirports'] = ['ZLXY']
    pr = st['pairings'][0]; k = C.legKey(pr['legs'][0]); st['delays'] = {k: 30}
    back = io.loads('\ufeff' + json.dumps(st, ensure_ascii=False))
    assert 'minHours' not in back['settings'] and back['settings']['bpTesterAirports'] == ['ZLXY']
    assert back['actuals'][k] == {'dep': pr['legs'][0]['dep'] + 30, 'arr': pr['legs'][0]['arr'] + 30, 'kind': 'est'}


def test_csv_roundtrip(st):
    pil = io.to_csv(io.pilot_rows(st)); prs = io.to_csv(io.pairing_rows(st))
    assert pil.startswith('\ufeff') and '\r\n' in pil
    w = json.loads(json.dumps(st))
    assert io.import_pilots(w, pil) == 100 and io.import_pairings(w, prs) == 148
    assert [p['legs'] for p in w['pairings']] == [p['legs'] for p in st['pairings']]
    assert [x['id'] for x in w['pilots']] == [x['id'] for x in st['pilots']]


def test_report_csvs(st):
    s = C.summarize(st)
    assert len(io.roster_rows(st)) == 1 + sum(len(p['legs']) for p in st['pairings'])
    assert len(io.hours_rows(st, s)) == 101 and io.violation_rows(s)[0] == ['级别', '类型', '任务', '说明']
