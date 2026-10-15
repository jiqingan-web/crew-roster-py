"""数据结构说明（与网页版 JSON 完全一致，均为普通 dict，便于 JSON 互通）。

时间：自 2026-11-01 00:00 起的分钟数（DAY = 1440），可跨午夜。

Pilot   = {id, name, rank, auth: [ICAO], prefs: [日], leave: [日]}
Leg     = {d: 任务内第几天, flt, from, to, dep, arr, ac: 'A320'|'A321', reg?: 机号如 'B-32GV'}
Pairing = {id, start, ndays, ac, legs: [Leg], crew: {C, F, T}, freshAt?, splitFrom?}
State   = {version, sample, settings, pilots, pairings, standby: {pilotId: [日]}, airports?: {ICAO: [名称, 纬度, 经度, 类别]},
           actuals?: {legKey: {dep?, arr?, kind: 'est'|'act'}}}
legKey  = f"{flt}@{dep}"（计划起飞分钟）
"""
from typing import TypedDict, Optional, List, Dict


class Pilot(TypedDict):
    id: str; name: str; rank: str; auth: List[str]; prefs: List[int]; leave: List[int]


class Leg(TypedDict, total=False):
    d: int; flt: str; dep: int; arr: int; ac: str; reg: str  # 另含 from / to（Python 关键字，用 dict 访问）


class Pairing(TypedDict, total=False):
    id: str; start: int; ndays: int; ac: str; legs: List[Leg]; crew: Dict[str, Optional[str]]; freshAt: str; splitFrom: str


class Actual(TypedDict, total=False):
    dep: int; arr: int; kind: str
