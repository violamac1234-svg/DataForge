from __future__ import annotations

import logging

from nicegui import run, ui
from nicegui.events import UploadEventArguments

from core.image_manager import add_image_bytes, delete_image, list_images, set_image_status, stats, thumbnail_url
from core.project_manager import ProjectError, create_project, list_projects, load_project
from core.predictor import prelabel_image
from pages.layout import page_shell


LOGGER = logging.getLogger(__name__)
STATUS_LABELS = {"unlabeled": "待炼", "prelabeled": "预炼", "verified": "精炼", "discarded": "废渣"}
STATUS_COLORS = {"unlabeled": "grey", "prelabeled": "orange", "verified": "positive", "discarded": "negative"}


def _notify_error(action: str, exc: Exception) -> None:
    LOGGER.exception("%s failed", action, exc_info=exc)
    ui.notify(f"{action}失败：{exc}", type="negative", close_button=True)


def _project_picker(current_id: str | None = None) -> None:
    options = {project["id"]: project["name"] for project in list_projects()}

    def switch_project(event) -> None:
        if event.value:
            ui.navigate.to(f"/project/{event.value}")

    ui.select(options, value=current_id, label="当前项目", on_change=switch_project).classes("min-w-56")


def _new_project_dialog() -> None:
    with ui.dialog() as dialog, ui.card().classes("w-[34rem] max-w-full p-6 gap-4"):
        ui.label("创建炼数项目").classes("text-xl font-bold")
        name = ui.input("项目名称").classes("w-full")
        description = ui.textarea("项目描述").classes("w-full")
        classes = ui.textarea("类别（每行一个或用逗号分隔）", placeholder="scratch\ncrack").classes("w-full")

        def submit() -> None:
            raw = str(classes.value or "").replace(",", "\n")
            try:
                project = create_project(str(name.value or ""), str(description.value or ""), raw.splitlines())
            except Exception as exc:
                _notify_error("创建项目", exc)
                return
            dialog.close()
            ui.notify("项目创建成功", type="positive")
            ui.navigate.to(f"/project/{project['id']}")

        with ui.row().classes("w-full justify-end"):
            ui.button("取消", on_click=dialog.close).props("flat")
            ui.button("创建项目", on_click=submit)
    ui.button("新建项目", icon="add", on_click=dialog.open)


def _empty_index() -> None:
    with page_shell("数据大厅"):
        with ui.row().classes("w-full items-center"):
            with ui.column().classes("gap-0"):
                ui.label("数据大厅").classes("text-3xl font-bold text-slate-900")
                ui.label("管理视觉数据原石，逐步完成预炼与精炼。").classes("text-slate-500")
            ui.space()
            _project_picker()
            _new_project_dialog()
        with ui.card().classes("w-full border border-dashed border-slate-300 p-12 items-center shadow-none"):
            ui.icon("inventory_2", size="52px").classes("text-teal-600")
            ui.label("还没有炼数项目").classes("text-xl font-semibold")
            ui.label("先定义项目类别，再导入图片。").classes("text-slate-500")


