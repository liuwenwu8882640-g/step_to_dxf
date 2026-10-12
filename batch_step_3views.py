# -*- coding: utf-8 -*-
"""
batch_step_3views.py

功能：
1. 启动程序后选择包含 STEP 文件的文件夹；
2. 扫描所选文件夹内的 .stp 和 .step 文件；
3. 每个 STEP 模型单独生成三个正投影视图；
4. 按中国第一角法排列：

       主视图    左视图
       俯视图

5. 三视图保持 1:1，不进行缩放；
6. 每个模型单独导出一个同名 DXF；
7. DXF 输出到 STEP 文件所在的已选择文件夹；
8. 单个模型失败时继续处理后续模型；
9. 输出最终批处理统计结果。

运行命令：

"D:\\FreeCAD\\bin\\freecadcmd.exe" ^
"D:\\Creo2dxf\\batch_step_3views.py"

也支持将文件夹路径作为命令行参数：

"D:\\FreeCAD\\bin\\freecadcmd.exe" ^
"D:\\Creo2dxf\\batch_step_3views.py" ^
"D:\\02_Projects\\Outputs\\2026 Project\\V222201~02\\stp"

说明：
FreeCADCmd.exe 加载脚本后，__name__ 不一定等于 "__main__"，
因此本程序在文件末尾直接调用 main()。
"""

import os
import sys
import traceback
import math


# ============================================================
# 用户配置
# ============================================================

# 是否导出隐藏线。
# 当前建议保持 False，先验证三视图布局和可见线。
EXPORT_HIDDEN_LINES = False

# 最小视图间隔，单位与 STEP 模型一致。
MIN_GAP = 200.0

# 间隔比例。
# Gap = max(MIN_GAP, max(L, W, H) * GAP_RATIO)
GAP_RATIO = 0.1

# 是否覆盖已有的同名 DXF。
OVERWRITE_EXISTING_DXF = True

# 是否扫描子文件夹。
# False：只处理用户选择的文件夹。
# True：递归处理所有子文件夹。
RECURSIVE_SCAN = False

# 支持的 STEP 扩展名。
STEP_EXTENSIONS = (
    ".stp",
    ".step",
)


# ============================================================
# 控制台日志
# ============================================================

def log(message=""):
    """
    输出日志并立即刷新缓冲区。
    """
    print(message, flush=True)


log("脚本已经开始执行。")


# ============================================================
# 导入 FreeCAD 模块
# ============================================================

try:
    log("正在导入 FreeCAD...")
    import FreeCAD as App
    log("FreeCAD 导入成功。")

    log("正在导入 Part...")
    import Part
    log("Part 导入成功。")

    log("正在导入 TechDraw...")
    import TechDraw
    log("TechDraw 导入成功。")

    log("正在导入 importDXF...")
    import importDXF
    log("importDXF 导入成功。")

except Exception as import_error:
    log()
    log("=" * 70)
    log("FreeCAD 模块导入失败")
    log("=" * 70)
    log(str(import_error))
    traceback.print_exc()
    sys.exit(1)


# ============================================================
# 三视图方向
# ============================================================

"""
坐标约定：

X 方向：模型长度 L
Y 方向：模型宽度 W
Z 方向：模型高度 H

当前视图方向：

FRONT：
    从 -Y 方向观察，理论显示 X-Z 平面。

TOP：
    从 -Z 方向观察，理论显示 X-Y 平面。

LEFT：
    从 +X 方向观察，理论显示 Y-Z 平面。

这些方向沿用原六视图脚本中已经使用的定义。

需验证：
STEP 文件自身的全局坐标方向必须与上述约定一致。
如果模型导出时摆放方向不同，程序仍能生成三视图，
但“主视图”可能不是工程上期待的最佳主视方向。
"""

VIEW_DIRECTIONS = {
    "FRONT": App.Vector(0, 1, 0),
    "LEFT": App.Vector(-1, 0, 0),
    "TOP": App.Vector(0, 0, 1),
}

# 三个原始正交投影的生成顺序。
CANDIDATE_VIEW_ORDER = (
    "FRONT",
    "TOP",
    "LEFT",
)

# 各原始投影的基础平面旋转角度。
#
# 这些角度沿用你当前脚本已经实际使用的方向修正：
#
# FRONT：
#     基础投影面为 X-Z，旋转后以 X 为水平、Z 为垂直。
#
# TOP：
#     基础投影面为 X-Y，以 X 为水平、Y 为垂直。
#
# LEFT：
#     基础投影面为 Y-Z，旋转后以 Y 为水平、Z 为垂直。
#
# 注意：
# 这些角度已根据你现有程序设置保留，
# 但 FreeCAD 不同版本或不同 STEP 坐标方向下仍需实测验证。
BASE_VIEW_ROTATIONS = {
    "FRONT": -90.0,
    "TOP": 0,
    "LEFT": 90.0,
}


# ============================================================
# 文件夹选择
# ============================================================

def select_folder():
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()

        try:
            root.attributes("-topmost", True)
        except:
            pass

        root.update()

        folder = filedialog.askdirectory(
            title="请选择包含 PRT/ASM 文件的文件夹",
            mustexist=True
        )

        root.destroy()

        if folder:
            return folder

    except Exception as e:
        print("Tkinter选择失败：", e)

    # 回退方案
    return input("请输入文件夹路径：").strip('"')



def select_folder_with_pyside():
    """
    tkinter 不可用时，尝试使用 PySide 文件夹选择窗口。

    同时兼容较常见的 PySide6 和 PySide2。

    Returns
    -------
    str
        用户选择的文件夹路径。

    Raises
    ------
    Exception
        PySide 不可用或窗口创建失败时抛出异常。
    """
    qt_widgets = None

    try:
        from PySide6 import QtWidgets
        qt_widgets = QtWidgets
    except Exception:
        from PySide2 import QtWidgets
        qt_widgets = QtWidgets

    application = qt_widgets.QApplication.instance()
    created_application = False

    if application is None:
        application = qt_widgets.QApplication(sys.argv)
        created_application = True

    selected_folder = qt_widgets.QFileDialog.getExistingDirectory(
        None,
        "请选择包含 STEP 文件的文件夹",
        "",
        qt_widgets.QFileDialog.ShowDirsOnly,
    )

    if created_application:
        try:
            application.quit()
        except Exception:
            pass

    return selected_folder


