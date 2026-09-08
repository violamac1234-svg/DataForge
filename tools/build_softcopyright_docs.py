from __future__ import annotations

import ast
import io
import math
import re
import textwrap
import tokenize
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_LINE_SPACING, WD_TAB_ALIGNMENT, WD_TAB_LEADER
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "softcopyright"
ASSETS = OUT / "assets"
SOFTWARE_NAME = "炼数 DataForge V1.0"


def set_run_font(run, latin: str, east_asia: str, size: float, bold: bool = False, color: str = "000000"):
    run.font.name = latin
    run._element.get_or_add_rPr().rFonts.set(qn("w:ascii"), latin)
    run._element.get_or_add_rPr().rFonts.set(qn("w:hAnsi"), latin)
    run._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), east_asia)
    run.font.size = Pt(size)
    run.bold = bold
    run.font.color.rgb = RGBColor.from_string(color)


def add_page_field(paragraph):
    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = paragraph.add_run("第 ")
    set_run_font(run, "Arial", "宋体", 9)
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    display = OxmlElement("w:t")
    display.text = "1"
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    for element in (begin, instr, separate, display, end):
        run._r.append(element)
    tail = paragraph.add_run(" 页")
    set_run_font(tail, "Arial", "宋体", 9)


def configure_page(section, *, code: bool = False):
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin = Inches(0.62 if code else 0.68)
    section.bottom_margin = Inches(0.58 if code else 0.65)
    section.left_margin = Inches(0.55 if code else 0.78)
    section.right_margin = Inches(0.55 if code else 0.78)
    section.header_distance = Inches(0.23)
    section.footer_distance = Inches(0.25)
    header = section.header
    hp = header.paragraphs[0]
    hp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    hp.paragraph_format.space_after = Pt(0)
    run = hp.add_run(SOFTWARE_NAME)
    set_run_font(run, "Arial", "宋体", 9, bold=True)
    footer = section.footer
    fp = footer.paragraphs[0]
    add_page_field(fp)


