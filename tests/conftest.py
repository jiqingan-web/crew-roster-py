import copy
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import roster as C  # noqa: E402


@pytest.fixture(scope='session')
def filled_json():
    st = C.generateSample(); summ = C.autoFill(st)
    return json.dumps(st, ensure_ascii=False), summ


@pytest.fixture
def st(filled_json):
    return json.loads(filled_json[0])


@pytest.fixture
def summ(filled_json):
    return copy.deepcopy(filled_json[1])
