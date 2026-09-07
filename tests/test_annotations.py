import io

import pytest
from PIL import Image

import core.project_manager as projects
from core.annotation_manager import AnnotationError, load_annotation, validate_bbox, verify_image, xyxy_to_yolo
from core.image_manager import add_image_bytes, get_image


def _image_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (100, 80), "white").save(buffer, "PNG")
    return buffer.getvalue()


@pytest.mark.parametrize("bbox", [[-0.1, 0, 1, 1], [0, 0, 1.1, 1], [0.4, 0, 0.4, 1], [0, 0.8, 1, 0.2]])
def test_invalid_bbox(bbox):
    with pytest.raises(AnnotationError):
        validate_bbox(bbox)


def test_bbox_edge_and_yolo_conversion():
    assert validate_bbox([0, 0, 1, 1]) == [0.0, 0.0, 1.0, 1.0]
    assert xyxy_to_yolo([0.1, 0.2, 0.5, 0.8]) == pytest.approx((0.3, 0.5, 0.4, 0.6))


def test_zero_target_can_be_verified(tmp_path, monkeypatch):
    monkeypatch.setattr(projects, "PROJECTS_DIR", tmp_path)
    project = projects.create_project("demo", "", ["scratch"])
    image = add_image_bytes(project["id"], "one.png", _image_bytes())
    data = load_annotation(project["id"], image["id"])
    verify_image(project["id"], image["id"], data)
    assert get_image(project["id"], image["id"])["status"] == "verified"
    assert load_annotation(project["id"], image["id"])["objects"] == []
