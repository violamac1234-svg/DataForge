from types import SimpleNamespace

import pytest

from core.predictor import _convert_result


class FakeTensor:
    def __init__(self, value):
        self.value = value

    def cpu(self):
        return self

    def tolist(self):
        return self.value


def test_result_adapter_is_framework_neutral():
    result = SimpleNamespace(
        boxes=SimpleNamespace(
            xyxyn=FakeTensor([[0.1, 0.2, 0.7, 0.8]]),
            cls=FakeTensor([2.0]),
            conf=FakeTensor([0.876]),
        )
    )
    assert _convert_result(result) == [
        {"class_id": 2, "bbox": pytest.approx([0.1, 0.2, 0.7, 0.8]), "confidence": pytest.approx(0.876)}
    ]
