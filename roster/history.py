"""撤销历史（请假调配与执勤处置共享）：保存应用方案前的完整快照。"""
import json
import time


class History:
    def __init__(self, limit=30):
        self.items = []; self.limit = limit

    def push(self, st, label):
        self.items.append({'snap': json.dumps(st, ensure_ascii=False), 'label': label, 'time': time.strftime('%H:%M:%S')})
        if len(self.items) > self.limit: self.items.pop(0)

    def undo(self):
        """返回 (恢复的状态, 标签)；无历史时返回 (None, None)"""
        if not self.items: return None, None
        x = self.items.pop()
        return json.loads(x['snap']), x['label']

    def __len__(self): return len(self.items)

    def to_list(self): return list(self.items)

    @classmethod
    def from_list(cls, items, limit=30):
        h = cls(limit); h.items = list(items or []); return h


def apply_solution(st, sol, hist, label):
    """一键应用方案：先存快照，再把方案中的排班状态写回 st（原地替换，返回新状态）"""
    if not sol or not sol.get('state'): raise ValueError('该方案需人工处理，无法一键应用')
    hist.push(st, label)
    return json.loads(json.dumps(sol['state'], ensure_ascii=False))