def _project_dataset(project_id: str) -> None:
    try:
        project = load_project(project_id)
    except ProjectError as exc:
        with page_shell("项目不可用"):
            ui.label("无法打开项目").classes("text-2xl font-bold")
            ui.label(str(exc)).classes("text-red-600")
            ui.button("返回数据大厅", on_click=lambda: ui.navigate.to("/"))
        return

    selected: set[str] = set()
    filters = {"search": "", "status": "all", "sort": "newest"}

    with page_shell("数据大厅", project_id):
        with ui.row().classes("w-full items-center"):
            with ui.column().classes("gap-0"):
                ui.label(project["name"]).classes("text-3xl font-bold text-slate-900")
                ui.label(project.get("description") or "暂无项目描述").classes("text-slate-500")
            ui.space()
            _project_picker(project_id)
            _new_project_dialog()

        @ui.refreshable
        def summary_cards() -> None:
            values = stats(project_id)
            cards = [
                ("数据总量", "total", "inventory_2", "text-slate-700"),
                ("待炼", "unlabeled", "hourglass_empty", "text-slate-500"),
                ("预炼", "prelabeled", "auto_awesome", "text-amber-600"),
                ("精炼", "verified", "verified", "text-emerald-600"),
                ("废渣", "discarded", "delete_sweep", "text-rose-600"),
            ]
            with ui.grid(columns=5).classes("w-full gap-4"):
                for label, key, icon, color in cards:
                    status_value = "all" if key == "total" else key

                    def apply_status(value=status_value) -> None:
                        filters["status"] = value
                        status_select.value = value
                        image_grid.refresh()

                    with ui.card().classes("cursor-pointer shadow-sm p-4").on("click", apply_status):
                        with ui.row().classes("items-center"):
                            ui.icon(icon).classes(color)
                            ui.label(label).classes("text-slate-500")
                        ui.label(str(values[key])).classes("text-3xl font-bold")

        async def upload_image(event: UploadEventArguments) -> None:
            try:
                add_image_bytes(project_id, event.file.name, await event.file.read())
                ui.notify(f"已导入 {event.file.name}", type="positive")
                summary_cards.refresh()
                image_grid.refresh()
            except Exception as exc:
                _notify_error("导入图片", exc)

        def batch_discard() -> None:
            for image_id in list(selected):
                set_image_status(project_id, image_id, "discarded")
            selected.clear()
            summary_cards.refresh()
            image_grid.refresh()
            ui.notify("所选图片已标记为废渣")

        async def batch_prelabel() -> None:
            if not selected:
                ui.notify("请先选择需要预炼的图片。", type="warning")
                return
            ui.notify(f"正在预炼 {len(selected)} 张图片，CPU 模式可能需要一些时间…", type="ongoing")
            completed = 0
            try:
                for target_id in list(selected):
                    await run.io_bound(prelabel_image, project_id, target_id)
                    completed += 1
                selected.clear()
                summary_cards.refresh()
                image_grid.refresh()
                ui.notify(f"已完成 {completed} 张图片的 AI 预炼", type="positive")
            except Exception as exc:
                _notify_error(f"批量 AI 预炼（已完成 {completed} 张）", exc)

        with ui.dialog() as delete_dialog, ui.card().classes("p-6"):
            ui.label("确认删除所选图片？").classes("text-lg font-bold")
            ui.label("图片、缩略图和对应标注将一并删除，此操作不可撤销。").classes("text-slate-500")

            def confirm_delete() -> None:
                for image_id in list(selected):
                    delete_image(project_id, image_id)
                selected.clear()
                delete_dialog.close()
                summary_cards.refresh()
                image_grid.refresh()
                ui.notify("所选图片已删除", type="positive")

            with ui.row().classes("justify-end w-full"):
                ui.button("取消", on_click=delete_dialog.close).props("flat")
                ui.button("确认删除", on_click=confirm_delete, color="negative")

        summary_cards()

        with ui.card().classes("w-full p-4 shadow-sm"):
            with ui.row().classes("w-full items-center gap-3"):
                ui.upload(label="导入图片", on_upload=upload_image, multiple=True, auto_upload=True).props(
                    'accept=".jpg,.jpeg,.png,.bmp,.webp" flat color=primary'
                ).classes("max-w-xs")
                ui.button(
                    "AI 批量预炼",
                    icon="auto_awesome",
                    on_click=batch_prelabel,
                ).props("outline" if project.get("active_model") else "outline disable")
                ui.button("标记废渣", icon="delete_sweep", on_click=batch_discard).props("flat")
                ui.button("删除", icon="delete", color="negative", on_click=delete_dialog.open).props("flat")
                ui.space()

                def search_changed(event) -> None:
                    filters["search"] = event.value or ""
                    image_grid.refresh()

                ui.input("搜索文件名", on_change=search_changed).props("clearable debounce=300").classes("w-56")

                def status_changed(event) -> None:
                    filters["status"] = event.value
                    image_grid.refresh()

                status_select = ui.select(
                    {"all": "全部状态", **STATUS_LABELS}, value="all", on_change=status_changed
                ).classes("w-36")

                def sort_changed(event) -> None:
                    filters["sort"] = event.value
                    image_grid.refresh()

                ui.select(
                    {"newest": "最新导入", "oldest": "最早导入", "filename": "文件名"},
                    value="newest",
                    on_change=sort_changed,
                ).classes("w-36")

        @ui.refreshable
        def image_grid() -> None:
            records = list_images(project_id, search=filters["search"], status=filters["status"], sort_by=filters["sort"])
            if not records:
                with ui.card().classes("w-full p-12 items-center shadow-none border border-dashed border-slate-300"):
                    ui.icon("photo_library", size="48px").classes("text-slate-400")
                    ui.label("当前筛选下没有图片").classes("text-slate-500")
                return
            with ui.grid(columns=4).classes("w-full gap-4"):
                for record in records:
                    image_id = record["id"]
                    with ui.card().classes("p-0 overflow-hidden shadow-sm hover:shadow-md"):
                        ui.image(thumbnail_url(project_id, image_id)).classes("w-full h-44 object-cover cursor-pointer").on(
                            "click", lambda _, iid=image_id: ui.navigate.to(f"/annotate/{project_id}/{iid}")
                        )
                        with ui.column().classes("w-full p-3 gap-2"):
                            with ui.row().classes("w-full items-center no-wrap"):
                                def selection_changed(event, iid=image_id) -> None:
                                    selected.add(iid) if event.value else selected.discard(iid)

                                ui.checkbox(value=image_id in selected, on_change=selection_changed)
                                ui.label(record["filename"]).classes("font-medium truncate grow")
                                ui.badge(STATUS_LABELS[record["status"]], color=STATUS_COLORS[record["status"]])
                            ui.label(f"{record['width']}×{record['height']} · {record['annotation_count']} 个目标").classes(
                                "text-xs text-slate-500"
                            )
                            if record["status"] == "discarded":
                                def restore(iid=image_id) -> None:
                                    set_image_status(project_id, iid, "unlabeled")
                                    summary_cards.refresh()
                                    image_grid.refresh()

                                ui.button("恢复为待炼", on_click=restore).props("flat dense")

        image_grid()


def register_dataset_pages() -> None:
    @ui.page("/")
    def index_page() -> None:
        projects = list_projects()
        if projects:
            ui.navigate.to(f"/project/{projects[0]['id']}")
            return
        _empty_index()

    @ui.page("/project/{project_id}")
    def project_page(project_id: str) -> None:
        _project_dataset(project_id)
