import io

from PIL import Image

import core.image_manager as images
import core.project_manager as projects


def _png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (64, 32), "red").save(buffer, "PNG")
    return buffer.getvalue()


def test_project_and_image_lifecycle(tmp_path, monkeypatch):
    monkeypatch.setattr(projects, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(images, "PROJECTS_DIR", tmp_path, raising=False)
    project = projects.create_project("测试项目", "说明", ["scratch", "crack"])
    assert project["classes"][1]["id"] == 1
    assert projects.load_project(project["id"])["name"] == "测试项目"

    image = images.add_image_bytes(project["id"], "中文.png", _png_bytes())
    assert image["width"] == 64
    assert images.stats(project["id"])["unlabeled"] == 1
    images.set_image_status(project["id"], image["id"], "discarded")
    assert images.stats(project["id"])["discarded"] == 1
    images.delete_image(project["id"], image["id"])
    assert images.stats(project["id"])["total"] == 0