def normalize_folder_path(folder_path):
    """
    规范化并验证文件夹路径。
    """
    if folder_path is None:
        return ""

    folder_path = str(folder_path).strip()

    # 允许用户在命令行中输入带引号的路径。
    folder_path = folder_path.strip('"')
    folder_path = folder_path.strip("'")

    if not folder_path:
        return ""

    folder_path = os.path.abspath(
        os.path.normpath(folder_path)
    )

    return folder_path


def select_input_folder():
    """
    获取待处理文件夹。

    获取顺序：
    1. 如果命令行提供了路径，直接采用；
    2. 尝试 tkinter 文件夹窗口；
    3. 尝试 PySide 文件夹窗口；
    4. 最后回退到控制台手动输入。

    Returns
    -------
    str
        有效文件夹路径。
    """
    # --------------------------------------------------------
    # 方式一：命令行参数
    # --------------------------------------------------------

    if len(sys.argv) >= 2:
        command_line_folder = normalize_folder_path(
            sys.argv[1]
        )

        if os.path.isdir(command_line_folder):
            log(
                "使用命令行指定的文件夹："
                f"{command_line_folder}"
            )
            return command_line_folder

        log(
            "警告：命令行参数不是有效文件夹："
            f"{command_line_folder}"
        )

    # --------------------------------------------------------
    # 方式二：tkinter
    # --------------------------------------------------------

    try:
        log("正在打开文件夹选择窗口...")

        selected_folder = select_folder_with_tkinter()
        selected_folder = normalize_folder_path(
            selected_folder
        )

        if selected_folder:
            if not os.path.isdir(selected_folder):
                raise NotADirectoryError(
                    f"选择的路径不是文件夹："
                    f"{selected_folder}"
                )

            return selected_folder

        raise RuntimeError("用户取消了文件夹选择。")

    except Exception as tkinter_error:
        log(
            "tkinter 文件夹选择窗口不可用："
            f"{tkinter_error}"
        )

    # --------------------------------------------------------
    # 方式三：PySide
    # --------------------------------------------------------

    try:
        log("正在尝试使用 PySide 打开文件夹选择窗口...")

        selected_folder = select_folder_with_pyside()
        selected_folder = normalize_folder_path(
            selected_folder
        )

        if selected_folder:
            if not os.path.isdir(selected_folder):
                raise NotADirectoryError(
                    f"选择的路径不是文件夹："
                    f"{selected_folder}"
                )

            return selected_folder

        raise RuntimeError("用户取消了文件夹选择。")

    except Exception as pyside_error:
        log(
            "PySide 文件夹选择窗口不可用："
            f"{pyside_error}"
        )

    # --------------------------------------------------------
    # 方式四：控制台输入
    # --------------------------------------------------------

    log()
    log("图形文件夹选择窗口不可用。")
    log("请在下面输入包含 STEP 文件的完整文件夹路径。")

    try:
        selected_folder = input(
            "STEP 文件夹路径："
        )
    except Exception as input_error:
        raise RuntimeError(
            "无法打开文件夹选择窗口，"
            "也无法从控制台读取文件夹路径。"
            f"\n详细错误：{input_error}"
        )

    selected_folder = normalize_folder_path(
        selected_folder
    )

    if not selected_folder:
        raise RuntimeError(
            "没有选择或输入文件夹。"
        )

    if not os.path.isdir(selected_folder):
        raise NotADirectoryError(
            f"输入的文件夹不存在："
            f"{selected_folder}"
        )

    return selected_folder


# ============================================================
# STEP 文件扫描
# ============================================================

def find_step_files(folder_path):
    """
    查找文件夹中的 STEP 文件。

    Parameters
    ----------
    folder_path : str
        待扫描文件夹。

    Returns
    -------
    list[str]
        STEP 文件完整路径列表。
    """
    step_files = []

    if RECURSIVE_SCAN:
        for current_root, _, file_names in os.walk(
            folder_path
        ):
            for file_name in file_names:
                extension = os.path.splitext(
                    file_name
                )[1].lower()

                if extension in STEP_EXTENSIONS:
                    step_files.append(
                        os.path.join(
                            current_root,
                            file_name,
                        )
                    )
    else:
        for file_name in os.listdir(folder_path):
            full_path = os.path.join(
                folder_path,
                file_name,
            )

            if not os.path.isfile(full_path):
                continue

            extension = os.path.splitext(
                file_name
            )[1].lower()

            if extension in STEP_EXTENSIONS:
                step_files.append(full_path)

    # 忽略大小写排序，使批处理顺序稳定。
    step_files.sort(
        key=lambda path: path.lower()
    )

    return step_files


def get_output_dxf_path(step_file):
    """
    根据 STEP 文件路径生成同名 DXF 路径。

    例如：
        D:\\Models\\part.stp
        ->
        D:\\Models\\part.dxf
    """
    file_root, _ = os.path.splitext(step_file)

    return file_root + ".dxf"


# ============================================================
# Shape 判断和组合
# ============================================================

def is_valid_shape(shape):
    """
    判断 Shape 是否有效并且至少包含一条边。
    """
    if shape is None:
        return False

    try:
        if shape.isNull():
            return False
    except Exception:
        return False

    try:
        return len(shape.Edges) > 0
    except Exception:
        return False


