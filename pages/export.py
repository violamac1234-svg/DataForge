from __future__ import annotations

import logging
import os

from nicegui import run, ui

from core.dataset_builder import dataset_summary
from core.export_manager import export_dataset, export_history, export_model
from core.model_manager import list_models
from core.project_manager import get_project_dir, load_project
from core.report_generator import generate_training_report
from pages.layout import page_shell


LOGGER = logging.getLogger(__name__)


def _open_directory(path: str) -> None:
    if os.name == "nt":
        os.startfile(path)  # type: ignore[attr-defined]
    else:
        import subprocess

        subprocess.Popen(["xdg-open", path])


def _export_page(project_id: str) -> None:
    project = load_project(project_id)
    summary = dataset_summary(project_id)
    models = list_models(project_id)

    with page_shell("结果导出", project_id):
        with ui.row().classes("w-full items-center"):
            with ui.column().classes("gap-0"):
                ui.label("结果导出").classes("text-3xl font-bold")
                ui.label("打包 Verified 数据、模型与可校验资产。").classes("text-slate-500")
            ui.space()
            ui.button("打开导出目录", icon="folder_open", on_click=lambda: _open_directory(str(get_project_dir(project_id) / "exports"))).props("outline")

        with ui.grid(columns=3).classes("w-full gap-4"):
            for label, value in (("Verified 图片", summary["verified_images"]), ("目标实例", summary["object_count"]), ("可用模型", len(models))):
                with ui.card().classes("p-5"):
                    ui.label(label).classes("text-slate-500")
                    ui.label(str(value)).classes("text-3xl font-bold")

        async def do_dataset_export() -> None:
            try:
                record = await run.io_bound(export_dataset, project_id)
                ui.notify(f"数据集已导出，SHA-256：{record['sha256']}", type="positive", multi_line=True, close_button=True)
                history_panel.refresh()
            except Exception as exc:
                LOGGER.exception("Dataset export failed", exc_info=exc)
                ui.notify(f"数据集导出失败：{exc}", type="negative", close_button=True)

        model_options = {model["id"]: model["name"] for model in models}
        with ui.grid(columns=3).classes("w-full gap-5"):
            with ui.card().classes("p-5 gap-3"):
                ui.icon("dataset", size="36px").classes("text-teal-600")
                ui.label("YOLO Detection Dataset").classes("text-xl font-bold")
                ui.label("仅包含人工确认的 Verified 数据，含空标签负样本。").classes("text-slate-500")
                ui.button("导出数据集 ZIP", on_click=do_dataset_export).props("outline")
            with ui.card().classes("p-5 gap-3"):
                ui.icon("memory", size="36px").classes("text-indigo-600")
                ui.label("PyTorch 模型").classes("text-xl font-bold")
                model_select = ui.select(model_options, value=project.get("active_model"), label="选择模型").classes("w-full")

                async def do_model_export() -> None:
                    if not model_select.value:
                        ui.notify("当前没有可导出的模型。", type="warning")
                        return
                    try:
                        record = await run.io_bound(export_model, project_id, model_select.value)
                        ui.notify(f"模型已导出，SHA-256：{record['sha256']}", type="positive", multi_line=True, close_button=True)
                        history_panel.refresh()
                    except Exception as exc:
                        LOGGER.exception("Model export failed", exc_info=exc)
                        ui.notify(f"模型导出失败：{exc}", type="negative", close_button=True)

                ui.button("导出模型 ZIP", on_click=do_model_export).props("outline")
            with ui.card().classes("p-5 gap-3"):
                ui.icon("analytics", size="36px").classes("text-amber-600")
                ui.label("HTML 训练报告").classes("text-xl font-bold")
                ui.label("生成含真实训练参数、指标与 Plotly 曲线的离线报告。").classes("text-slate-500")
                report_model = ui.select(model_options, value=project.get("active_model"), label="选择模型").classes("w-full")

                async def do_report() -> None:
                    if not report_model.value:
                        ui.notify("当前没有可生成报告的模型。", type="warning")
                        return
                    try:
                        record = await run.io_bound(generate_training_report, project_id, report_model.value)
                        ui.notify(f"报告已生成：{record['report_path']}", type="positive", close_button=True)
                        history_panel.refresh()
                    except Exception as exc:
                        LOGGER.exception("Report generation failed", exc_info=exc)
                        ui.notify(f"报告生成失败：{exc}", type="negative", close_button=True)

                ui.button("生成 HTML 报告", on_click=do_report).props("outline")

        @ui.refreshable
        def history_panel() -> None:
            ui.label("最近导出").classes("text-xl font-bold mt-4")
            history = export_history(project_id)
            if not history:
                ui.label("还没有导出记录。").classes("text-slate-500")
                return
            with ui.column().classes("w-full gap-2"):
                for record in history:
                    with ui.card().classes("w-full p-4"):
                        with ui.row().classes("w-full items-center"):
                            ui.badge({"dataset": "数据集", "model": "模型", "report": "报告"}.get(record["type"], record["type"]))
                            ui.label(record["artifact"]).classes("font-medium")
                            ui.space()
                            ui.label(record["created_at"]).classes("text-xs text-slate-400")
                        ui.label(f"SHA-256  {record['sha256']}").classes("text-xs font-mono text-slate-500")

        history_panel()


def register_export_pages() -> None:
    @ui.page("/export/{project_id}")
    def export_page(project_id: str) -> None:
        try:
            _export_page(project_id)
        except Exception as exc:
            LOGGER.exception("Open export page failed", exc_info=exc)
            with page_shell("结果导出", project_id):
                ui.label("结果导出页无法打开").classes("text-2xl font-bold")
                ui.label(str(exc)).classes("text-red-600")
