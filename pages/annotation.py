from __future__ import annotations

import json
import logging

from nicegui import run, ui

from config import LOW_CONFIDENCE_THRESHOLD
from core.annotation_manager import load_annotation, save_annotation, verify_image
from core.image_manager import get_image, list_images, thumbnail_url
from core.project_manager import load_project
from core.predictor import prelabel_image
from pages.layout import page_shell


LOGGER = logging.getLogger(__name__)
STATUS_NAMES = {"unlabeled": "待炼", "prelabeled": "预炼", "verified": "精炼", "discarded": "废渣"}


def _next_image_id(project_id: str, current_id: str) -> str | None:
    records = [item for item in list_images(project_id, sort_by="oldest") if item["status"] != "discarded"]
    ids = [item["id"] for item in records]
    if current_id not in ids or len(ids) < 2:
        return None
    index = ids.index(current_id)
    return ids[(index + 1) % len(ids)]


def _annotation_page(project_id: str, image_id: str) -> None:
    try:
        project = load_project(project_id)
        image = get_image(project_id, image_id)
        annotation = load_annotation(project_id, image_id)
    except Exception as exc:
        LOGGER.exception("Open annotation workspace failed", exc_info=exc)
        with page_shell("炼数工作台", project_id, immersive=True):
            ui.label("无法打开炼数工作台").classes("text-2xl font-bold")
            ui.label(str(exc)).classes("text-red-600")
        return

    ui.add_head_html('<link rel="stylesheet" href="/static/annotation.css?v=4">')
    ui.add_head_html('<script src="/static/annotation.js?v=4"></script>')
    root_id = f"df_{project_id}_{image_id}"
    state = {"pending": None}

    with page_shell("炼数工作台", project_id, immersive=True):
        with ui.row().classes("w-full items-center"):
            with ui.column().classes("gap-0"):
                ui.label(image["filename"]).classes("text-2xl font-bold")
                ui.label(f"{image['width']}×{image['height']} · {STATUS_NAMES[image['status']]}").classes("text-slate-500")
            ui.space()
            ui.button("返回数据大厅", icon="arrow_back", on_click=lambda: request_navigation(None)).props("flat")
            action_slot = ui.row().classes("items-center gap-2")

        with ui.element("div").props(f'id="{root_id}" tabindex="0"').classes("df-workspace"):
            with ui.element("aside").classes("df-queue"):
                ui.label("图片队列").classes("df-panel-title")
                for record in list_images(project_id, sort_by="oldest"):
                    if record["status"] == "discarded":
                        continue
                    with ui.element("button").classes(
                        "df-queue-item" + (" active" if record["id"] == image_id else "")
                    ).on("click", lambda _, iid=record["id"]: request_navigation(iid)):
                        ui.image(thumbnail_url(project_id, record["id"]))
                        with ui.element("span").classes("df-queue-meta"):
                            ui.label(record["filename"]).classes("df-queue-name")
                            ui.label(STATUS_NAMES[record["status"]]).classes("df-queue-status")

            with ui.element("main").classes("df-center"):
                ui.html(
                    '<div class="df-toolbar">'
                    '<button class="df-tool active" data-mode="select">V 选择</button>'
                    '<button class="df-tool" data-mode="box">B 矩形框</button>'
                    '<button class="df-tool" data-action="confidence">显示置信度</button>'
                    '<button class="df-tool danger" data-action="delete">Delete 删除</button>'
                    '</div>'
                )
                frame_style = (
                    f"aspect-ratio:{image['width']}/{image['height']};"
                    f"width:min(100%,calc((100vh - 270px)*{image['width'] / image['height']}));"
                )
                with ui.element("div").classes("df-stage"):
                    ui.html(
                        f'<div class="df-canvas-frame" style="{frame_style}">'
                        f'<img src="/storage/projects/{project_id}/images/{image["stored_name"]}" draggable="false">'
                        '<svg class="df-overlay" viewBox="0 0 1 1" preserveAspectRatio="none"></svg>'
                        '</div>'
                    ).classes("w-full flex justify-center")
                ui.html(
                    f'<div class="df-statusbar"><span>{STATUS_NAMES[image["status"]]}</span>'
                    '<span class="df-count">0 个目标</span><span class="df-save-state">已保存</span></div>'
                )

            with ui.element("aside").classes("df-inspector"):
                ui.html(
                    '<div class="df-panel-title">标注对象</div>'
                    '<div class="df-object-list"></div>'
                    '<div class="df-panel-title" style="margin-top:18px">目标类别</div>'
                    '<select class="df-class-select" disabled></select>'
                    '<div class="df-help">快捷键：V 选择 · B 画框 · P AI预炼 · Delete 删除 · Ctrl+S 保存 · Space 确认下一张 · 1~9 切换类别</div>'
                )

        async def read_editor_state() -> dict:
            return await ui.run_javascript(
                f"window.dataForgeAnnotators[{json.dumps(root_id)}].getState()",
                timeout=10,
            )

        async def save_current(*_) -> bool:
            try:
                editor = await read_editor_state()
                save_annotation(project_id, image_id, {"objects": editor["objects"]})
                await ui.run_javascript(f"window.dataForgeAnnotators[{json.dumps(root_id)}].markSaved()")
                ui.notify("草稿已保存", type="positive")
                return True
            except Exception as exc:
                LOGGER.exception("Save annotation failed", exc_info=exc)
                ui.notify(f"保存失败：{exc}", type="negative", close_button=True)
                return False

        async def verify_and_next(*_) -> None:
            try:
                editor = await read_editor_state()
                verify_image(project_id, image_id, {"objects": editor["objects"]})
                await ui.run_javascript(f"window.dataForgeAnnotators[{json.dumps(root_id)}].markSaved()")
                target = _next_image_id(project_id, image_id)
                ui.notify("当前图片已精炼确认", type="positive")
                ui.navigate.to(f"/annotate/{project_id}/{target}" if target else f"/project/{project_id}")
            except Exception as exc:
                LOGGER.exception("Verify annotation failed", exc_info=exc)
                ui.notify(f"确认失败：{exc}", type="negative", close_button=True)

        async def ai_prelabel(*_) -> None:
            progress = None
            try:
                editor = await read_editor_state()
                if editor.get("dirty"):
                    ui.notify("请先保存或放弃当前修改，再执行 AI 预炼。", type="warning")
                    return
                progress = ui.notification(
                    "正在使用当前模型进行 CPU 推理…",
                    type="ongoing",
                    spinner=True,
                    timeout=None,
                )
                await run.io_bound(prelabel_image, project_id, image_id)
                ui.notify("AI 预炼完成", type="positive")
                ui.navigate.to(f"/annotate/{project_id}/{image_id}")
            except Exception as exc:
                LOGGER.exception("AI prelabel failed", exc_info=exc)
                ui.notify(f"AI 预炼失败：{exc}", type="negative", close_button=True)
            finally:
                if progress is not None:
                    progress.dismiss()

        async def request_navigation(target_id: str | None) -> None:
            editor = await read_editor_state()
            target = f"/annotate/{project_id}/{target_id}" if target_id else f"/project/{project_id}"
            if not editor.get("dirty"):
                ui.navigate.to(target)
                return
            state["pending"] = target
            unsaved_dialog.open()

        async def save_and_switch() -> None:
            if await save_current():
                unsaved_dialog.close()
                ui.navigate.to(state["pending"])

        async def discard_and_switch() -> None:
            await ui.run_javascript(f"window.dataForgeAnnotators[{json.dumps(root_id)}].markSaved()")
            unsaved_dialog.close()
            ui.navigate.to(state["pending"])

        with ui.dialog() as unsaved_dialog, ui.card().classes("p-6 gap-4"):
            ui.label("当前图片存在未保存修改").classes("text-lg font-bold")
            with ui.row().classes("justify-end"):
                ui.button("取消", on_click=unsaved_dialog.close).props("flat")
                ui.button("放弃修改", on_click=discard_and_switch, color="negative").props("flat")
                ui.button("保存并切换", on_click=save_and_switch)

        with action_slot:
            ai_button = ui.button(
                "AI 预炼",
                icon="auto_awesome",
                on_click=ai_prelabel,
            ).props("outline")
            if not project.get("active_model"):
                ai_button.disable()
                ai_button.tooltip("当前项目尚未配置检测模型，请先在模型熔炉完成训练。")
            ui.button("保存草稿", icon="save", on_click=save_current).props("outline")
            ui.button("确认并加载下一张", icon="task_alt", on_click=verify_and_next)

        options = {
            "objects": annotation["objects"],
            "classes": project["classes"],
            "lowThreshold": LOW_CONFIDENCE_THRESHOLD,
        }

        async def initialize_editor() -> None:
            await ui.run_javascript(
                f"window.createDataForgeAnnotator({json.dumps(root_id)}, {json.dumps(options, ensure_ascii=False)})",
                timeout=10,
            )

        ui.timer(0.2, initialize_editor, once=True)
        ui.on("dataforge-save-request", save_current)
        ui.on("dataforge-verify-request", verify_and_next)
        ui.on("dataforge-ai-request", ai_prelabel)


def register_annotation_pages() -> None:
    @ui.page("/annotate/{project_id}")
    def annotation_entry(project_id: str) -> None:
        records = [item for item in list_images(project_id, sort_by="oldest") if item["status"] != "discarded"]
        if records:
            ui.navigate.to(f"/annotate/{project_id}/{records[0]['id']}")
        else:
            ui.navigate.to(f"/project/{project_id}")

    @ui.page("/annotate/{project_id}/{image_id}")
    def annotation_workspace(project_id: str, image_id: str) -> None:
        _annotation_page(project_id, image_id)