def combine_shapes(shapes):
    """
    将多个有效 Shape 组合成一个 Compound。

    Parameters
    ----------
    shapes : list
        Part.Shape 对象列表。

    Returns
    -------
    Part.Shape or None
        组合后的 Shape。
    """
    valid_shapes = []

    for shape in shapes:
        if is_valid_shape(shape):
            valid_shapes.append(shape.copy())

    if not valid_shapes:
        return None

    if len(valid_shapes) == 1:
        return valid_shapes[0]

    return Part.makeCompound(valid_shapes)


def project_one_view(source_shape, direction):
    """
    对模型进行一个方向的二维正投影。

    返回
    ----
    visible_shape : Part.Shape
        TechDraw.project() 返回的可见边组合。

    hidden_shape : Part.Shape or None
        TechDraw.project() 返回的隐藏边组合。

    重要说明
    --------
    本版本不再调用 TechDraw.findShapeOutline()。

    原因：
    1. TechDraw.project() 已经生成投影边；
    2. 再叠加 findShapeOutline() 可能产生重复轮廓；
    3. 某些圆柱、圆环和复杂曲面可能出现重复边或异常边；
    4. 当前优先修复“重复投影”问题。

    可能的影响：
    某些特殊曲面模型可能缺少少量轮廓线，需通过实际模型验证。
    如果确实出现缺线，应采用边去重方案，而不是直接重新叠加
    findShapeOutline() 的全部结果。
    """
    result = TechDraw.project(
        source_shape,
        direction,
    )

    if not isinstance(result, (list, tuple)):
        raise RuntimeError(
            "TechDraw.project() 没有返回列表或元组。"
        )

    if len(result) < 4:
        raise RuntimeError(
            "TechDraw.project() 返回对象数量不足，"
            f"实际数量为：{len(result)}"
        )

    # 根据你当前 FreeCAD 环境已经验证过的返回结构：
    # result[0]、result[1] 组合为可见投影边；
    # result[2]、result[3] 组合为隐藏投影边。
    #
    # 不再加入 findShapeOutline()，避免轮廓重复。
    visible_shape = combine_shapes([
        result[0],
        result[1],
    ])

    hidden_shape = combine_shapes([
        result[2],
        result[3],
    ])

    if not is_valid_shape(visible_shape):
        raise RuntimeError(
            "TechDraw.project() 没有生成有效可见线。"
        )

    return visible_shape, hidden_shape


def get_shape_size(shape):
    """
    获取投影 Shape 的二维包围盒尺寸。

    Returns
    -------
    width : float
        二维投影 X 方向尺寸。

    height : float
        二维投影 Y 方向尺寸。
    """
    if not is_valid_shape(shape):
        return 0.0, 0.0

    bbox = shape.BoundBox

    width = float(bbox.XLength)
    height = float(bbox.YLength)

    return width, height


# ============================================================
# 模型尺寸和基准点
# ============================================================

def get_model_dimensions(source_shape):
    """
    根据 STEP 模型三维包围盒取得 L、W、H。

    当前约定：

    L = XLength
    W = YLength
    H = ZLength
    """
    bbox = source_shape.BoundBox

    length = float(bbox.XLength)
    width = float(bbox.YLength)
    height = float(bbox.ZLength)

    dimensions = {
        "X / L": length,
        "Y / W": width,
        "Z / H": height,
    }

    for dimension_name, dimension_value in dimensions.items():
        if not math.isfinite(dimension_value):
            raise RuntimeError(
                f"模型 {dimension_name} 尺寸不是有限数值："
                f"{dimension_value}"
            )

        if dimension_value <= 0.0:
            raise RuntimeError(
                f"模型 {dimension_name} 尺寸无效："
                f"{dimension_value}"
            )

    return length, width, height


def get_model_center(shape):
    """
    获取模型三维包围盒中心。
    """
    bbox = shape.BoundBox

    return App.Vector(
        (
            float(bbox.XMin)
            + float(bbox.XMax)
        ) / 2.0,
        (
            float(bbox.YMin)
            + float(bbox.YMax)
        ) / 2.0,
        (
            float(bbox.ZMin)
            + float(bbox.ZMax)
        ) / 2.0,
    )


def make_anchor_marker(
    model_center,
    length,
    width,
    height,
):
    """
    在模型包围盒中心创建三维十字线基准标记。

    标记只用于计算各视图中统一基准点的投影坐标，
    不会导出到最终 DXF。
    """
    max_dimension = max(
        float(length),
        float(width),
        float(height),
    )

    marker_half_length = max(
        1.0,
        max_dimension * 0.01,
    )

    center_x = float(model_center.x)
    center_y = float(model_center.y)
    center_z = float(model_center.z)

    x_axis_line = Part.makeLine(
        App.Vector(
            center_x - marker_half_length,
            center_y,
            center_z,
        ),
        App.Vector(
            center_x + marker_half_length,
            center_y,
            center_z,
        ),
    )

    y_axis_line = Part.makeLine(
        App.Vector(
            center_x,
            center_y - marker_half_length,
            center_z,
        ),
        App.Vector(
            center_x,
            center_y + marker_half_length,
            center_z,
        ),
    )

    z_axis_line = Part.makeLine(
        App.Vector(
            center_x,
            center_y,
            center_z - marker_half_length,
        ),
        App.Vector(
            center_x,
            center_y,
            center_z + marker_half_length,
        ),
    )

    anchor_marker = Part.makeCompound([
        x_axis_line,
        y_axis_line,
        z_axis_line,
    ])

    if anchor_marker.isNull():
        raise RuntimeError(
            "三维十字线基准标记创建失败。"
        )

    if len(anchor_marker.Edges) < 3:
        raise RuntimeError(
            "三维十字线基准标记边数不足，"
            f"实际边数：{len(anchor_marker.Edges)}"
        )

    return anchor_marker


