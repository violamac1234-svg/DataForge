from __future__ import annotations

import logging
from pathlib import Path

import plotly.graph_objects as go
from nicegui import run, ui
from nicegui.events import UploadEventArguments

from config import DEFAULT_BATCH, DEFAULT_EPOCHS, DEFAULT_IMGSZ, DEFAULT_TRAIN_RATIO, PRETRAINED_DIR
from core.dataset_builder import dataset_summary
from core.metrics_parser import parse_metrics
from core.model_manager import activate_model, list_models
from core.project_manager import load_project
from core.training_manager import (
    available_base_models,
    list_jobs,
    refresh_job,
    start_training,
    stop_training,
    tail_log,
)
from pages.layout import page_shell


LOGGER = logging.getLogger(__name__)
STATUS_NAMES = {
    "idle": "空闲",
    "preparing": "准备中",
    "running": "训练中",
    "completed": "已完成",
    "failed": "失败",
    "stopped": "已停止",
}


def _training_page(project_id: str) -> None:
    summary = dataset_summary(project_id)
    state: dict[str, str | None] = {"job_id": list_jobs(project_id)[0]["id"] if list_jobs(project_id) else None}

    with page_shell("模型熔炉", project_id):
        with ui.row().classes("w-full items-center"):
            with ui.column().classes("gap-0"):
                ui.label("模型熔炉").classes("text-3xl font-bold")
                ui.label("使用 Verified 数据快照训练本地 YOLO 模型。CPU 训练耗时取决于数据量与参数。").classes("text-slate-500")
            ui.space()
            ui.button("返回数据大厅", on_click=lambda: ui.navigate.to(f"/project/{project_id}")).props("flat")

        with ui.grid(columns=3).classes("w-full gap-4"):
            for label, value, icon in (
                ("Verified 图片", summary["verified_images"], "verified"),
                ("目标实例", summary["object_count"], "category"),
                ("负样本", summary["negative_images"], "filter_none"),
            ):
                with ui.card().classes("p-5"):
                    ui.icon(icon).classes("text-teal-600")
                    ui.label(label).classes("text-slate-500")
                    ui.label(str(value)).classes("text-3xl font-bold")

        if summary["invalid"]:
            ui.label("存在非法 Verified 数据：" + "；".join(summary["invalid"])).classes("text-red-600")

        with ui.grid(columns=2).classes("w-full gap-5"):
            with ui.card().classes("w-full p-5 gap-4"):
                ui.label("训练配置").classes("text-xl font-bold")
                model_select = ui.select(available_base_models(project_id), label="Base Model").classes("w-full")

                async def upload_weight(event: UploadEventArguments) -> None:
                    name = Path(event.file.name).name
                    if Path(name).suffix.lower() != ".pt":
                        ui.notify("基础权重必须是 .pt 文件。", type="negative")
                        return
                    target = PRETRAINED_DIR / name
                    await event.file.save(target)
                    model_select.options = available_base_models(project_id)
                    model_select.value = str(target.resolve())
                    model_select.update()
                    ui.notify(f"已加入基础权重：{name}", type="positive")

                ui.upload(label="导入本地 .pt 基础权重", on_upload=upload_weight, auto_upload=True).props('accept=".pt" flat')
                epochs = ui.number("Epoch", value=DEFAULT_EPOCHS, min=1, step=1).classes("w-full")
                batch = ui.number("Batch Size", value=DEFAULT_BATCH, min=1, step=1).classes("w-full")
                imgsz = ui.number("Image Size", value=DEFAULT_IMGSZ, min=32, step=32).classes("w-full")
                device = ui.select({"auto": "Auto（本机为 CPU）", "cpu": "CPU"}, value="auto", label="Device").classes("w-full")
                train_ratio = ui.number("Train Ratio", value=DEFAULT_TRAIN_RATIO, min=0.1, max=0.9, step=0.05).classes("w-full")

                async def start() -> None:
                    if not model_select.value:
                        ui.notify("请先选择或导入基础权重。", type="warning")
                        return
                    try:
                        job = await run.io_bound(
                            start_training,
                            project_id,
                            base_model=model_select.value,
                            epochs=int(epochs.value),
                            batch=int(batch.value),
                            imgsz=int(imgsz.value),
                            device=device.value,
                            train_ratio=float(train_ratio.value),
                        )
                        state["job_id"] = job["id"]
                        status_panel.refresh()
                        ui.notify("训练子进程已启动", type="positive")
                    except Exception as exc:
                        LOGGER.exception("Start training failed", exc_info=exc)
                        ui.notify(f"启动训练失败：{exc}", type="negative", close_button=True)

                ui.button("开始训练", icon="local_fire_department", on_click=start).classes("w-full")

            @ui.refreshable
            def status_panel() -> None:
                job_id = state["job_id"]
                with ui.card().classes("w-full p-5 gap-3"):
                    ui.label("训练状态").classes("text-xl font-bold")
                    if not job_id:
                        ui.label("尚无训练任务").classes("text-slate-500")
                        return
                    job = refresh_job(project_id, job_id)
                    ui.badge(STATUS_NAMES.get(job["status"], job["status"]), color="positive" if job["status"] == "completed" else "primary")
                    progress = min(1.0, job.get("current_epoch", 0) / max(1, job["epochs"]))
                    ui.linear_progress(progress, show_value=False).classes("w-full")
                    ui.label(f"Epoch {job.get('current_epoch', 0)} / {job['epochs']}")
                    if job.get("error"):
                        ui.label(job["error"]).classes("text-red-600")
                    results_csv = Path(job["dataset_snapshot"]).parents[1] / "training_jobs" / job_id / "run" / "results.csv"
                    metrics = parse_metrics(results_csv)
                    if metrics:
                        latest = metrics[-1]
                        with ui.grid(columns=4).classes("w-full gap-2"):
                            for label, key in (("Box Loss", "box_loss"), ("mAP50", "map50"), ("Precision", "precision"), ("Recall", "recall")):
                                value = latest.get(key)
                                with ui.card().classes("p-3 shadow-none bg-slate-50"):
                                    ui.label(label).classes("text-xs text-slate-500")
                                    ui.label("—" if value is None else f"{value:.4f}").classes("font-bold")
                        epochs_axis = [row["epoch"] for row in metrics]
                        loss = go.Figure()
                        loss.add_trace(go.Scatter(x=epochs_axis, y=[row["box_loss"] for row in metrics], name="Box Loss"))
                        loss.add_trace(go.Scatter(x=epochs_axis, y=[row["cls_loss"] for row in metrics], name="Cls Loss"))
                        loss.update_layout(title="Loss", height=260, margin=dict(l=35, r=15, t=45, b=30), template="plotly_white")
                        ui.plotly(loss).classes("w-full")
                        quality = go.Figure()
                        for label, key in (("mAP50", "map50"), ("mAP50-95", "map5095"), ("Precision", "precision"), ("Recall", "recall")):
                            quality.add_trace(go.Scatter(x=epochs_axis, y=[row[key] for row in metrics], name=label))
                        quality.update_layout(title="质量指标", height=280, margin=dict(l=35, r=15, t=45, b=30), template="plotly_white", yaxis_range=[0, 1])
                        ui.plotly(quality).classes("w-full")
                    if job["status"] == "running":
                        async def stop() -> None:
                            try:
                                await run.io_bound(stop_training, project_id, job_id)
                                status_panel.refresh()
                                ui.notify("训练已停止")
                            except Exception as exc:
                                ui.notify(f"停止失败：{exc}", type="negative")

                        ui.button("停止训练", icon="stop", color="negative", on_click=stop).props("outline")
                    ui.label("训练日志（最后 160 行）").classes("font-semibold mt-3")
                    ui.code(tail_log(project_id, job_id) or "等待训练输出…", language="text").classes("w-full max-h-80 overflow-auto text-xs")

            status_panel()

        def poll() -> None:
            if state["job_id"]:
                status_panel.refresh()

        ui.timer(2.0, poll)

        @ui.refreshable
        def model_history() -> None:
            project = load_project(project_id)
            models = list_models(project_id)
            ui.label("模型历史").classes("text-xl font-bold mt-4")
            if not models:
                ui.label("训练成功后，模型版本会出现在这里。").classes("text-slate-500")
                return
            with ui.grid(columns=3).classes("w-full gap-4"):
                for model in models:
                    active = project.get("active_model") == model["id"]
                    with ui.card().classes("p-4"):
                        with ui.row().classes("items-center w-full"):
                            ui.label(model["name"]).classes("font-bold")
                            ui.space()
                            if active:
                                ui.badge("当前模型", color="positive")
                        metrics = model.get("metrics", {})
                        ui.label(f"mAP50: {metrics.get('map50') if metrics.get('map50') is not None else '—'}").classes("text-sm text-slate-500")
                        ui.label(model.get("created_at") or "").classes("text-xs text-slate-400")
                        if not active:
                            def make_active(mid=model["id"]) -> None:
                                activate_model(project_id, mid)
                                model_history.refresh()
                                ui.notify(f"已切换到 {mid}", type="positive")

                            ui.button("设为当前模型", on_click=make_active).props("flat dense")

        model_history()


def register_training_pages() -> None:
    @ui.page("/training/{project_id}")
    def training_page(project_id: str) -> None:
        try:
            _training_page(project_id)
        except Exception as exc:
            LOGGER.exception("Open training page failed", exc_info=exc)
            with page_shell("模型熔炉", project_id):
                ui.label("模型熔炉无法打开").classes("text-2xl font-bold")
                ui.label(str(exc)).classes("text-red-600")
