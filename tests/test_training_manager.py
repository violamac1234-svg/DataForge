import pytest

from core.training_manager import TrainingError, _validate_config


def test_cpu_training_config_validation():
    _validate_config(epochs=1, batch=1, imgsz=640, train_ratio=0.8, device="cpu")
    with pytest.raises(TrainingError):
        _validate_config(epochs=0, batch=1, imgsz=640, train_ratio=0.8, device="cpu")
    with pytest.raises(TrainingError):
        _validate_config(epochs=1, batch=1, imgsz=640, train_ratio=1.0, device="cpu")
    with pytest.raises(TrainingError):
        _validate_config(epochs=1, batch=1, imgsz=640, train_ratio=0.8, device="cuda")