def get_projected_anchor(
    anchor_marker,
    direction,
):
    """
    使用与主模型相同的方向投影三维十字线标记，
    取得统一基准点在二维投影平面中的实际坐标。
    """
    projected = TechDraw.project(
        anchor_marker,
        direction,
    )

    if not isinstance(projected, (list, tuple)):
        raise RuntimeError(
            "基准标记投影没有返回列表或元组。"
        )

    if len(projected) < 4:
        raise RuntimeError(
            "基准标记投影返回对象不足，"
            f"实际数量：{len(projected)}"
        )

    valid_projected_shapes = []

    for projected_shape in projected:
        if is_valid_shape(projected_shape):
            valid_projected_shapes.append(
                projected_shape.copy()
            )

    if not valid_projected_shapes:
        direction_text = (
            f"({float(direction.x):.3f}, "
            f"{float(direction.y):.3f}, "
            f"{float(direction.z):.3f})"
        )

        raise RuntimeError(
            "三维十字线基准标记没有生成有效投影。"
            f"投影方向：{direction_text}"
        )

    if len(valid_projected_shapes) == 1:
        marker_projection = valid_projected_shapes[0]
    else:
        marker_projection = Part.makeCompound(
            valid_projected_shapes
        )

    if not is_valid_shape(marker_projection):
        raise RuntimeError(
            "三维十字线基准标记的组合投影无效。"
        )

    bbox = marker_projection.BoundBox

    anchor_x = (
        float(bbox.XMin)
        + float(bbox.XMax)
    ) / 2.0

    anchor_y = (
        float(bbox.YMin)
        + float(bbox.YMax)
    ) / 2.0

    if not math.isfinite(anchor_x):
        raise RuntimeError(
            f"基准点投影 X 坐标无效：{anchor_x}"
        )

    if not math.isfinite(anchor_y):
        raise RuntimeError(
            f"基准点投影 Y 坐标无效：{anchor_y}"
        )

    return anchor_x, anchor_y

def choose_largest_projected_view(view_data):
    """
    根据各候选投影的二维包围盒面积选择主视图。

    面积计算：
        projected_width * projected_height

    注意：
    这里比较的是投影外接矩形面积，
    不是封闭轮廓的真实几何面积。

    平面积相同时的优先级：
        FRONT > TOP > LEFT

    设置固定优先级可以避免浮点微小误差导致同一模型
    在不同运行中选择不同主视图。

    Returns
    -------
    str
        "FRONT"、"TOP" 或 "LEFT"
    """
    priority_order = (
        "FRONT",
        "TOP",
        "LEFT",
    )

    best_view_name = None
    best_area = -1.0
    area_tolerance = 1.0e-9

    for view_name in priority_order:
        if view_name not in view_data:
            raise RuntimeError(
                f"缺少候选投影数据：{view_name}"
            )

        projected_width, projected_height = (
            view_data[view_name]["projected_size"]
        )

        projected_area = (
            float(projected_width)
            * float(projected_height)
        )

        if not math.isfinite(projected_area):
            raise RuntimeError(
                f"{view_name} 投影面积不是有限数值："
                f"{projected_area}"
            )

        if projected_area <= 0.0:
            raise RuntimeError(
                f"{view_name} 投影面积无效："
                f"{projected_area}"
            )

        view_data[view_name]["projected_area"] = (
            projected_area
        )

        if projected_area > best_area + area_tolerance:
            best_area = projected_area
            best_view_name = view_name

    if best_view_name is None:
        raise RuntimeError(
            "没有找到可作为主视图的有效投影。"
        )

    return best_view_name


def build_view_role_mapping(main_view_name):
    """
    根据被选中的主视图，确定第一角法布局中的三个角色。

    角色定义：
        MAIN：
            面积最大的投影，放在左上方。

        BOTTOM：
            放在 MAIN 下方，与 MAIN 保持水平尺寸方向对齐。

        RIGHT：
            放在 MAIN 右侧，与 MAIN 保持垂直尺寸方向对齐。

    返回值中的 extra_rotation 表示：
        在基础旋转完成后，还需要增加的平面旋转角度。

    注意：
    当前映射基于三个标准投影平面：
        FRONT = X-Z
        TOP   = X-Y
        LEFT  = Y-Z

    FreeCAD 实际输出方向可能受版本和模型坐标系影响，
    因此正负方向仍需要通过一个非对称测试模型验证。
    """
    if main_view_name == "FRONT":
        return {
            "MAIN": {
                "source_view": "FRONT",
                "extra_rotation": 0.0,
            },
            "BOTTOM": {
                "source_view": "TOP",
                "extra_rotation": 0.0,
            },
            "RIGHT": {
                "source_view": "LEFT",
                "extra_rotation": 0.0,
            },
        }

    if main_view_name == "TOP":
        return {
            "MAIN": {
                "source_view": "TOP",
                "extra_rotation": 0.0,
            },
            "BOTTOM": {
                "source_view": "FRONT",
                "extra_rotation": 0.0,
            },
            # TOP 主视图垂直方向为 Y。
            # LEFT 的基础旋转后，Y 位于水平方向，
            # 因此再旋转 90°，让 Y 转到垂直方向。
            "RIGHT": {
                "source_view": "LEFT",
                "extra_rotation": 90.0,
            },
        }

    if main_view_name == "LEFT":
        return {
            "MAIN": {
                "source_view": "LEFT",
                "extra_rotation": 0.0,
            },
            # LEFT 主视图水平方向为 Y。
            # TOP 的基础方向中 Y 为垂直方向，
            # 因此再旋转 90°，让 Y 转到水平方向。
            "BOTTOM": {
                "source_view": "TOP",
                "extra_rotation": 90.0,
            },
            # FRONT 的垂直方向为 Z，
            # 与 LEFT 主视图的垂直方向 Z 一致。
            "RIGHT": {
                "source_view": "FRONT",
                "extra_rotation": 0.0,
            },
        }

    raise RuntimeError(
        f"不支持的主视图名称：{main_view_name}"
    )


