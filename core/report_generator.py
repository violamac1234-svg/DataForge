from __future__ import annotations

import html
from pathlib import Path
from typing import Any

import plotly.graph_objects as go

from core.export_manager import ExportError, _timestamp, _unique_dir
from core.json_store import read_json, write_json_atomic
from core.metrics_parser import parse_metrics
from core.model_manager import list_models
from core.project_manager import get_project_dir, load_project, now_iso


def _display(value: Any, digits: int = 4) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return html.escape(str(value))


def generate_training_report(project_id: str, model_id: str) -> dict[str, Any]:
    project = load_project(project_id)
    model = next((item for item in list_models(project_id) if item["id"] == model_id), None)
    if model is None:
        raise ExportError("所选模型不存在。")
    model_dir = get_project_dir(project_id) / "models" / model_id
    rows = parse_metrics(model_dir / "results.csv")
    manifest = read_json(get_project_dir(project_id) / "datasets" / model["dataset_snapshot"] / "manifest.json", {})
    stamp = _timestamp()
    output = _unique_dir(get_project_dir(project_id) / "exports", f"report_{model_id}_{stamp}")

    charts = "<p class='empty'>没有可用的 results.csv 曲线数据。</p>"
    if rows:
        epochs = [row["epoch"] for row in rows]
        loss = go.Figure()
        loss.add_trace(go.Scatter(x=epochs, y=[row["box_loss"] for row in rows], name="Box Loss"))
        loss.add_trace(go.Scatter(x=epochs, y=[row["cls_loss"] for row in rows], name="Cls Loss"))
        loss.update_layout(title="Loss 曲线", template="plotly_white", height=360)
        quality = go.Figure()
        for label, key in (("mAP50", "map50"), ("mAP50-95", "map5095"), ("Precision", "precision"), ("Recall", "recall")):
            quality.add_trace(go.Scatter(x=epochs, y=[row[key] for row in rows], name=label))
        quality.update_layout(title="检测质量指标", template="plotly_white", height=380, yaxis_range=[0, 1])
        charts = loss.to_html(full_html=False, include_plotlyjs="inline") + quality.to_html(full_html=False, include_plotlyjs=False)

    metrics = model.get("metrics", {})
    config = model.get("training_config", {})
    classes = "".join(f"<li><span>{item['id']}</span>{html.escape(item['name'])}</li>" for item in project["classes"])
    report_html = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(project['name'])} · {model_id} 训练报告</title>
<style>
body{{margin:0;background:#f1f5f9;color:#0f172a;font:15px/1.6 system-ui,"Microsoft YaHei",sans-serif}}main{{max-width:1120px;margin:auto;padding:42px 24px}}
.hero{{background:linear-gradient(135deg,#0f172a,#134e4a);color:white;border-radius:20px;padding:34px}}.eyebrow{{color:#5eead4;letter-spacing:.14em;font-size:12px}}
h1{{margin:8px 0}}.muted{{color:#94a3b8}}.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin:20px 0}}.card{{background:white;border-radius:14px;padding:20px;box-shadow:0 3px 18px #0f172a0d}}
.metric{{font-size:26px;font-weight:750}}table{{width:100%;border-collapse:collapse}}td{{padding:10px;border-bottom:1px solid #e2e8f0}}td:first-child{{color:#64748b;width:42%}}ul{{list-style:none;padding:0}}li{{padding:7px 0}}li span{{display:inline-block;width:28px;color:#0f766e;font-weight:bold}}.empty{{color:#64748b}}</style></head>
<body><main><section class="hero"><div class="eyebrow">炼数 DATAFORGE V1.0</div><h1>{html.escape(project['name'])}</h1><div>{model['name']} · 训练报告</div><div class="muted">生成时间：{now_iso()}</div></section>
<section class="grid"><div class="card"><div>mAP50</div><div class="metric">{_display(metrics.get('map50'))}</div></div><div class="card"><div>mAP50-95</div><div class="metric">{_display(metrics.get('map5095'))}</div></div><div class="card"><div>Precision</div><div class="metric">{_display(metrics.get('precision'))}</div></div><div class="card"><div>Recall</div><div class="metric">{_display(metrics.get('recall'))}</div></div></section>
<section class="card"><h2>训练与数据</h2><table><tr><td>模型版本</td><td>{model_id}</td></tr><tr><td>基础模型</td><td>{_display(model.get('base_model'))}</td></tr><tr><td>Epoch</td><td>{_display(config.get('epochs'))}</td></tr><tr><td>Batch</td><td>{_display(config.get('batch'))}</td></tr><tr><td>Image Size</td><td>{_display(config.get('imgsz'))}</td></tr><tr><td>Device</td><td>{_display(config.get('device'))}</td></tr><tr><td>Train Ratio</td><td>{_display(config.get('train_ratio'))}</td></tr><tr><td>Train 图片</td><td>{len(manifest.get('train_images', []))}</td></tr><tr><td>Validation 图片</td><td>{len(manifest.get('val_images', []))}</td></tr><tr><td>负样本</td><td>{_display(manifest.get('negative_images', 0))}</td></tr></table></section>
<section class="card" style="margin-top:20px"><h2>训练曲线</h2>{charts}</section><section class="card" style="margin-top:20px"><h2>类别</h2><ul>{classes}</ul></section>
</main></body></html>"""
    report_path = output / "training_report.html"
    report_path.write_text(report_html, encoding="utf-8")
    record = {
        "schema_version": 1,
        "id": f"export_{stamp}_report",
        "type": "report",
        "model_id": model_id,
        "created_at": now_iso(),
        "artifact": report_path.name,
        "sha256": None,
        "directory": output.name,
    }
    write_json_atomic(output / "export.json", record)
    return {**record, "report_path": str(report_path.resolve()), "output_dir": str(output.resolve())}
