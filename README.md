# 炼数 DataForge V1.0

本地运行的目标检测数据管理、Bounding Box 标注、AI 辅助预标注、Ultralytics YOLO 训练与资产导出工具。

## 启动

使用 Python 3.11 创建环境并安装依赖：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python app.py
```

如果已经有可用的 Python 环境，也可以直接在该环境中运行以上安装和启动命令。CPU/GPU 版 PyTorch 的安装方式不同；NVIDIA GPU 用户应先按照 PyTorch 官网选择适合本机驱动的 CUDA 安装命令，再安装本项目依赖。

默认访问 `http://127.0.0.1:8080`。如果 8080 已被占用，应用会自动选择之后的可用端口，并在终端显示实际地址。也可以通过 `DATAFORGE_PORT` 指定首选端口。

## 使用顺序

1. 在数据大厅创建项目并定义类别。
2. 导入图片，在炼数工作台画框并确认 Verified。
3. 在模型熔炉导入一个 Ultralytics `.pt` 基础权重，设置 CPU 训练参数并开始训练。
4. 训练成功后，`model_vNNN` 自动成为当前模型，可用于 AI 预炼。
5. 在结果导出页生成 YOLO Dataset ZIP、模型 ZIP 和 HTML 训练报告。

运行测试：

```powershell
python -m pytest -q
```

## 本地数据

所有项目资产保存在 `storage/projects/proj_xxxxxxxx/`。应用不使用数据库，不上传项目图片。训练由独立 Python 子进程执行，同一时间最多运行一个训练任务。