def build_role_view_data(
    candidate_view_data,
    role_mapping,
):
    """
    根据角色映射生成最终 MAIN、BOTTOM、RIGHT 投影数据。

    基础投影已经完成 BASE_VIEW_ROTATIONS 中的旋转。
    本函数只处理特定主视图布局所需的额外旋转。

    Returns
    -------
    dict
        键为 MAIN、BOTTOM、RIGHT。
    """
    role_view_data = {}

    for role_name in (
        "MAIN",
        "BOTTOM",
        "RIGHT",
    ):
        mapping = role_mapping[role_name]

        source_view_name = mapping["source_view"]
        extra_rotation = float(
            mapping["extra_rotation"]
        )

        source_data = candidate_view_data[
            source_view_name
        ]

        visible_shape = source_data["visible"].copy()

        hidden_shape = None
        if is_valid_shape(source_data["hidden"]):
            hidden_shape = (
                source_data["hidden"].copy()
            )

        anchor_x, anchor_y = (
            source_data["anchor"]
        )

        if abs(extra_rotation) > 1.0e-9:
            (
                visible_shape,
                hidden_shape,
                anchor_x,
                anchor_y,
            ) = rotate_projected_view(
                visible_shape=visible_shape,
                hidden_shape=hidden_shape,
                anchor_x=anchor_x,
                anchor_y=anchor_y,
                angle_degrees=extra_rotation,
            )

        if not is_valid_shape(visible_shape):
            raise RuntimeError(
                f"{role_name} 角色投影无效，"
                f"来源投影：{source_view_name}"
            )

        projected_width, projected_height = (
            get_shape_size(visible_shape)
        )

        if (
            projected_width <= 0.0
            or projected_height <= 0.0
        ):
            raise RuntimeError(
                f"{role_name} 投影包围盒尺寸无效："
                f"{projected_width} × "
                f"{projected_height}"
            )

        role_view_data[role_name] = {
            "source_view": source_view_name,
            "visible": visible_shape,
            "hidden": hidden_shape,
            "anchor": (
                anchor_x,
                anchor_y,
            ),
            "projected_size": (
                projected_width,
                projected_height,
            ),
            "extra_rotation": extra_rotation,
            "total_rotation": (
                float(
                    source_data["rotation_angle"]
                )
                + extra_rotation
            ),
        }

    return role_view_data

# ============================================================
# 中国第一角法三视图布局
# ============================================================

def build_first_angle_three_view_layout(
    role_view_data,
    gap,
):
    """
    根据三个实际投影包围盒尺寸计算第一角法布局。

    布局：

        MAIN        RIGHT

        BOTTOM

    MAIN 位于原点。

    RIGHT 位于 MAIN 右侧：

        X距离 =
            MAIN宽度 / 2
            + gap
            + RIGHT宽度 / 2

    BOTTOM 位于 MAIN 下方：

        Y距离 =
            MAIN高度 / 2
            + gap
            + BOTTOM高度 / 2

    使用实际投影尺寸的优点：
    1. 主视图可以动态切换；
    2. 不再假设 FRONT 永远是主视图；
    3. 旋转后的视图尺寸也能正确参与布局；
    4. 减少视图重叠或间距过大的情况。
    """
    required_roles = (
        "MAIN",
        "BOTTOM",
        "RIGHT",
    )

    for role_name in required_roles:
        if role_name not in role_view_data:
            raise RuntimeError(
                f"缺少视图角色数据：{role_name}"
            )

    main_width, main_height = (
        role_view_data["MAIN"]["projected_size"]
    )

    bottom_width, bottom_height = (
        role_view_data["BOTTOM"]["projected_size"]
    )

    right_width, right_height = (
        role_view_data["RIGHT"]["projected_size"]
    )

    all_sizes = (
        main_width,
        main_height,
        bottom_width,
        bottom_height,
        right_width,
        right_height,
        gap,
    )

    for value in all_sizes:
        if not math.isfinite(float(value)):
            raise RuntimeError(
                f"布局尺寸包含非有限数值：{value}"
            )

    horizontal_center_distance = (
        float(main_width) / 2.0
        + float(gap)
        + float(right_width) / 2.0
    )

    vertical_center_distance = (
        float(main_height) / 2.0
        + float(gap)
        + float(bottom_height) / 2.0
    )

    positions = {
        "MAIN": (
            0.0,
            0.0,
        ),
        "RIGHT": (
            horizontal_center_distance,
            0.0,
        ),
        "BOTTOM": (
            0.0,
            vertical_center_distance,
        ),
    }

    distances = {
        "horizontal_center_distance": (
            horizontal_center_distance
        ),
        "vertical_center_distance": (
            vertical_center_distance
        ),
    }

    return positions, distances

def rotate_point_2d(
    point_x,
    point_y,
    angle_degrees,
):
    """
    将二维点绕原点旋转。

    Parameters
    ----------
    point_x : float
        旋转前 X 坐标。

    point_y : float
        旋转前 Y 坐标。

    angle_degrees : float
        逆时针为正，顺时针为负。

    Returns
    -------
    tuple[float, float]
        旋转后的二维坐标。
    """
    angle_radians = math.radians(
        float(angle_degrees)
    )

    cosine_value = math.cos(
        angle_radians
    )

    sine_value = math.sin(
        angle_radians
    )

    rotated_x = (
        float(point_x) * cosine_value
        - float(point_y) * sine_value
    )

    rotated_y = (
        float(point_x) * sine_value
        + float(point_y) * cosine_value
    )

    return rotated_x, rotated_y


