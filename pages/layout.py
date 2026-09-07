from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from nicegui import ui

from config import APP_NAME


@contextmanager
def page_shell(title: str, project_id: str | None = None, *, immersive: bool = False) -> Iterator[None]:
    """Render the shared application chrome."""
    ui.colors(primary="#0F766E", secondary="#334155", accent="#F59E0B")
    drawer = ui.left_drawer(value=not immersive).classes("bg-slate-900 text-slate-100")
    with drawer:
        ui.label("DATAFORGE").classes("text-xs tracking-widest text-teal-400 px-3 py-4")
        target = f"/project/{project_id}" if project_id else "/"
        ui.link("数据大厅", target).classes("block px-3 py-2 text-white")
        if project_id:
            ui.link("炼数工作台", f"/annotate/{project_id}").classes("block px-3 py-2 text-white")
            ui.link("模型熔炉", f"/training/{project_id}").classes("block px-3 py-2 text-white")
            ui.link("结果导出", f"/export/{project_id}").classes("block px-3 py-2 text-white")

    with ui.header().classes("items-center bg-slate-950 text-white px-6"):
        if immersive:
            ui.button(icon="menu", on_click=drawer.toggle).props("flat round color=white").tooltip("打开导航")
        ui.label(APP_NAME).classes("text-lg font-bold")
        ui.space()
        ui.label(title).classes("text-sm text-slate-300")
        ui.badge("本地运行", color="positive")

    content_classes = (
        "w-full h-[calc(100vh-106px)] p-3 gap-2 overflow-hidden"
        if immersive
        else "w-full max-w-7xl mx-auto p-6 gap-5"
    )
    with ui.column().classes(content_classes):
        yield