def set_cell_shading(cell, fill: str):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def set_table_borders(table, color: str = "D9D9D9"):
    tbl_pr = table._tbl.tblPr
    borders = tbl_pr.first_child_found_in("w:tblBorders")
    if borders is None:
        borders = OxmlElement("w:tblBorders")
        tbl_pr.append(borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        element = borders.find(qn(f"w:{edge}"))
        if element is None:
            element = OxmlElement(f"w:{edge}")
            borders.append(element)
        element.set(qn("w:val"), "single")
        element.set(qn("w:sz"), "4")
        element.set(qn("w:color"), color)


def set_cell_margins(cell, top=90, start=110, bottom=90, end=110):
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    tc_mar = tc_pr.first_child_found_in("w:tcMar")
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    for tag, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = tc_mar.find(qn(f"w:{tag}"))
        if node is None:
            node = OxmlElement(f"w:{tag}")
            tc_mar.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def style_doc(doc: Document):
    styles = doc.styles
    normal = styles["Normal"]
    normal.font.name = "Arial"
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
    normal.font.size = Pt(10.5)
    normal.font.color.rgb = RGBColor(0, 0, 0)
    for name, size in (("Title", 25), ("Heading 1", 17), ("Heading 2", 13)):
        style = styles[name]
        style.font.name = "Arial"
        style._element.rPr.rFonts.set(qn("w:eastAsia"), "黑体")
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = RGBColor(0, 0, 0)
    styles["Title"].paragraph_format.space_after = Pt(16)
    styles["Heading 1"].paragraph_format.space_before = Pt(0)
    styles["Heading 1"].paragraph_format.space_after = Pt(9)
    styles["Heading 2"].paragraph_format.space_before = Pt(7)
    styles["Heading 2"].paragraph_format.space_after = Pt(5)


def python_source_without_comments(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    docstring_lines: set[int] = set()
    try:
        tree = ast.parse(text)
        for node in ast.walk(tree):
            body = getattr(node, "body", None)
            if body and isinstance(body, list):
                first = body[0]
                if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                    docstring_lines.update(range(first.lineno, (first.end_lineno or first.lineno) + 1))
    except SyntaxError:
        pass
    tokens = []
    try:
        for token in tokenize.generate_tokens(io.StringIO(text).readline):
            if token.type == tokenize.COMMENT:
                continue
            tokens.append(token)
        text = tokenize.untokenize(tokens)
    except tokenize.TokenError:
        pass
    lines = []
    for number, line in enumerate(text.splitlines(), 1):
        if number in docstring_lines:
            continue
        stripped = line.rstrip()
        if stripped.strip():
            lines.append(stripped)
    return lines


def script_source_without_comments(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return [line.rstrip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("//")]


def wrap_source_line(line: str, width: int = 118) -> list[str]:
    if len(line) <= width:
        return [line]
    indent = re.match(r"\s*", line).group(0)
    wrapped = textwrap.wrap(
        line,
        width=width,
        subsequent_indent=indent + "    ",
        break_long_words=True,
        break_on_hyphens=False,
        replace_whitespace=False,
        drop_whitespace=False,
    )
    return [part.rstrip() for part in wrapped if part.strip()]


def collect_source_lines() -> list[str]:
    order = [
        "config.py",
        "core/json_store.py",
        "core/project_manager.py",
        "core/image_manager.py",
        "core/annotation_manager.py",
        "core/dataset_builder.py",
        "core/metrics_parser.py",
        "core/training_worker.py",
        "core/training_manager.py",
        "core/model_manager.py",
        "core/predictor.py",
        "core/export_manager.py",
        "core/report_generator.py",
        "pages/layout.py",
        "pages/dataset.py",
        "pages/annotation.py",
        "pages/training.py",
        "pages/export.py",
        "static/annotation.js",
        "static/annotation.css",
        "app.py",
        "launcher.py",
    ]
    lines: list[str] = []
    for rel in order:
        path = ROOT / rel
        raw = python_source_without_comments(path) if path.suffix == ".py" else script_source_without_comments(path)
        for line in raw:
            lines.extend(wrap_source_line(line))
    remainder = len(lines) % 50
    additions = (50 - remainder) % 50
    for _ in range(additions):
        candidates = [(len(line), i) for i, line in enumerate(lines[:-2]) if len(line) >= 36]
        if not candidates:
            raise RuntimeError("Unable to balance source pages")
        _, index = max(candidates)
        line = lines[index]
        split_at = min((pos for pos in range(len(line) // 2, len(line)) if line[pos] in " ,;)]}"), default=len(line) // 2)
        left = line[: split_at + 1].rstrip()
        right = line[split_at + 1 :].lstrip()
        indent = re.match(r"\s*", line).group(0) + "    "
        lines[index:index + 1] = [left, indent + right]
    assert len(lines) % 50 == 0
    assert lines[-1].strip() == "main()"
    return lines


def build_source_doc() -> Path:
    lines = collect_source_lines()
    doc = Document()
    configure_page(doc.sections[0], code=True)
    style_doc(doc)
    normal = doc.styles["Normal"]
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.space_after = Pt(0)
    normal.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    normal.paragraph_format.line_spacing = Pt(9.55)
    for index, line in enumerate(lines):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        p.paragraph_format.line_spacing = Pt(9.55)
        run = p.add_run(line)
        size = 6.4 if len(line) <= 118 else max(5.2, 6.4 * 118 / len(line))
        set_run_font(run, "Courier New", "等线", size)
        if (index + 1) % 50 == 0 and index + 1 < len(lines):
            run.add_break(WD_BREAK.PAGE)
    core = doc.core_properties
    core.title = f"{SOFTWARE_NAME} 源代码示例文件"
    core.subject = "计算机软件著作权登记源程序材料"
    core.author = "DataForge"
    path = OUT / "炼数DataForge_V1.0_源代码示例文件.docx"
    doc.save(path)
    (OUT / "source_manifest.txt").write_text(
        f"display_lines={len(lines)}\npages={len(lines)//50}\nlines_per_page=50\nlast_line={lines[-1]}\n",
        encoding="utf-8",
    )
    return path


def add_title(doc: Document, text: str, subtitle: str | None = None):
    p = doc.add_paragraph(style="Title")
    if getattr(doc, "_dataforge_page_break", False):
        p.paragraph_format.page_break_before = True
        doc._dataforge_page_break = False
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    run = p.add_run(text)
    set_run_font(run, "Arial", "黑体", 25, bold=True)
    if subtitle:
        sp = doc.add_paragraph()
        sp.paragraph_format.space_after = Pt(10)
        sr = sp.add_run(subtitle)
        set_run_font(sr, "Arial", "宋体", 11, color="475569")


def add_heading(doc: Document, text: str, level: int = 1):
    p = doc.add_paragraph(style=f"Heading {level}")
    run = p.add_run(text)
    set_run_font(run, "Arial", "黑体", 17 if level == 1 else 13, bold=True)
    return p


def add_body(doc: Document, text: str, *, bold_lead: str | None = None):
    p = doc.add_paragraph()
    p.paragraph_format.first_line_indent = Pt(21)
    p.paragraph_format.line_spacing = 1.25
    p.paragraph_format.space_after = Pt(4)
    if bold_lead and text.startswith(bold_lead):
        r1 = p.add_run(bold_lead)
        set_run_font(r1, "Arial", "宋体", 10.5, bold=True)
        r2 = p.add_run(text[len(bold_lead):])
        set_run_font(r2, "Arial", "宋体", 10.5)
    else:
        run = p.add_run(text)
        set_run_font(run, "Arial", "宋体", 10.5)
    return p


def add_steps(doc: Document, steps: list[str], *, compact: bool = False):
    for i, text in enumerate(steps, 1):
        p = doc.add_paragraph()
        p.paragraph_format.left_indent = Pt(8)
        p.paragraph_format.first_line_indent = Pt(-8)
        p.paragraph_format.space_after = Pt(0 if compact else 4)
        if compact:
            p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
            p.paragraph_format.line_spacing = Pt(10.8)
        else:
            p.paragraph_format.line_spacing = 1.2
        run = p.add_run(f"{i:02d}  {text}")
        set_run_font(run, "Arial", "宋体", 8.5 if compact else 10.2)


def add_table(doc: Document, headers: list[str], rows: list[list[str]], widths: list[float] | None = None):
    table = doc.add_table(rows=1, cols=len(headers))
    table.autofit = False
    set_table_borders(table)
    for i, header in enumerate(headers):
        cell = table.rows[0].cells[i]
        set_cell_shading(cell, "0F3B4C")
        set_cell_margins(cell)
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        if widths:
            cell.width = Inches(widths[i])
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(header)
        set_run_font(r, "Arial", "黑体", 9.5, bold=True, color="FFFFFF")
    for ri, row in enumerate(rows):
        cells = table.add_row().cells
        for ci, value in enumerate(row):
            cell = cells[ci]
            set_cell_margins(cell)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            if widths:
                cell.width = Inches(widths[ci])
            if ri % 2:
                set_cell_shading(cell, "F2F7F8")
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER if ci == 0 else WD_ALIGN_PARAGRAPH.LEFT
            r = p.add_run(str(value))
            set_run_font(r, "Arial", "宋体", 9.2)
    doc.add_paragraph().paragraph_format.space_after = Pt(0)
    return table


def add_figure(doc: Document, filename: str, caption: str, width: float = 6.75):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(3)
    p.add_run().add_picture(str(ASSETS / filename), width=Inches(width))
    cp = doc.add_paragraph()
    cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cp.paragraph_format.space_after = Pt(7)
    r = cp.add_run(caption)
    set_run_font(r, "Arial", "宋体", 9, color="475569")


def add_toc(doc: Document, entries: list[tuple[str, int]]):
    intro = doc.add_paragraph()
    intro.paragraph_format.space_after = Pt(12)
    run = intro.add_run("本目录页码按当前V1.0用户手册正文编排。")
    set_run_font(run, "Arial", "宋体", 10.5, color="475569")
    for title, page in entries:
        p = doc.add_paragraph()
        p.paragraph_format.left_indent = Pt(10)
        p.paragraph_format.right_indent = Pt(10)
        p.paragraph_format.space_after = Pt(8)
        p.paragraph_format.tab_stops.add_tab_stop(Inches(6.2), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS)
        r1 = p.add_run(title)
        set_run_font(r1, "Arial", "宋体", 11)
        r2 = p.add_run(f"\t{page}")
        set_run_font(r2, "Arial", "宋体", 11)


def page_break(doc: Document):
    doc._dataforge_page_break = True


def build_manual_doc() -> Path:
    doc = Document()
    configure_page(doc.sections[0], code=False)
    style_doc(doc)

    add_title(doc, "炼数 DataForge V1.0 用户手册", "目标检测数据管理 标注 训练与导出")
    add_body(doc, "本手册说明炼数 DataForge V1.0 的安装、启动、项目管理、图片标注、AI预标注、模型训练、版本管理和成果导出方法。操作人员按照数据大厅、炼数工作台、模型熔炉、结果导出的顺序，即可完成目标检测数据与模型的本地闭环管理。")
    add_figure(doc, "01_data_hall.png", "图1  炼数 DataForge V1.0 数据大厅", 6.65)
    add_table(doc, ["文档项目", "内容"], [["软件名称", SOFTWARE_NAME], ["文档名称", "用户手册"], ["适用版本", "V1.0"], ["运行方式", "Windows本地运行 浏览器访问"]], [1.45, 5.1])

    page_break(doc)
    add_title(doc, "目录")
    add_toc(doc, [
        ("1 软件概述", 3),
        ("2 安装与运行环境", 5),
        ("3 启动与界面导航", 6),
        ("4 项目创建与类别设置", 7),
        ("5 图片导入与数据管理", 8),
        ("6 批量操作与数据检查", 9),
        ("7 炼数工作台", 10),
        ("8 人工标注操作", 11),
        ("9 AI预标注与人工复核", 12),
        ("10 训练数据准备", 13),
        ("11 模型训练", 14),
        ("12 训练监控与模型版本", 15),
        ("13 结果导出", 16),
        ("14 导出操作与文件说明", 17),
        ("15 本地数据与目录结构", 18),
        ("16 常见问题与操作检查", 20),
    ])

    page_break(doc)
    add_title(doc, "1 软件概述")
    add_heading(doc, "1 1 产品定位")
    add_body(doc, "炼数 DataForge 是面向目标检测任务的本地数据与模型工作台。系统将项目建档、图片导入、目标框标注、AI预标注、YOLO训练、模型版本和成果导出放在同一操作界面中。")
    add_heading(doc, "1 2 主要用户")
    add_steps(doc, [
        "数据标注人员负责导入图片、绘制目标框并确认标注结果。",
        "算法工程人员负责准备基础权重、设置训练参数并查看指标。",
        "项目管理人员负责检查数据状态、模型版本和导出记录。",
        "单机用户可在无数据库条件下保存项目数据和训练资产。",
        "使用者应了解目标检测类别和矩形框标注的基本含义。",
    ])
    add_heading(doc, "1 3 功能流程")
    add_table(doc, ["阶段", "输入", "主要操作", "输出"], [
        ["项目准备", "项目名称和类别", "创建项目并定义类别", "项目目录"],
        ["数据整理", "原始图片", "导入 筛选 状态管理", "图片清单"],
        ["人工标注", "项目图片", "绘框 调整 分类 确认", "标注文件"],
        ["模型训练", "已确认数据和权重", "划分数据并训练", "模型版本"],
        ["成果交付", "数据 模型 指标", "打包并生成报告", "ZIP和HTML"],
    ], [0.9, 1.55, 2.45, 1.65])
    add_body(doc, "系统默认仅在本机127.0.0.1地址提供服务。项目图片、标注、训练任务、模型和导出文件保存在软件目录下的storage文件夹中，软件不要求连接数据库。")
    add_figure(doc, "01_data_hall.png", "图2  软件功能入口与项目数据概览", 3.85)

    page_break(doc)
    add_title(doc, "2 安装与运行环境")
    add_heading(doc, "2 1 推荐配置")
    add_table(doc, ["项目", "建议配置"], [
        ["处理器", "x86-64多核处理器"], ["内存", "8GB及以上 建议16GB以上"],
        ["存储", "至少10GB可用空间 数据集和模型空间另计"], ["操作系统", "Windows 10或Windows 11 64位"],
        ["Python", "Python 3.11"], ["浏览器", "Microsoft Edge Chrome等现代浏览器"],
    ], [1.35, 5.2])
    add_heading(doc, "2 2 安装步骤")
    add_steps(doc, [
        "确认计算机已安装Python 3.11并可从命令行调用。",
        "将软件目录完整复制到本机具有读写权限的位置。",
        "打开PowerShell并进入炼数DataForge软件目录。",
        "执行python -m venv .venv创建独立虚拟环境。",
        "执行.venv\\Scripts\\Activate.ps1激活虚拟环境。",
        "执行python -m pip install --upgrade pip升级安装工具。",
        "执行pip install -r requirements.txt安装运行依赖。",
        "使用NVIDIA显卡时按PyTorch环境要求安装相应版本。",
        "CPU环境可直接使用依赖文件中安装的PyTorch版本。",
        "确认storage、storage/projects和logs目录具有写权限。",
        "将Ultralytics基础权重放入storage/pretrained目录。",
        "基础权重文件扩展名应为.pt，例如yolo11n.pt。",
        "执行python launcher.py --check检查核心依赖与端口。",
        "检查结果应显示Python、NiceGUI和Ultralytics版本。",
        "如8080端口被占用，系统会在后续端口中自动选择。",
        "也可通过DATAFORGE_PORT环境变量指定首选端口。",
        "Windows用户可编辑launch_dataforge.cmd中的解释器路径。",
        "保存启动脚本后可双击该文件启动软件。",
        "启动窗口必须保持打开，关闭窗口会停止本地服务。",
        "浏览器无法打开时，应先查看启动窗口和logs/app.log。",
        "不要删除正在使用的storage目录或其中的项目文件。",
        "升级软件前建议完整备份storage目录。",
        "项目图片较多时，应预留额外磁盘空间存放缩略图。",
        "训练过程还会生成数据快照、日志和中间权重文件。",
        "模型训练时间取决于图片数量、图像尺寸和训练轮次。",
        "V1.0训练设备选项支持Auto和CPU。",
        "导出压缩包会保存在对应项目的exports目录。",
        "首次启动后应先创建测试项目验证读写权限。",
        "测试完成后再导入正式项目数据。",
        "环境检查无误后进入下一章完成软件启动。",
    ], compact=True)

    page_break(doc)
    add_title(doc, "3 启动与界面导航")
    add_heading(doc, "3 1 启动软件")
    add_body(doc, "在已配置环境中运行python app.py，或双击launch_dataforge.cmd。启动成功后，终端显示本地访问地址，启动器会在服务就绪后打开默认浏览器。默认地址为http://127.0.0.1:8080。")
    add_figure(doc, "01_data_hall.png", "图2  软件启动后的数据大厅", 6.55)
    add_heading(doc, "3 2 导航区域")
    add_table(doc, ["导航项", "用途"], [["数据大厅", "项目切换 图片导入 数据状态与筛选"], ["炼数工作台", "人工框选 AI预标注 标注复核"], ["模型熔炉", "数据检查 训练配置 进度指标 模型历史"], ["结果导出", "数据集 模型 训练报告与导出记录"]], [1.45, 5.1])
    add_body(doc, "页面右上角显示本地运行标记，用于提示当前界面连接的是本机服务。打开其他项目时，左侧导航会自动带入当前项目编号。")

    page_break(doc)
    add_title(doc, "4 项目创建与类别设置")
    add_heading(doc, "4 1 创建项目")
    add_steps(doc, [
        "打开数据大厅并单击右上角的新建项目按钮。",
        "在项目名称框中输入能够区分任务的名称。",
        "项目名称不能为空，建议包含检测对象或业务简称。",
        "在项目描述中填写数据来源、用途或验收范围。",
        "在类别输入框中逐行填写目标检测类别。",
        "也可以使用英文逗号分隔多个类别名称。",
        "系统会清除类别名称前后的多余空格。",
        "同一项目中的类别名称不得重复。",
        "类别按输入顺序从编号0开始生成。",
        "不同类别会获得不同的显示颜色。",
        "确认名称和类别无误后单击创建项目。",
        "创建成功后系统进入该项目的数据大厅。",
        "项目基本信息保存在项目目录的project.json。",
        "每个项目使用独立目录存放图片和训练资产。",
        "项目编号由系统生成，用户无需手工修改。",
        "创建后应立即检查页面标题是否为目标项目。",
        "顶部当前项目下拉框可切换到其他项目。",
        "切换项目前应先保存正在编辑的标注。",
        "类别定义应在大量标注开始前完成确认。",
        "V1.0界面不提供已建类别的批量重排功能。",
        "不要直接编辑JSON文件改变已经使用的类别编号。",
        "类别编号变化会导致既有标注与模型含义不一致。",
        "测试项目和正式项目建议使用不同名称。",
        "项目描述可记录标注规则版本和负责人信息。",
        "项目数据不会自动上传到外部服务器。",
        "复制项目时应复制完整项目目录而非单个JSON文件。",
        "恢复备份后重新启动软件以重新读取项目列表。",
        "无法创建项目时检查名称、类别和目录写权限。",
        "创建完成后进入图片导入和数据管理流程。",
        "正式作业前应由项目负责人确认类别定义。",
    ], compact=True)

    page_break(doc)
    add_title(doc, "5 图片导入与数据管理")
    add_figure(doc, "01_data_hall.png", "图3  图片导入 筛选与状态统计区域", 6.55)
    add_heading(doc, "5 1 导入图片")
    add_body(doc, "单击导入图片区域选择一个或多个文件。系统支持JPG、JPEG、PNG、BMP和WebP格式。导入时软件校验文件内容、读取宽高、计算文件哈希、生成内部文件名和缩略图；内容完全相同的图片不会重复加入项目。")
    add_heading(doc, "5 2 状态与筛选")
    add_table(doc, ["状态", "含义", "建议处理"], [["待炼", "尚未完成人工确认", "进入标注工作台处理"], ["预炼", "已有AI候选框", "人工复核后确认"], ["精炼", "已经人工确认", "用于训练和导出"], ["废渣", "不参与后续流程", "必要时恢复为待炼"]], [1.05, 2.3, 3.2])
    add_body(doc, "数据卡片显示总量及各状态数量。单击状态卡片或使用状态下拉框可以筛选图片；搜索框按文件名查找；排序下拉框支持最新导入、最早导入和文件名顺序。")

    page_break(doc)
    add_title(doc, "6 批量操作与数据检查")
    add_steps(doc, [
        "在图片卡片左侧勾选框中选择需要处理的图片。",
        "选择结果仅在当前页面会话中保存。",
        "批量预炼前必须确认项目已经设置当前模型。",
        "未配置当前模型时AI批量预炼按钮不可用。",
        "批量预炼会按选中顺序逐张执行本地推理。",
        "CPU推理速度受图片尺寸和模型大小影响。",
        "预炼完成后图片状态更新为预炼。",
        "AI预测可能存在漏检、误检和框选偏差。",
        "预炼结果必须进入炼数工作台进行人工复核。",
        "单击标记废渣可将选中图片排除在训练之外。",
        "废渣图片仍保留在项目目录并可恢复为待炼。",
        "单击删除会打开确认对话框。",
        "确认删除后原图、缩略图和对应标注一并删除。",
        "删除操作不可从软件界面撤销。",
        "删除正式数据前应确认已有独立备份。",
        "图片卡片显示原始文件名、尺寸和目标数量。",
        "单击图片缩略图可进入对应标注页面。",
        "目标数量来源于该图片当前保存的标注文件。",
        "已存在标注但未确认的图片仍可能显示待炼状态。",
        "只有精炼状态图片可以进入训练数据集。",
        "只有精炼状态图片会进入数据集导出。",
        "精炼图片允许包含零个目标并作为负样本。",
        "训练数据不能全部为零目标负样本。",
        "正式训练前应检查类别样本数量是否合理。",
        "搜索筛选不会修改图片本身或标注内容。",
        "排序只改变界面显示顺序。",
        "批量操作完成后统计卡片会自动刷新。",
        "异常提示出现时记录文件名并查看应用日志。",
        "数据整理完成后进入炼数工作台开始标注。",
        "建议按小批量导入、标注和抽检，降低返工成本。",
    ], compact=True)

    page_break(doc)
    add_title(doc, "7 炼数工作台")
    add_figure(doc, "02_annotation_workbench.png", "图4  目标框标注与对象检查界面", 6.55)
    add_heading(doc, "7 1 工作区组成")
    add_table(doc, ["区域", "功能"], [["顶部操作区", "返回 AI预炼 保存草稿 确认下一张"], ["左侧图片队列", "切换图片并查看处理状态"], ["中部画布", "显示图片 绘制 选择 移动与调整目标框"], ["右侧检查器", "查看对象列表 修改目标类别"], ["底部状态栏", "显示状态 目标数和保存状态"]], [1.55, 5.0])
    add_body(doc, "打开工作台后应等待图片和目标框加载完成。已保存的目标框显示类别名称和类别颜色；AI生成的框还可以显示置信度与是否经过人工修正。")

    page_break(doc)
    add_title(doc, "8 人工标注操作")
    add_steps(doc, [
        "在顶部工具栏单击B矩形框进入画框模式。",
        "也可按键盘B键快速进入画框模式。",
        "在目标左上角按下鼠标并拖动到目标右下角。",
        "松开鼠标后系统生成一个新的目标框。",
        "宽度或高度过小的框会被自动忽略。",
        "新建目标框默认使用第一个类别。",
        "按V键或单击V选择进入选择模式。",
        "单击目标框可以选中该标注对象。",
        "选中对象后目标框显示八个调整手柄。",
        "拖动目标框内部可以整体移动标注位置。",
        "拖动边或角上的手柄可以调整框的范围。",
        "目标框坐标被限制在图片有效区域内。",
        "右侧对象列表与画布中的目标框保持同步。",
        "单击对象列表中的记录也可以选中对应目标框。",
        "使用目标类别下拉框修改选中对象类别。",
        "类别编号1至9可通过数字键快速选择。",
        "按Delete键可以删除当前选中的目标框。",
        "也可单击工具栏中的Delete删除按钮。",
        "删除后应检查目标数量是否按预期减少。",
        "单击显示置信度可切换AI结果置信度显示。",
        "手工创建的标注不显示AI置信度。",
        "移动或改类后的AI框会标记为已人工修正。",
        "页面底部未保存提示表示当前内容已经改变。",
        "按Ctrl加S或单击保存草稿保存当前标注。",
        "草稿保存不会自动将图片标记为精炼。",
        "完成复核后单击确认并加载下一张。",
        "确认操作将图片状态设置为精炼。",
        "确认后系统自动打开队列中的下一张图片。",
        "存在未保存修改时切换图片会弹出提示。",
        "可选择取消、放弃修改或保存并切换。",
    ], compact=True)

    page_break(doc)
    add_title(doc, "9 AI预标注与人工复核")
    add_heading(doc, "9 1 使用条件")
    add_body(doc, "AI预标注需要项目存在可用模型并已将其中一个模型设置为当前模型。当前模型权重位于项目models目录，软件使用Ultralytics在本机CPU上执行预测。")
    add_steps(doc, [
        "进入需要预标注的图片页面。",
        "确认页面不存在未保存的人工修改。",
        "单击顶部AI预炼按钮或按P键。",
        "软件读取当前项目设置的活动模型。",
        "软件加载对应模型目录中的best.pt权重。",
        "推理按照系统配置的置信度阈值过滤结果。",
        "预测框坐标转换为零到一之间的归一化坐标。",
        "预测类别保存为项目类别编号。",
        "预测置信度与标注来源一并写入标注文件。",
        "推理完成后页面重新载入预测结果。",
        "图片状态更新为预炼。",
        "单击显示置信度检查每个预测框的分数。",
        "低置信度目标会使用醒目样式提示。",
        "逐个确认预测框是否覆盖完整目标。",
        "拖动位置不准确的预测框。",
        "调整过大或过小的预测框边界。",
        "删除误检目标框。",
        "为漏检目标补充人工目标框。",
        "检查预测类别是否与实际目标一致。",
        "使用类别下拉框纠正错误类别。",
        "保存草稿后可继续检查同一图片。",
        "确认结果前再次核对对象总数。",
        "单击确认并加载下一张完成当前图片。",
        "批量AI预炼可在数据大厅对多张图片执行。",
        "批量预炼结束后仍需逐张人工复核。",
        "模型输出为空时允许保留零目标结果。",
        "零目标图片经人工确认后作为负样本。",
        "模型或图片异常时页面会显示推理失败原因。",
        "必要时返回模型熔炉更换当前模型。",
        "所有复核完成后进入训练数据准备。",
    ], compact=True)

    page_break(doc)
    add_title(doc, "10 训练数据准备")
    add_steps(doc, [
        "打开模型熔炉查看Verified图片和目标实例数量。",
        "Verified图片数量对应已经人工确认的图片。",
        "目标实例数量是有效标注对象的总数。",
        "负样本表示已确认但没有目标框的图片。",
        "训练前系统逐张加载Verified图片及其标注。",
        "系统检查原始图片文件是否存在。",
        "系统检查标注文件结构和图片编号。",
        "系统验证目标框包含四个有效坐标值。",
        "坐标必须在零到一的归一化范围内。",
        "目标框右下角必须位于左上角之后。",
        "类别编号必须存在于当前项目类别列表。",
        "发现非法标注时训练页会列出对应图片。",
        "应返回标注工作台修正错误后再训练。",
        "没有Verified图片时不能创建训练数据集。",
        "所有Verified图片均为负样本时不能训练。",
        "系统按Train Ratio划分训练集和验证集。",
        "默认训练比例为百分之八十。",
        "数据划分使用固定随机种子以便复现。",
        "只有一张图片时验证集可能为空。",
        "系统为每次训练建立独立数据快照。",
        "快照目录以训练任务编号命名。",
        "训练与验证图片分别复制到images子目录。",
        "标注转换为YOLO中心点宽高格式。",
        "空目标图片会生成空标签文件。",
        "data.yaml记录数据路径和类别名称映射。",
        "manifest.json记录划分、类别数量和负样本数量。",
        "训练开始后修改项目标注不会改变当前快照。",
        "新的训练任务会重新生成新的数据快照。",
        "正式训练前建议备份已确认数据。",
        "数据检查通过后设置模型训练参数。",
    ], compact=True)

    page_break(doc)
    add_title(doc, "11 模型训练")
    add_figure(doc, "03_training.png", "图5  训练配置 进度 指标和曲线", 6.55)
    add_heading(doc, "11 1 参数说明")
    add_table(doc, ["参数", "说明"], [["Base Model", "storage/pretrained中的基础权重或当前模型"], ["Epoch", "训练轮次 范围1至10000"], ["Batch Size", "单批图片数量 范围1至1024"], ["Image Size", "训练输入尺寸 范围32至4096"], ["Device", "V1.0支持Auto和CPU"], ["Train Ratio", "训练集占比 必须大于0且小于1"]], [1.35, 5.2])
    add_body(doc, "设置参数后单击开始训练。软件先创建数据快照，再启动独立Python子进程执行Ultralytics训练。同一时间最多运行一个训练任务。")

    page_break(doc)
    add_title(doc, "12 训练监控与模型版本")
    add_steps(doc, [
        "训练启动后状态从准备中变为运行中。",
        "训练进度显示当前Epoch与总Epoch。",
        "系统定期读取results.csv更新进度。",
        "Box Loss反映目标框回归误差。",
        "mAP50显示IoU阈值0.5下的平均精度。",
        "Precision表示预测结果中的正确比例。",
        "Recall表示真实目标被检出的比例。",
        "指标为空时界面使用短横线显示。",
        "训练曲线根据已有轮次结果动态更新。",
        "日志区域显示最近一百六十行训练输出。",
        "CPU训练耗时与数据量和参数直接相关。",
        "浏览器关闭不会主动终止训练子进程。",
        "应用主进程关闭可能影响任务状态刷新。",
        "需要中止时单击停止训练。",
        "停止操作先请求训练进程正常退出。",
        "超时未退出时系统会终止该进程。",
        "停止后的任务状态记录为已停止。",
        "训练异常时任务状态记录为失败。",
        "失败信息写入任务记录和worker_result.json。",
        "训练成功必须生成run/weights/best.pt。",
        "成功后系统创建递增编号的模型版本。",
        "首个版本编号通常为model_v001。",
        "模型目录保存best.pt和可选last.pt。",
        "模型目录还保存训练指标和model.json。",
        "模型历史区域列出版本名称和创建时间。",
        "模型历史显示mAP50等关键质量信息。",
        "新训练成功的模型自动成为当前模型。",
        "也可在模型历史中手工设置当前模型。",
        "当前模型用于后续单张和批量AI预标注。",
        "确认模型状态后可进入结果导出页面。",
    ], compact=True)

    page_break(doc)
    add_title(doc, "13 结果导出")
    add_figure(doc, "04_export.png", "图6  数据集 模型和训练报告导出界面", 6.55)
    add_heading(doc, "13 1 可导出成果")
    add_table(doc, ["成果", "内容"], [["YOLO数据集", "Verified图片 标签 data.yaml 清单与说明"], ["PyTorch模型", "best.pt model.json 指标和说明"], ["HTML训练报告", "训练参数 数据概况 指标与Plotly曲线"]], [1.55, 5.0])
    add_body(doc, "页面顶部显示可导出的已确认图片、目标实例和模型数量。每次导出均建立独立目录并记录导出时间；ZIP成果同时生成SHA-256校验文件。")

    page_break(doc)
    add_title(doc, "14 导出操作与文件说明")
    add_steps(doc, [
        "打开结果导出页面检查顶部统计数据。",
        "确认Verified图片数量符合交付范围。",
        "确认目标实例数量与标注抽检结果一致。",
        "导出数据集前至少需要一张Verified图片。",
        "单击导出数据集ZIP开始生成数据包。",
        "数据包仅包含Verified状态图片。",
        "图片复制到导出目录的images文件夹。",
        "标签写入labels文件夹并与图片同名。",
        "每行标签包含类别和归一化框坐标。",
        "零目标负样本对应空标签文件。",
        "data.yaml记录数据路径和类别映射。",
        "manifest.json记录图片数、目标数和类别。",
        "README.txt记录软件、项目和导出范围。",
        "导出目录随后压缩为ZIP文件。",
        "同名导出目录存在时系统自动增加序号。",
        "模型导出前在下拉框中选择模型版本。",
        "单击导出模型ZIP复制best.pt和模型信息。",
        "存在results.csv时同时导出metrics.csv。",
        "模型包README说明模型格式和版本。",
        "训练报告导出前选择需要报告的模型。",
        "单击生成HTML报告创建离线网页。",
        "报告展示mAP、Precision和Recall。",
        "存在训练结果时报告包含Loss和质量曲线。",
        "报告还列出训练参数、数据量和类别。",
        "ZIP完成后系统计算SHA-256摘要。",
        "摘要文件可用于核验压缩包是否被修改。",
        "最近导出区域显示成果名称和时间。",
        "单击打开导出目录可在资源管理器中查看文件。",
        "交付前应解压测试并核对README与清单。",
        "确认成果可用后再复制到正式交付位置。",
    ], compact=True)

    page_break(doc)
    add_title(doc, "15 本地数据与目录结构")
    add_heading(doc, "15 1 主要目录")
    add_table(doc, ["目录", "保存内容"], [["storage/pretrained", "可选的Ultralytics基础权重"], ["storage/projects", "全部项目数据"], ["images", "项目原始图片"], ["thumbnails", "页面显示用缩略图"], ["annotations", "每张图片的标注JSON"], ["datasets", "每次训练冻结的数据快照"], ["training_jobs", "任务配置 日志和训练输出"], ["models", "登记后的模型版本"], ["exports", "数据集 模型和报告成果"], ["logs", "应用运行日志"]], [2.05, 4.5])
    add_heading(doc, "15 2 备份与恢复")
    add_body(doc, "备份时应先停止训练并关闭软件，然后复制完整storage目录。只复制图片而遗漏project.json、images.json或annotations目录会导致项目信息不完整。恢复时将备份目录放回原位置并重新启动软件。")
    add_body(doc, "不得手工修改模型编号、任务编号或内部图片文件名。需要迁移到另一台计算机时，应同时迁移软件代码、依赖说明和storage目录，并重新配置启动脚本中的Python解释器路径。")
    add_figure(doc, "04_export.png", "图7  项目成果与导出记录的集中管理", 3.8)

    page_break(doc)
    add_title(doc, "16 常见问题与操作检查")
    add_steps(doc, [
        "软件无法启动时先运行launcher.py --check。",
        "检查Python版本是否为3.11及依赖是否完整。",
        "端口冲突时查看终端显示的实际访问地址。",
        "页面无法访问时确认启动窗口仍处于运行状态。",
        "图片无法导入时检查扩展名和文件是否损坏。",
        "重复图片未加入项目属于内容哈希去重结果。",
        "缩略图异常时检查项目thumbnails目录写权限。",
        "标注框未显示时等待页面脚本加载后刷新一次。",
        "切换图片前确认底部保存状态为已保存。",
        "AI预炼不可用时检查项目是否存在当前模型。",
        "AI推理失败时检查best.pt与图片文件是否存在。",
        "AI结果为空不表示程序故障，应结合图片判断。",
        "训练按钮不可用时检查基础权重是否放置正确。",
        "训练前确认存在正样本和有效类别。",
        "非法标注提示应返回对应图片重新保存确认。",
        "训练进度缓慢时可减少Epoch或Image Size。",
        "内存不足时可降低Batch Size。",
        "训练失败时查看页面日志和stdout.log。",
        "停止任务后需要重新创建任务才能继续训练。",
        "模型未出现时确认训练生成了best.pt。",
        "导出按钮报错时检查项目exports目录写权限。",
        "数据集为空时确认图片状态已经设置为精炼。",
        "模型导出前确认下拉框已选择有效模型。",
        "报告无曲线时检查模型目录是否有results.csv。",
        "ZIP校验失败时重新导出并避免修改压缩包。",
        "迁移项目前停止软件并复制完整项目目录。",
        "定期备份storage目录和重要导出成果。",
        "不要在训练运行中删除对应任务或数据快照。",
        "正式交付前完成图片、类别、模型和压缩包抽检。",
        "操作结束后关闭启动窗口以停止本地服务。",
    ], compact=True)
    add_heading(doc, "16 1 完成标准")
    add_body(doc, "当全部目标图片完成精炼确认、训练任务生成有效模型版本、目标成果能够正常导出且SHA-256校验一致时，本次DataForge作业流程完成。")

    core = doc.core_properties
    core.title = f"{SOFTWARE_NAME} 用户手册"
    core.subject = "计算机软件著作权登记用户手册材料"
    core.author = "DataForge"
    path = OUT / "炼数DataForge_V1.0_用户手册_含目录.docx"
    doc.save(path)
    return path


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    source = build_source_doc()
    manual = build_manual_doc()
    print(source)
    print(manual)


if __name__ == "__main__":
    main()