def rotate_projected_view(
    visible_shape,
    hidden_shape,
    anchor_x,
    anchor_y,
    angle_degrees,
):
    """
    将投影视图和对应投影基准点同步旋转。

    必须同步处理 Shape 和 anchor，否则 Shape 旋转后，
    anchor 仍停留在旋转前的位置，后续平移会发生偏差。

    Parameters
    ----------
    visible_shape : Part.Shape
        可见线 Shape。

    hidden_shape : Part.Shape or None
        隐藏线 Shape。

    anchor_x : float
        旋转前基准点 X。

    anchor_y : float
        旋转前基准点 Y。

    angle_degrees : float
        旋转角度，逆时针为正。

    Returns
    -------
    tuple
        rotated_visible_shape,
        rotated_hidden_shape,
        rotated_anchor_x,
        rotated_anchor_y
    """
    rotation_center = App.Vector(
        0.0,
        0.0,
        0.0,
    )

    rotation_axis = App.Vector(
        0.0,
        0.0,
        1.0,
    )

    rotated_visible_shape = None

    if is_valid_shape(visible_shape):
        rotated_visible_shape = (
            visible_shape.copy()
        )

        rotated_visible_shape.rotate(
            rotation_center,
            rotation_axis,
            float(angle_degrees),
        )

    rotated_hidden_shape = None

    if is_valid_shape(hidden_shape):
        rotated_hidden_shape = (
            hidden_shape.copy()
        )

        rotated_hidden_shape.rotate(
            rotation_center,
            rotation_axis,
            float(angle_degrees),
        )

    rotated_anchor_x, rotated_anchor_y = (
        rotate_point_2d(
            point_x=anchor_x,
            point_y=anchor_y,
            angle_degrees=angle_degrees,
        )
    )

    return (
        rotated_visible_shape,
        rotated_hidden_shape,
        rotated_anchor_x,
        rotated_anchor_y,
    )
# ============================================================
# Shape 平移
# ============================================================

def translate_shape_by_anchor(
    source_shape,
    current_anchor_x,
    current_anchor_y,
    target_anchor_x,
    target_anchor_y,
):
    """
    按统一基准点平移投影视图。

    只进行平移，不进行缩放或旋转。
    """
    if not is_valid_shape(source_shape):
        return None

    moved_shape = source_shape.copy()

    offset_x = (
        float(target_anchor_x)
        - float(current_anchor_x)
    )

    offset_y = (
        float(target_anchor_y)
        - float(current_anchor_y)
    )

    moved_shape.translate(
        App.Vector(
            offset_x,
            offset_y,
            0.0,
        )
    )

    return moved_shape


# ============================================================
# 创建 FreeCAD DXF 导出对象
# ============================================================

def create_part_feature(
    document,
    object_name,
    shape,
):
    """
    创建用于 DXF 导出的 Part::Feature 对象。
    """
    if not is_valid_shape(shape):
        return None

    obj = document.addObject(
        "Part::Feature",
        object_name,
    )

    obj.Label = object_name
    obj.Shape = shape

    return obj


# ============================================================
# 单个 STEP 转换
# ============================================================

