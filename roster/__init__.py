"""机组智能排班助手 · Python 版核心（纯标准库）。与网页版 js/core.js 同算法、同随机种子，结果逐项一致。"""
from .rules import *  # noqa: F401,F403
from .rules import (YEAR, MONTH, DAYS, DAY, RANK_VAL, RANKS, GROUPS, AIRPORTS, CAT_DESC, AUTH_CATS, LEG_COLS, SLOT_NAME, SLOTS,
                    defaultSettings, defaultFdpTable, migrateSettings, pairingHours, report, release, daysTouched, fmtT, fmtH,
                    crewIssue, personCheck, buildIndex, candidates, dayStatus, restGaps, freeRuns, shareFor, fdpDays, fdpLimit, legKey,
                    apName, apCat, isSpecial, specialAirportsOf, isNightLeg, rankGroup, seatOK, catOK, blockMin, rng)
from .generator import generateSample
from .metrics import validate, summarize, stats
from .solver import autoFill, assignStandby, trimPeaks, repairPrefs, repairUnfilled
from .leave import applyLeave, leaveOptions, evaluate, fillVac, STRATS
from .fdp import (migrateDelays, pairingRisk, fdpRiskSummary, downstream, dutyMonitor, splitPairing, fdpOptions, RISK_ORDER, RISK_TXT)
from .history import History, apply_solution
from . import io

__version__ = '1.0.0'
