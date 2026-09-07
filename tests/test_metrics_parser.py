from core.metrics_parser import parse_metrics


def test_ultralytics_metric_columns_and_non_finite_values(tmp_path):
    csv = tmp_path / "results.csv"
    csv.write_text(
        "epoch, train/box_loss, train/cls_loss, metrics/precision(B), metrics/recall(B), metrics/mAP50(B), metrics/mAP50-95(B)\n"
        "0,0.5,0.4,0.8,0.7,0.75,nan\n"
        "1,0.3,0.2,0.9,0.85,0.88,0.6\n",
        encoding="utf-8",
    )
    rows = parse_metrics(csv)
    assert rows[0]["epoch"] == 1
    assert rows[0]["map5095"] is None
    assert rows[-1]["precision"] == 0.9
    assert rows[-1]["map50"] == 0.88