def convert_one_step_to_three_view_dxf(
    step_file,
    output_dxf,
    file_index,
    total_files,
):
    """
    将单个 STEP 文件转换为动态最大面积主视图的
    中国第一角法三视图 DXF。

    流程：
    1. 读取 STEP；
    2. 生成 FRONT、TOP、LEFT 三个候选投影；
    3. 按投影外接矩形面积选择主视图；
    4. 自动确定下方视图和右侧视图；
    5. 根据实际投影尺寸布局；
    6. 导出一个 DXF。
    """
    document = None

    log()
    log("=" * 70)
    log(
        f"[{file_index}/{total_files}] "
        f"开始处理：{os.path.basename(step_file)}"
    )
    log("=" * 70)
    log(f"输入 STEP：{step_file}")
    log(f"输出 DXF ：{output_dxf}")

    try:
        if not os.path.isfile(step_file):
            raise FileNotFoundError(
                f"找不到 STEP 文件：{step_file}"
            )

        if (
            os.path.isfile(output_dxf)
            and not OVERWRITE_EXISTING_DXF
        ):
            log("同名 DXF 已存在，按配置跳过。")

            return {
                "status": "skipped",
                "step_file": step_file,
                "output_dxf": output_dxf,
                "message": "同名 DXF 已存在",
            }

        # ====================================================
        # 1. 加载 STEP
        # ====================================================

        log()
        log("[1/6] 正在加载 STEP 模型...")

        source_shape = Part.Shape()
        source_shape.read(step_file)

        if source_shape.isNull():
            raise RuntimeError(
                "STEP 读取完成，但 Shape 为空。"
            )

        if len(source_shape.Edges) == 0:
            raise RuntimeError(
                "STEP 模型没有有效边。"
            )

        log(f"      边数：{len(source_shape.Edges)}")
        log(f"      面数：{len(source_shape.Faces)}")

        length, width, height = (
            get_model_dimensions(source_shape)
        )

        model_center = get_model_center(
            source_shape
        )

        anchor_marker = make_anchor_marker(
            model_center=model_center,
            length=length,
            width=width,
            height=height,
        )

        log()
        log("      三维包围盒尺寸：")
        log(f"      X：{length:.3f}")
        log(f"      Y：{width:.3f}")
        log(f"      Z：{height:.3f}")

        log(
            "      模型统一基准点："
            f"({model_center.x:.3f}, "
            f"{model_center.y:.3f}, "
            f"{model_center.z:.3f})"
        )

        max_dimension = max(
            length,
            width,
            height,
        )

        gap = max(
            MIN_GAP,
            max_dimension * GAP_RATIO,
        )

        log()
        log(
            "      Gap = max("
            f"{MIN_GAP:.3f}, "
            f"{max_dimension:.3f} × "
            f"{GAP_RATIO:.3f})"
        )
        log(f"      最终 Gap：{gap:.3f}")

        # ====================================================
        # 2. 生成三个候选投影
        # ====================================================

        log()
        log("[2/6] 正在生成三个候选投影...")

        candidate_view_data = {}

        for view_name in CANDIDATE_VIEW_ORDER:
            direction = VIEW_DIRECTIONS[view_name]

            log(f"      正在生成 {view_name}...")

            visible_shape, hidden_shape = (
                project_one_view(
                    source_shape=source_shape,
                    direction=direction,
                )
            )

            anchor_x, anchor_y = (
                get_projected_anchor(
                    anchor_marker=anchor_marker,
                    direction=direction,
                )
            )

            rotation_angle = float(
                BASE_VIEW_ROTATIONS[view_name]
            )

            if abs(rotation_angle) > 1.0e-9:
                (
                    visible_shape,
                    hidden_shape,
                    anchor_x,
                    anchor_y,
                ) = rotate_projected_view(
                    visible_shape=visible_shape,
                    hidden_shape=hidden_shape,
                    anchor_x=anchor_x,
                    anchor_y=anchor_y,
                    angle_degrees=rotation_angle,
                )

            if not is_valid_shape(visible_shape):
                raise RuntimeError(
                    f"{view_name} 旋转后可见线无效。"
                )

            projected_width, projected_height = (
                get_shape_size(visible_shape)
            )

            projected_area = (
                projected_width
                * projected_height
            )

            hidden_edge_count = 0

            if is_valid_shape(hidden_shape):
                hidden_edge_count = len(
                    hidden_shape.Edges
                )

            candidate_view_data[view_name] = {
                "visible": visible_shape,
                "hidden": hidden_shape,
                "projected_size": (
                    projected_width,
                    projected_height,
                ),
                "projected_area": projected_area,
                "anchor": (
                    anchor_x,
                    anchor_y,
                ),
                "rotation_angle": rotation_angle,
            }

            log(
                f"        基础旋转角度："
                f"{rotation_angle:.3f}°"
            )
            log(
                f"        投影包围盒："
                f"{projected_width:.3f} × "
                f"{projected_height:.3f}"
            )
            log(
                f"        包围盒面积："
                f"{projected_area:.3f}"
            )
            log(
                f"        可见边："
                f"{len(visible_shape.Edges)}，"
                f"隐藏边：{hidden_edge_count}"
            )

        # ====================================================
        # 3. 固定 FRONT 为主视图
        # ====================================================

        log()
        log("[3/6] 使用固定主视图...")

        main_view_name = "FRONT"

        role_mapping = build_view_role_mapping(
            main_view_name
        )

        role_view_data = build_role_view_data(
            candidate_view_data=(
                candidate_view_data
            ),
            role_mapping=role_mapping,
        )

        log(
            f"      最大面积主视图："
            f"{main_view_name}"
        )

        for role_name in (
            "MAIN",
            "BOTTOM",
            "RIGHT",
        ):
            role_data = role_view_data[role_name]

            role_width, role_height = (
                role_data["projected_size"]
            )

            log(
                f"      {role_name:<7}："
                f"来源={role_data['source_view']}，"
                f"总旋转={role_data['total_rotation']:.3f}°，"
                f"尺寸={role_width:.3f} × "
                f"{role_height:.3f}"
            )

        # ====================================================
        # 4. 计算三视图布局
        # ====================================================

        log()
        log("[4/6] 正在计算第一角法布局...")

        positions, distances = (
            build_first_angle_three_view_layout(
                role_view_data=role_view_data,
                gap=gap,
            )
        )

        log(
            "      主视图到右侧视图中心距离："
            f"{distances['horizontal_center_distance']:.3f}"
        )

        log(
            "      主视图到下方视图中心距离："
            f"{distances['vertical_center_distance']:.3f}"
        )

        for role_name in (
            "MAIN",
            "RIGHT",
            "BOTTOM",
        ):
            target_x, target_y = positions[
                role_name
            ]

            log(
                f"      {role_name:<7}："
                f"({target_x:.3f}, "
                f"{target_y:.3f})"
            )

        # ====================================================
        # 5. 创建 DXF 导出对象
        # ====================================================

        log()
        log("[5/6] 正在创建二维导出对象...")

        document_name = (
            f"ThreeViewsDXF_{file_index}"
        )

        document = App.newDocument(
            document_name
        )

        export_objects = []

        for role_name in (
            "MAIN",
            "RIGHT",
            "BOTTOM",
        ):
            role_data = role_view_data[role_name]

            target_anchor_x, target_anchor_y = (
                positions[role_name]
            )

            current_anchor_x, current_anchor_y = (
                role_data["anchor"]
            )

            moved_visible_shape = (
                translate_shape_by_anchor(
                    source_shape=role_data["visible"],
                    current_anchor_x=current_anchor_x,
                    current_anchor_y=current_anchor_y,
                    target_anchor_x=target_anchor_x,
                    target_anchor_y=target_anchor_y,
                )
            )

            visible_object = create_part_feature(
                document=document,
                object_name=(
                    f"{role_name}_"
                    f"{role_data['source_view']}_VISIBLE"
                ),
                shape=moved_visible_shape,
            )

            if visible_object is not None:
                export_objects.append(
                    visible_object
                )

            if EXPORT_HIDDEN_LINES:
                hidden_shape = role_data["hidden"]

                if is_valid_shape(hidden_shape):
                    moved_hidden_shape = (
                        translate_shape_by_anchor(
                            source_shape=hidden_shape,
                            current_anchor_x=(
                                current_anchor_x
                            ),
                            current_anchor_y=(
                                current_anchor_y
                            ),
                            target_anchor_x=(
                                target_anchor_x
                            ),
                            target_anchor_y=(
                                target_anchor_y
                            ),
                        )
                    )

                    hidden_object = create_part_feature(
                        document=document,
                        object_name=(
                            f"{role_name}_"
                            f"{role_data['source_view']}_HIDDEN"
                        ),
                        shape=moved_hidden_shape,
                    )

                    if hidden_object is not None:
                        export_objects.append(
                            hidden_object
                        )

        document.recompute()

        if not export_objects:
            raise RuntimeError(
                "没有生成任何可用于 DXF 导出的对象。"
            )

        log(
            f"      创建导出对象数量："
            f"{len(export_objects)}"
        )

        # ====================================================
        # 6. 导出 DXF
        # ====================================================

        log()
        log("[6/6] 正在导出 DXF...")

        output_directory = os.path.dirname(
            output_dxf
        )

        if output_directory:
            os.makedirs(
                output_directory,
                exist_ok=True,
            )

        if os.path.isfile(output_dxf):
            if OVERWRITE_EXISTING_DXF:
                os.remove(output_dxf)
            else:
                raise FileExistsError(
                    f"DXF 已存在：{output_dxf}"
                )

        importDXF.export(
            export_objects,
            output_dxf,
        )

        if not os.path.isfile(output_dxf):
            raise RuntimeError(
                "FreeCAD 执行导出后，"
                "没有找到 DXF 输出文件。"
            )

        output_size = os.path.getsize(
            output_dxf
        )

        if output_size <= 0:
            raise RuntimeError(
                "DXF 文件已经创建，"
                "但文件大小为 0。"
            )

        log()
        log("当前模型转换成功")
        log(f"输出文件：{output_dxf}")
        log(f"文件大小：{output_size} 字节")
        log(f"主视图来源：{main_view_name}")
        log(
            "下方视图来源："
            f"{role_view_data['BOTTOM']['source_view']}"
        )
        log(
            "右侧视图来源："
            f"{role_view_data['RIGHT']['source_view']}"
        )
        log(f"Gap：{gap:.3f}")

        return {
            "status": "success",
            "step_file": step_file,
            "output_dxf": output_dxf,
            "output_size": output_size,
            "length": length,
            "width": width,
            "height": height,
            "gap": gap,
            "main_view": main_view_name,
            "bottom_view": (
                role_view_data[
                    "BOTTOM"
                ]["source_view"]
            ),
            "right_view": (
                role_view_data[
                    "RIGHT"
                ]["source_view"]
            ),
        }

    finally:
        if document is not None:
            try:
                App.closeDocument(
                    document.Name
                )
            except Exception as close_error:
                log(
                    "警告：关闭 FreeCAD 文档失败："
                    f"{close_error}"
                )


# ============================================================
# 批量处理
# ============================================================

def batch_convert_folder(folder_path):
    """
    批量转换文件夹中的 STEP 文件。
    """
    step_files = find_step_files(
        folder_path
    )

    if not step_files:
        raise RuntimeError(
            "所选文件夹中没有找到 "
            ".stp 或 .step 文件。"
        )

    total_files = len(step_files)

    log()
    log("=" * 70)
    log("STEP 中国第一角法三视图批量转换")
    log("=" * 70)
    log(f"处理文件夹：{folder_path}")
    log(f"找到 STEP 文件数量：{total_files}")
    log(f"递归扫描子文件夹：{RECURSIVE_SCAN}")
    log(f"覆盖已有 DXF：{OVERWRITE_EXISTING_DXF}")
    log(f"导出隐藏线：{EXPORT_HIDDEN_LINES}")

    log()
    log("待处理文件：")

    for index, step_file in enumerate(
        step_files,
        start=1,
    ):
        log(
            f"  {index:>4}. "
            f"{step_file}"
        )

    successful_results = []
    skipped_results = []
    failed_results = []

    for file_index, step_file in enumerate(
        step_files,
        start=1,
    ):

        output_dxf = get_output_dxf_path(
            step_file
        )

        try:

            result = (
                convert_one_step_to_three_view_dxf(
                    step_file=step_file,
                    output_dxf=output_dxf,
                    file_index=file_index,
                    total_files=total_files,
                )
            )

            if result["status"] == "success":
                successful_results.append(
                    result
                )

            elif result["status"] == "skipped":
                skipped_results.append(
                    result
                )

        except Exception:

            error_text = traceback.format_exc()

            log()
            log("=" * 70)
            log("当前模型处理失败")
            log("=" * 70)
            log(step_file)
            log(error_text)

            failed_results.append({
                "step_file": step_file,
                "error": error_text,
            })

    # ========================================================
    # 输出统计结果
    # ========================================================

    log()
    log("=" * 70)
    log("批量转换完成")
    log("=" * 70)

    log(
        f"STEP 总数量：{total_files}"
    )

    log(
        f"成功数量：{len(successful_results)}"
    )

    log(
        f"跳过数量：{len(skipped_results)}"
    )

    log(
        f"失败数量：{len(failed_results)}"
    )

    if successful_results:

        log()
        log("成功文件：")

        for result in successful_results:

            log(
                f"  [成功] "
                f"{os.path.basename(result['step_file'])}"
            )

    if skipped_results:

        log()
        log("跳过文件：")

        for result in skipped_results:

            log(
                f"  [跳过] "
                f"{os.path.basename(result['step_file'])}"
            )

    if failed_results:

        log()
        log("失败文件：")

        for result in failed_results:

            log(
                f"  [失败] "
                f"{os.path.basename(result['step_file'])}"
            )

    log()
    log("=" * 70)

    if successful_results:

        log(
            "批量转换完成，至少有一个 DXF 成功生成。"
        )

    else:

        raise RuntimeError(
            "没有成功生成任何 DXF 文件。"
        )




# ============================================================
# 主程序
# ============================================================

def main():

    folder_path = select_input_folder()

    batch_convert_folder(
        folder_path
    )


# ============================================================
# 程序入口
# ============================================================

try:

    log()
    log("=" * 70)
    log("正在进入主程序")
    log("=" * 70)

    main()

except Exception as error:

    log()
    log("=" * 70)
    log("程序执行失败")
    log("=" * 70)

    log(str(error))

    traceback.print_exc()

    sys.exit(1)