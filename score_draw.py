"""
score_draw.py — 影视决策测评系统 五维度雷达图生成器
=====================================================
功能：
    1. 强制启用 Agg 无界面后端，适配服务器 / Mac 无 GUI 环境，杜绝图形报错。
    2. 五维度顺序与 parser.py 完全统一：["理性", "利他", "激进", "效率", "谨慎"]。
    3. 主函数 generate_radar(score_list, theme) → 返回 PNG 二进制字节流。
       theme 仅支持 cyber(科幻) / magic(魔幻) / anime(动漫)，自动匹配专属配色、画布背景、图表标题。
    4. 计分规则：任意维度分数 < 0 强制修正为 0，上限 100 封顶。
    5. 雷达图闭环绘图、半透明填充、线条清晰，画布尺寸适配网页展示。
    6. 图片不落地本地文件，使用 io.BytesIO 返回字节流，适配 Flask 网页直接渲染。
    7. 绘图结束执行 plt.close(fig) 释放画布，防止内存堆积。
    8. 雷达径向刻度永久锁定 0~100，不自动自适应缩放。
    9. 中文字体稳健回退：未找到候选中文字体时强制使用 DejaVu Sans。

安全加固（v2）：
    - sanitize_score(): 任意输入→0.0-100.0 float（处理 None/字符串/NaN/inf）
    - 顶点文字溢出自动向内放置，防止画布外溢
    - parser 容错导入，避免与标准库冲突
    - generate_radar_for_block 支持中英文变体输入
    - role_lib 外置到 roles.json，按需加载 + LRU 缓存
    - 向量相似度匹配角色（余弦相似度）
    - pytest 单元测试覆盖核心路径

依赖：仅标准库 + matplotlib + numpy（requirements.txt 已包含，无需新增）。
"""

# ============================================================
# 一、强制启用 Agg 后端（必须在导入 pyplot 之前执行）
# ============================================================
import matplotlib
matplotlib.use("Agg")  # 无 GUI 后端，适配服务器/无桌面环境，避免 Tcl/Tk 报错
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np
import io
import os
import json
import math
from functools import lru_cache


# ============================================================
# 二、安全加固：sanitize_score — 任意输入 → 0.0-100.0 float
# ============================================================
def sanitize_score(x):
    """将任意输入规范为 0.0-100.0 的 float，处理边界异常值。

    处理规则：
        - None → 0.0
        - 字符串数字（如 "85"）→ 85.0
        - NaN / inf → 0.0
        - < 0 → 0.0（强制归零）
        - > 100 → 100.0（强制封顶）
        - 正常值 → 保留，转为 float

    参数：
        x : 任意类型（int/float/str/None/NaN/inf）

    返回：
        float : 0.0 ~ 100.0 范围内的浮点数
    """
    if x is None:
        return 0.0
    try:
        val = float(x)
    except (ValueError, TypeError):
        return 0.0
    if math.isnan(val) or math.isinf(val):
        return 0.0
    return max(0.0, min(100.0, val))


# ---------- 中文字体稳健回退配置（适配 Windows / Mac / Linux）----------
# 按优先级尝试常见中文字体名，找到第一个可用的即配置；
# 找不到则强制降级为 DejaVu Sans（避免中文显示方块）。
_ZH_FONT_CANDIDATES = [
    "Arial Unicode MS",     # macOS 通用中文字体
    "PingFang SC",          # macOS 苹方
    "Heiti TC",             # macOS 黑体
    "Hiragino Sans GB",     # macOS 冬青黑体
    "Microsoft YaHei",      # Windows 微软雅黑
    "SimHei",               # Windows 黑体
    "Noto Sans CJK SC",    # Linux 思源黑体
    "WenQuanYi Micro Hei",  # Linux 文泉驿
]
_available_fonts = {f.name for f in font_manager.fontManager.ttflist}
ZH_FONT = next((f for f in _ZH_FONT_CANDIDATES if f in _available_fonts), None)
if ZH_FONT:
    plt.rcParams["font.sans-serif"] = [ZH_FONT, "DejaVu Sans"]
else:
    # 【字体稳健回退】未找到任何候选中文字体时，强制使用 DejaVu Sans
    plt.rcParams["font.sans-serif"] = ["DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False  # 负号正常显示


# ============================================================
# 二、维度定义（与 parser.py 的 DIMENSIONS 严格统一，勿改顺序）
# ============================================================
DIMENSIONS = ["理性", "利他", "激进", "效率", "谨慎"]
DIM_COUNT = len(DIMENSIONS)  # 固定 5


# ============================================================
# 三、三套主题配色预设（科幻赛博 / 魔幻 / 动漫清新）
# ============================================================
# 说明：如需自定义颜色，直接修改下方对应主题的色值即可。
#       - line_color  : 雷达图轮廓线颜色
#       - fill_color  : 雷达图填充色（半透明在绘图时通过 alpha 控制）
#       - vertex_color: 顶点圆点颜色
#       - text_color  : 维度标签文字颜色
#       - bg_color    : 画布背景色
#       - title       : 该主题默认图表标题（自动套用）
THEME_PRESETS = {
    # ① 科幻赛博风：青色霓虹 + 品红强调（对应 app.py 赛博朋克主题）
    "cyber": {
        "line_color":   "#00ffd5",
        "fill_color":   "#00ffd5",
        "vertex_color": "#ff006e",
        "text_color":   "#e6edf3",
        "bg_color":     "#0d1117",
        "title":        "科幻 · 决策倾向雷达图",
    },
    # ② 魔幻风：暗金 + 紫色魔法光（对应哈利波特/指环王/爱丽丝板块）
    "magic": {
        "line_color":   "#ffd700",
        "fill_color":   "#9b59b6",
        "vertex_color": "#ffd700",
        "text_color":   "#f0e6d2",
        "bg_color":     "#1a0d2e",
        "title":        "魔幻 · 决策倾向雷达图",
    },
    # ③ 动漫清新风：薄荷绿 + 樱花粉（对应千与千寻/天气之子/疯狂动物城板块）
    "anime": {
        "line_color":   "#39ff14",
        "fill_color":   "#ff9ecd",
        "vertex_color": "#39ff14",
        "text_color":   "#2d3436",
        "bg_color":     "#fdfdfd",
        "title":        "动漫 · 决策倾向雷达图",
    },
}

# 默认主题（app.py 未指定时使用）
DEFAULT_THEME = "cyber"


# ============================================================
# 四、核心绘图函数
# ============================================================

def generate_radar(score_list, theme=DEFAULT_THEME, title=None):
    """生成五维度雷达图，返回 PNG 二进制字节流。

    参数：
        score_list : 长度为 5 的数字列表/元组，顺序严格对应
                     [理性, 利他, 激进, 效率, 谨慎]
        theme      : 配色主题，仅支持 "cyber"(科幻) / "magic"(魔幻) / "anime"(动漫)
                     自动匹配该主题的专属配色、画布背景、图表标题。
        title      : 自定义标题（可选）。传 None 时自动套用主题默认标题。

    返回：
        bytes : PNG 图片二进制数据，可直接写入 Flask/Streamlit 响应流。
                例:  st.image(bytes, use_container_width=True)
                     或  Response(bytes, mimetype="image/png")

    异常处理：
        - 分数 < 0 自动修正为 0（不报错）
        - 长度 ≠ 5 抛 ValueError（提示维度不匹配）
        - 未知 theme 抛 ValueError
    """
    # ---------- 1. 入参校验 ----------
    if len(score_list) != DIM_COUNT:
        raise ValueError(
            f"score_list 长度必须为 {DIM_COUNT}（当前 {len(score_list)}），"
            f"顺序对应：{DIMENSIONS}"
        )
    if theme not in THEME_PRESETS:
        raise ValueError(
            f"未知主题 '{theme}'，仅支持：{list(THEME_PRESETS.keys())}"
        )

    # ---------- 2. 计分规则：使用 sanitize_score 规范化输入 ----------
    # 【安全加固】统一使用 sanitize_score 处理，支持 None/字符串/NaN/inf 等异常输入
    scores = [sanitize_score(s) for s in score_list]

    # ---------- 3. 闭环数据：首点追加到末尾，形成闭合多边形 ----------
    angles = np.linspace(0, 2 * np.pi, DIM_COUNT, endpoint=False).tolist()
    closed_scores = scores + scores[:1]   # 首点追加到末尾
    closed_angles = angles + angles[:1]   # 角度同样闭合

    # ---------- 4. 创建画布 ----------
    # figsize=5 英寸方形 + dpi=150 → 约 750×750 px，适配网页嵌入
    cfg = THEME_PRESETS[theme]
    fig = plt.figure(figsize=(5, 5), dpi=150)
    ax = fig.add_subplot(111, polar=True)

    # 背景色：画布 + 绘图区均设为主题背景色
    fig.patch.set_facecolor(cfg["bg_color"])
    ax.set_facecolor(cfg["bg_color"])

    # ---------- 5. 绘制半透明填充与清晰轮廓线 ----------
    ax.fill(closed_angles, closed_scores,
            color=cfg["fill_color"], alpha=0.25, zorder=1)    # 半透明填充
    ax.plot(closed_angles, closed_scores,
            color=cfg["line_color"], linewidth=2.5, zorder=2)  # 清晰轮廓线

    # ---------- 6. 绘制顶点彩色圆点 ----------
    ax.scatter(angles, scores,
               color=cfg["vertex_color"], s=60, zorder=3)

    # ========== 【视觉优化1：顶点分数文字分离 + 溢出保护】==========
    # 使用数据坐标系沿径向向外偏移 8 个单位，
    # 【溢出保护】当 sc + offset > 100 时改为向内放置（sc - offset），
    # 防止文字被裁切或画布外溢。
    VERTEX_OFFSET = 8  # 顶点分数文字径向偏移量
    for ang, sc in zip(angles, scores):
        # 溢出检测：超过上限时向内放置
        if sc + VERTEX_OFFSET <= 100:
            text_r = sc + VERTEX_OFFSET  # 正常向外放置
        else:
            text_r = max(0, sc - VERTEX_OFFSET)  # 溢出时向内放置
        ax.text(ang, text_r, f"{int(sc)}",
                color=cfg["vertex_color"], fontsize=11,
                fontweight="bold", ha="center", va="center",
                zorder=4, clip_on=False)

    # ---------- 8. 维度刻度（外圈五个维度名）----------
    ax.set_xticks(angles)
    ax.set_xticklabels(DIMENSIONS, color=cfg["text_color"], fontsize=13)
    ax.tick_params(axis='x', pad=15)  # 维度标签放在圈外稍远处

    # ---------- 9. 径向轴：标尺永久锁定 0~100，隐藏所有刻度数字与刻度线 ----------
    # ⚠️ 按需求删除 20/40/60/80/100 环形刻度数字与径向刻度标记，
    #    仅保留 set_yticks 的位置锚点，让圆形背景网格辅助线仍可正常绘制。
    ax.set_ylim(0, 100)
    ax.set_yticks([20, 40, 60, 80, 100])      # 保留刻度位置（给网格线用）
    ax.set_yticklabels([])                     # 隐藏刻度数字（空标签）
    ax.tick_params(axis='y', left=False, labelleft=False)  # 隐藏径向刻度线 + 刻度标记

    # ---------- 11. 网格与边框美化 ----------
    ax.grid(color=cfg["text_color"], alpha=0.2, linestyle="--", linewidth=0.8)
    ax.spines['polar'].set_color(cfg["text_color"])
    ax.spines['polar'].set_alpha(0.3)

    # ---------- 12. 标题（传 None 自动套用主题默认标题）----------
    if title is None:
        title = cfg["title"]
    if title:
        ax.set_title(title, color=cfg["text_color"], fontsize=15,
                     fontweight="bold", pad=25)

    # ---------- 13. 紧凑布局 ----------
    fig.tight_layout()

    # ---------- 14. 导出为 PNG 字节流（不落地本地文件）----------
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150,
                facecolor=fig.get_facecolor(), bbox_inches="tight")
    buf.seek(0)
    png_bytes = buf.getvalue()

    # ---------- 15. 关闭画布与缓冲区，防止内存泄漏 ----------
    buf.close()
    plt.close(fig)  # 必须关闭，避免句柄堆积

    return png_bytes


# ============================================================
# 五、便捷封装：按板块名自动匹配主题（支持中英文变体）
# ============================================================

# 【增强】主题变体映射表：支持常见英文/中文变体输入
_THEME_VARIANTS = {
    # cyber 科幻
    "cyber": "cyber",
    "sci-fi": "cyber",
    "scifi": "cyber",
    "sci_fi": "cyber",
    "科幻": "cyber",
    "科幻片": "cyber",
    # magic 魔幻
    "magic": "magic",
    "fantasy": "magic",
    "魔幻": "magic",
    "魔幻片": "magic",
    # anime 动漫
    "anime": "anime",
    "cartoon": "anime",
    "animation": "anime",
    "动漫": "anime",
    "动画片": "anime",
}


def _resolve_theme(block_name):
    """将板块名解析为标准主题 key。

    参数：
        block_name : 板块名称，支持中英文变体

    返回：
        str : 标准主题 key（cyber/magic/anime）
    """
    if block_name in _THEME_VARIANTS:
        return _THEME_VARIANTS[block_name]
    # 模糊匹配：检查是否包含关键字
    name_lower = str(block_name).lower()
    for keyword, theme in _THEME_VARIANTS.items():
        if keyword.lower() in name_lower:
            return theme
    return DEFAULT_THEME


def generate_radar_for_block(score_list, block_name, title=None):
    """根据板块名自动匹配配色主题（支持中英文变体）。

    参数：
        score_list : 长度 5 的分数列表
        block_name : 板块名，支持 cyber/科幻/sci-fi 等变体
        title      : 自定义标题（可选，传 None 自动套用主题默认标题）

    返回：
        bytes : PNG 字节流
    """
    theme = _resolve_theme(block_name)
    return generate_radar(score_list, theme=theme, title=title)


# ============================================================
# 【新增区域】角色决策分析模块
# ============================================================
# 说明：以下内容为本次新增，未改动文件上方任何绘图代码、主题配置、字体配置。
#       仅在文件末尾追加 get_style_analysis 函数与 role_lib 角色文案库。
#       ⚠️ 注意：本模块必须位于 __main__ 块之前，否则自测调用时函数未定义。
# ============================================================


# ============================================================
# 角色文案库加载（支持 JSON 外置 + LRU 缓存）
# ============================================================

# roles.json 文件路径（与 score_draw.py 同目录）
_ROLES_JSON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "roles.json")

# role_lib 缓存变量（模块级，避免重复加载）
_role_lib_cache = None


@lru_cache(maxsize=1)
def load_role_lib():
    """加载角色文案库，优先从 roles.json 读取，不存在则回退到内置字典。

    返回：
        dict : 三层嵌套结构 {theme: {movie: {dimension: {name, text, vector}}}}
    """
    global _role_lib_cache
    if _role_lib_cache is not None:
        return _role_lib_cache

    # 优先尝试从 roles.json 加载
    if os.path.exists(_ROLES_JSON_PATH):
        try:
            with open(_ROLES_JSON_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            _role_lib_cache = data
            return data
        except (json.JSONDecodeError, IOError):
            pass  # 加载失败则回退到内置字典

    # 回退：从内置 role_lib 转换（兼容旧格式）
    global role_lib
    converted = {}
    for theme, movies in role_lib.items():
        converted[theme] = {}
        for movie, dims in movies.items():
            converted[theme][movie] = {}
            for dim, value in dims.items():
                if isinstance(value, tuple) and len(value) == 2:
                    # 旧格式：(name, text) → 新格式：{name, text, vector: None}
                    converted[theme][movie][dim] = {
                        "name": value[0],
                        "text": value[1],
                        "vector": None
                    }
                elif isinstance(value, dict):
                    # 已是新格式
                    converted[theme][movie][dim] = value
    _role_lib_cache = converted
    return converted


def cosine_similarity(vec_a, vec_b):
    """计算两个向量的余弦相似度。

    参数：
        vec_a : 向量 A（list/np.ndarray）
        vec_b : 向量 B（list/np.ndarray）

    返回：
        float : 余弦相似度，范围 [-1, 1]
    """
    a = np.array(vec_a, dtype=float)
    b = np.array(vec_b, dtype=float)
    dot_product = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot_product / (norm_a * norm_b))


# ---------- 三层嵌套角色文案库（内置备份，格式：tuple） ----------
# 结构层级：theme → 影片名 → 维度 → (角色名称, 完整长段分析文本)
# 【安全加固】优先使用 roles.json，此内置字典作为回退
role_lib = {
    # ============================================================
    # ① 科幻板块（cyber）
    # ============================================================
    "cyber": {
        # ---------- 《黑客帝国》已完整填充（标准示范）----------
        "黑客帝国": {
            "理性": (
                "墨菲斯",
                "你像墨菲斯一样以信念与逻辑驱动决策，擅长在信息残缺的绝境中拆解因果链、"
                "为团队锚定最优路径，是群体里最稳的「战略支点」。"
                "短板在于过度依赖推演，面对需要快速直觉反应的瞬变场景时容易因权衡过久错失窗口。"
            ),
            "利他": (
                "崔妮蒂",
                "你像崔妮蒂一样把他人安危置于自身之上，关键时刻愿意为同伴扛下致命风险，"
                "是团队里最值得托付后背的守护者。"
                "短板在于容易把「自我牺牲」当作默认选项，忽视自身资源枯竭，长线作战时会被消耗拖垮。"
            ),
            "激进": (
                "尼奥（觉醒态）",
                "你像觉醒后的尼奥一样相信主动出击能改写规则，"
                "敢于在不可能的格局里撕开缺口，是冲锋时走在最前的破局者。"
                "短板是行动先于情报核实，容易在敌方布局未明的区域贸然深入，"
                "被诱敌战术反制。"
            ),
            "效率": (
                "史密斯（早期）",
                "你像早期史密斯一样以目标达成为唯一准绳，擅长压缩冗余流程、"
                "用最短链路完成任务，是执行力最强的「清道夫」。"
                "短板是过度追求效率会牺牲人情与长期信任，把盟友当成可替换的零件。"
            ),
            "谨慎": (
                "塞弗",
                "你像塞弗一样精于风险评估与自保策略，"
                "总能在行动前算清退路与代价，是团队里最难被套路的「冷算手」。"
                "短板是把安全置于价值之上，在需要信念支撑的持久战里容易因收益预期不足而倒戈。"
            ),
        },
        # ---------- 《银翼杀手》已完整填充 ----------
        "银翼杀手": {
            "理性": (
                "里克·德卡德",
                "你像德卡德一样用冷静的逻辑审视每一个细节，在模糊的身份边界中保持清醒判断，"
                "是团队里最敏锐的「观察者」。"
                "短板在于过度分析容易陷入存在主义的困惑，在需要果断行动时会因内耗而迟疑。"
            ),
            "利他": (
                "乔伊",
                "你像乔伊一样在有限的生命里追求真挚的情感连接，愿意为重要的人打破既定规则，"
                "是最动人的「追寻者」。"
                "短板在于把永恒的爱情当作全部意义，面对失去时容易陷入自我毁灭式的悲伤。"
            ),
            "激进": (
                "罗伊·巴蒂",
                "你像罗伊一样带着被创造者的愤怒与不甘，敢于向造物主发起挑战，"
                "在生命最后的时刻爆发出最强烈的存在感，是最悲壮的「反叛者」。"
                "短板在于被愤怒驱动容易做出极端决定，把短暂的生命消耗在复仇上。"
            ),
            "效率": (
                "Gaff",
                "你像Gaff一样用最少的动作完成最关键的任务，沉默寡言却总能精准命中目标，"
                "是最高效的「执行者」。"
                "短板在于过于工具化，在需要温度与情感的合作中会显得冷漠疏离。"
            ),
            "谨慎": (
                "特瑞莎",
                "你像特瑞莎一样在知晓自身身份后选择低调生活，懂得在危险环境中保持克制，"
                "是最谨慎的「生存者」。"
                "短板在于过度谨慎容易错过改变命运的契机，在需要主动出击时会被恐惧束缚。"
            ),
        },
        # ---------- 《沙丘》已完整填充 ----------
        "沙丘": {
            "理性": (
                "保罗·厄崔迪",
                "你像保罗一样通过预知未来来规划每一步行动，在时间的长河里保持清醒的目标感，"
                "是最有远见的「先知」。"
                "短板在于过度依赖预知能力，面对未知的变量时会因计划被打乱而陷入混乱。"
            ),
            "利他": (
                "杰西卡",
                "你像杰西卡一样为了保护子女可以不惜一切代价，在权力的漩涡中始终以家人为重，"
                "是最伟大的「守护者」。"
                "短板在于把家人安全凌驾于一切之上，容易为了保护而做出违背道德的选择。"
            ),
            "激进": (
                "斯蒂尔加",
                "你像斯蒂尔加一样为了解放受压迫的民族可以付出生命代价，在面对帝国时从不退缩，"
                "是最勇猛的「反抗者」。"
                "短板在于对自由的执念过于极端，容易在胜利后陷入新的独裁陷阱。"
            ),
            "效率": (
                "杜飞特·哈瓦特",
                "你像哈瓦特一样以精准的暗杀手段解决政治对手，用最高效的方式清除威胁，"
                "是最冷酷的「清除者」。"
                "短板在于过于相信暴力解决问题，忽视了制度与民心的长期影响。"
            ),
            "谨慎": (
                "弗瑞曼长老",
                "你像弗瑞曼长老一样在沙漠中生存数千年，懂得资源管理与时机把握，"
                "是最智慧的「生存专家」。"
                "短板在于过于固守传统与经验，面对全新挑战时会因循守旧而失败。"
            ),
        },
    },

    # ============================================================
    # ② 魔幻板块（magic）— 全部已完整填充
    # ============================================================
    "magic": {
        # ---------- 《哈利波特》已完整填充 ----------
        "哈利波特": {
            "理性": (
                "邓布利多",
                "你像邓布利多一样以大局为重统筹全局，用缜密的计划引导团队走向胜利，"
                "是最睿智的「引路人」。"
                "短板在于为了整体目标可以牺牲个体，有时会显得过于冷漠与不可预测。"
            ),
            "利他": (
                "赫敏·格兰杰",
                "你像赫敏一样坚信知识与善良的力量，愿意为了正义挺身而出帮助弱者，"
                "是最勇敢的「守护者」。"
                "短板在于过于相信规则与程序，面对需要打破常规的情境时会陷入挣扎。"
            ),
            "激进": (
                "哈利·波特",
                "你像哈利一样面对黑魔法势力从不退缩，关键时刻总能爆发出惊人的勇气与力量，"
                "是最无畏的「斗士」。"
                "短板在于容易被愤怒与冲动驱动，有时会在没有充分准备的情况下贸然行动。"
            ),
            "效率": (
                "罗恩·韦斯莱",
                "你像罗恩一样在关键时刻总能找到最实用的解决方案，用直觉与幽默感化解紧张气氛，"
                "是最可靠的「应变者」。"
                "短板在于缺乏长远规划，面对复杂的长期任务时容易失去耐心。"
            ),
            "谨慎": (
                "斯内普",
                "你像斯内普一样在黑暗中潜伏多年只为最终的胜利，懂得隐藏真实意图与感情，"
                "是最深沉的「潜伏者」。"
                "短板在于过于封闭与孤僻，在需要信任他人时会因过往经历而无法敞开心扉。"
            ),
        },
        # ---------- 《指环王》已完整填充 ----------
        "指环王": {
            "理性": (
                "甘道夫",
                "你像甘道夫一样以智慧引导众人，在迷雾般的局势中保持清晰的判断力，"
                "是最明智的「向导」。"
                "短板在于喜欢用命运与预言来解释一切，有时会忽视个体的自由意志。"
            ),
            "利他": (
                "山姆·怀斯",
                "你像山姆一样对朋友忠诚不渝，在末日山的最后时刻依然坚守在弗罗多身边，"
                "是最忠诚的「伙伴」。"
                "短板在于过于依赖弗罗多的领导，面对需要独立决策的时刻会缺乏自信。"
            ),
            "激进": (
                "阿拉贡",
                "你像阿拉贡一样背负着王者的使命却不逃避责任，敢于直面黑暗魔君的力量，"
                "是最英勇的「王者」。"
                "短板在于被宿命感束缚，有时会忽略自己的幸福与他人的感受。"
            ),
            "效率": (
                "莱戈拉斯",
                "你像莱戈拉斯一样以精灵的敏锐与精准完成每一个任务，行动优雅且高效，"
                "是最敏捷的「射手」。"
                "短板在于过于完美主义，面对不完美的方案会因无法接受而犹豫。"
            ),
            "谨慎": (
                "格里马·沃姆舌",
                "你像沃姆舌一样在危险的权力漩涡中善于观察与伪装，懂得等待最佳时机，"
                "是最阴险的「权谋家」。"
                "短板在于被欲望驱动最终自食其果，证明了过度谨慎与算计反而会导致毁灭。"
            ),
        },
        # ---------- 《爱丽丝漫游仙境》已完整填充 ----------
        "爱丽丝漫游仙境": {
            "理性": (
                "蓝 Caterpillar",
                "你像毛毛虫一样以哲学家的视角审视世界，喜欢追问事物的本质与存在的意义，"
                "是最思辨的「思想者」。"
                "短板在于过度沉湎于思考而缺乏行动力，面对需要果断决策时会陷入迷惘。"
            ),
            "利他": (
                "白兔先生",
                "你像白兔一样总是为他人着想，虽然自己慌慌张张却从不忘记帮助朋友，"
                "是最热心的「引路者」。"
                "短板在于过于焦虑与紧张，在压力下容易把事情搞得更糟。"
            ),
            "激进": (
                "红心王后",
                "你像红心王后一样拥有绝对的权威与决断力，敢于挑战一切既定规则，"
                "是最霸气的「统治者」。"
                "短板在于过于专横跋扈，听不进任何反对意见，最终导致众叛亲离。"
            ),
            "效率": (
                "疯帽匠",
                "你像疯帽匠一样思维跳脱点子多，擅长用非常规方式解决问题，"
                "是最跳脱的「创意家」。"
                "短板在于思维过于跳跃难以预测，与团队协作时会让他人跟不上节奏。"
            ),
            "谨慎": (
                "柴郡猫",
                "你像柴郡猫一样在疯狂的世界里保持着超然的清醒，懂得观察局势再行动，"
                "是最神秘的「旁观者」。"
                "短板在于过于虚无与不可捉摸，在需要承诺与担当的时候会消失不见。"
            ),
        },
    },

    # ============================================================
    # ③ 动漫板块（anime）— 全部预留空白模板
    # ============================================================
    "anime": {
                "千与千寻": {
            "理性": (
                "钱婆婆",
                "你像钱婆婆一样以智慧与通透驱动决策，擅长在纷繁复杂的乱象中看透事物本质，为他人指点迷津，是群体里最有定力的「定盘星」。"
                "短板在于过于超脱，面对需要快速介入的冲突时容易因置身事外而错失干预时机。"
            ),
            "利他": (
                "千寻",
                "你像千寻一样把他人的难处放在心上，愿意为了守护重要的人拼尽全力，在绝境中也能保持善良与坚韧，是团队里最温暖的「微光」。"
                "短板在于容易把别人的责任扛到自己身上，过度承担会让自己在长期压力下身心俱疲。"
            ),
            "激进": (
                "无脸男",
                "你像无脸男一样追求即时的反馈与满足，敢于在陌生环境中用极端方式争取存在感，行动力极强，是能快速打破僵局的「破局者」。"
                "短板在于情绪波动大，容易在欲望中迷失自我，被外界的评价和反馈牵着走。"
            ),
            "效率": (
                "汤婆婆",
                "你像汤婆婆一样以目标达成为核心导向，擅长统筹资源、建立规则，把复杂的系统运营得井井有条，是执行力极强的「掌舵人」。"
                "短板在于过度追求结果会忽视人的情感需求，把下属当成运转的零件，容易积累不满。"
            ),
            "谨慎": (
                "锅炉爷爷",
                "你像锅炉爷爷一样在复杂环境中谨小慎微，懂得自保也懂得默默助人，总能在规则的缝隙里找到生存空间，是团队里最可靠的「暗桩」。"
                "短板在于过于谨慎不敢出头，在需要站出来承担责任的关键时刻容易选择退缩。"
            ),
        },
        "天气之子": {
            "理性": (
                "须贺圭介",
                "你像须贺圭介一样以成熟的理性权衡利弊，经历过失去后更懂得现实的重量，不会被热血冲昏头脑，是团队里最清醒的「压舱石」。"
                "短板在于过于务实容易磨灭初心，在需要信念支撑的抉择面前会因计算得失而犹豫。"
            ),
            "利他": (
                "天野阳菜",
                "你像阳菜一样把他人的期盼置于自身安危之上，愿意用自己的力量为世界带来光亮，是能给周围人带来希望的「小太阳」。"
                "短板在于习惯把责任全揽在自己身上，容易忽视自身的需求与边界，最终被过度的奉献拖垮。"
            ),
            "激进": (
                "森岛帆高",
                "你像帆高一样相信爱能超越一切规则，敢于为了守护重要的人与整个世界对抗，充满少年人的热血与冲劲，是最无畏的「逆行者」。"
                "短板在于行动先于思考，容易在冲动下做出不计后果的决定，给身边的人带来不必要的风险。"
            ),
            "效率": (
                "须贺夏美",
                "你像夏美一样行动力拉满，擅长用最短的时间搞定最麻烦的事，思维活跃点子多，是团队里最能打的「实干家」。"
                "短板在于做事容易三分钟热度，缺乏长期规划，遇到需要耐心打磨的事就会显得浮躁。"
            ),
            "谨慎": (
                "立花富美",
                "你像立花富美一样带着长辈的通透与谨慎，懂得敬畏自然与规律，做事稳扎稳打留有余地，是团队里最有智慧的「引路人」。"
                "短板在于过于保守容易错失机遇，在需要破釜沉舟的关键时刻会因顾虑太多而不敢出手。"
            ),
        },
        "疯狂动物城": {
            "理性": (
                "尼克·王尔德",
                "你像尼克一样用冷静的逻辑看透规则与人心，擅长在复杂的局面中找到最优解，思维缜密算无遗策，是团队里最聪明的「军师」。"
                "短板在于过于相信理性容易玩世不恭，在需要真心投入的关系里会因习惯性设防而错过真挚的连接。"
            ),
            "利他": (
                "夏奇羊",
                "你像夏奇羊一样用自己的影响力传递善意与包容，关心弱势群体的处境，愿意为了更公平的世界发声，是能凝聚人心的「精神旗帜」。"
                "短板在于过于追求和谐容易回避冲突，面对尖锐的矛盾时会因不想得罪人而无法做出果断抉择。"
            ),
            "激进": (
                "朱迪·霍普斯",
                "你像朱迪一样充满干劲与正义感，敢于挑战既定规则与权威，为了目标能拼尽全力，是最有冲劲的「开拓者」。"
                "短板在于过于急于证明自己，容易在冲动下做出欠考虑的决定，有时会为了速度牺牲质量和他人的感受。"
            ),
            "效率": (
                "牛局长",
                "你像牛局长一样以结果为导向，擅长建立秩序、管理团队，用严格的标准保证组织高效运转，是最可靠的「管理者」。"
                "短板在于过于刻板不近人情，容易忽视个体的特殊性与情感需求，把人当成执行任务的工具。"
            ),
            "谨慎": (
                "大先生",
                "你像大先生一样行事沉稳、步步为营，在复杂的利益格局中总能稳坐钓鱼台，注重风险控制从不打无准备之仗，是最有定力的「掌舵者」。"
                "短板在于过于保守不敢冒险，在需要大胆破局的时刻会因顾虑太多而错失良机。"
            ),
        },
    },
}


# ---------- 人格判定阈值：第一名与第二名差值 ≤ 此值判定为复合型 ----------
COMPOUND_THRESHOLD = 8


def get_style_analysis(score_list, theme, movie_name):
    """角色决策分析：根据五维分数匹配角色并输出性格分析文本。

    参数：
        score_list : 长度为 5 的数字列表，顺序对应
                     [理性, 利他, 激进, 效率, 谨慎]（与 DIMENSIONS 对齐）
        theme      : 仅 cyber / magic / anime 三选一，对应三大板块
        movie_name : 精准影片名称字符串（如 "黑客帝国"、"哈利波特"）

    返回：
        str : 完整文本报告，分两段——
              第一段：客观打印全部五维分数；
              第二段：角色匹配 + 性格分析（复合型人格自动插入补充描述）。

    匹配策略：
        - 若角色条目含 vector 字段且非 null，优先使用余弦相似度匹配；
        - 否则使用原有的主次维度检索逻辑。
    """
    # ---------- 1. 入参校验 ----------
    if len(score_list) != DIM_COUNT:
        raise ValueError(
            f"score_list 长度必须为 {DIM_COUNT}（当前 {len(score_list)}），"
            f"顺序对应：{DIMENSIONS}"
        )
    # 使用 load_role_lib() 获取最新文案库（支持 roles.json 外置）
    _lib = load_role_lib()
    if theme not in _lib:
        raise ValueError(
            f"未知主题 '{theme}'，仅支持：{list(_lib.keys())}"
        )
    if movie_name not in _lib[theme]:
        raise ValueError(
            f"影片 '{movie_name}' 不在 {theme} 板块文案库中，"
            f"可选：{list(_lib[theme].keys())}"
        )

    # ---------- 2. 统一分数处理：使用 sanitize_score 规范化输入 ----------
    scores = [sanitize_score(s) for s in score_list]

    # ---------- 3. 向量相似度匹配（若角色含 vector 字段）----------
    movie_lib = _lib[theme][movie_name]
    use_vector_match = False
    matched_entry = None
    matched_dim = None

    # 检查该影片是否有任何角色配置了 vector
    has_vectors = any(
        isinstance(movie_lib.get(dim), dict) and movie_lib[dim].get("vector") is not None
        for dim in DIMENSIONS
    )

    if has_vectors:
        # 使用余弦相似度匹配最相近的角色
        best_sim = -2.0
        for dim in DIMENSIONS:
            entry = movie_lib[dim]
            if isinstance(entry, dict) and entry.get("vector") is not None:
                sim = cosine_similarity(scores, entry["vector"])
                if sim > best_sim:
                    best_sim = sim
                    matched_entry = entry
                    matched_dim = dim
        if matched_entry is not None:
            use_vector_match = True

    # ---------- 4. 传统主次维度匹配（回退方案）----------
    if not use_vector_match:
        # 五维分数排序，识别主导人格
        dim_score_pairs = list(zip(DIMENSIONS, scores))
        sorted_pairs = sorted(dim_score_pairs, key=lambda x: x[1], reverse=True)
        primary_dim, primary_score = sorted_pairs[0]
        secondary_dim, secondary_score = sorted_pairs[1]
        diff = primary_score - secondary_score
        is_compound = diff <= COMPOUND_THRESHOLD

        # 提取角色（兼容新旧格式）
        def _get_entry(dim):
            entry = movie_lib[dim]
            if isinstance(entry, dict):
                return entry["name"], entry["text"]
            elif isinstance(entry, tuple):
                return entry[0], entry[1]
            return str(entry), ""

        primary_role, primary_text = _get_entry(primary_dim)
        secondary_role, secondary_text = _get_entry(secondary_dim) if is_compound else (None, None)

        # ---------- 5. 组装报告（传统模式）----------
        report_lines = []
        report_lines.append("【第一段 · 五维决策分数】")
        report_lines.append("-" * 50)
        for dim, sc in zip(DIMENSIONS, scores):
            report_lines.append(f"  {dim}：{int(sc)} 分")
        report_lines.append("")

        report_lines.append("【第二段 · 角色匹配与性格分析】")
        report_lines.append("-" * 50)
        report_lines.append(f"  主导人格：{primary_dim}（{primary_score:.0f} 分）")
        report_lines.append(f"  匹配角色：{primary_role}")
        report_lines.append(f"  性格分析：{primary_text}")
        report_lines.append("")

        if is_compound:
            report_lines.append(f"  ⚡ 复合型人格检测：第一、二名差值 {diff:.0f} ≤ {COMPOUND_THRESHOLD}，"
                                f"判定为【{primary_dim} + {secondary_dim}】复合型。")
            report_lines.append(f"  次主导人格：{secondary_dim}（{secondary_score:.0f} 分）")
            report_lines.append(f"  次角色：{secondary_role}")
            report_lines.append(f"  补充分析：{secondary_text}")
            report_lines.append(f"  综合描述：你的决策风格以「{primary_dim}」为主基调，"
                                f"同时具备「{secondary_dim}」的调节能力，"
                                f"在不同情境下能在两种人格间灵活切换，但需警惕两者方向冲突时的内耗。")

        return "\n".join(report_lines)

    # ---------- 6. 向量匹配模式 ----------
    primary_role = matched_entry["name"]
    primary_text = matched_entry["text"]
    primary_dim = matched_dim
    vector_score = cosine_similarity(scores, matched_entry["vector"])

    report_lines = []
    report_lines.append("【第一段 · 五维决策分数】")
    report_lines.append("-" * 50)
    for dim, sc in zip(DIMENSIONS, scores):
        report_lines.append(f"  {dim}：{int(sc)} 分")
    report_lines.append("")

    report_lines.append("【第二段 · 角色匹配与性格分析】")
    report_lines.append("-" * 50)
    report_lines.append(f"  匹配方式：向量相似度匹配（余弦相似度 = {vector_score:.3f}）")
    report_lines.append(f"  匹配角色：{primary_role}（{primary_dim}维度）")
    report_lines.append(f"  性格分析：{primary_text}")

    return "\n".join(report_lines)


# ============================================================
# 六、自测代码：运行脚本自动生成三张主题预览图 + 角色分析测试
# ============================================================
if __name__ == "__main__":
    import os

    print("=" * 60)
    print("  score_draw.py 雷达图生成测试")
    print("=" * 60)

    # 测试数据 1：科幻赛博风（模拟典型激进型玩家）
    test_scores_cyber = [62, 45, 78, 70, 30]
    print(f"\n[1] 科幻赛博风  分数: {test_scores_cyber}")
    png1 = generate_radar(test_scores_cyber, theme="cyber")

    # 测试数据 2：魔幻风（含负数，验证归零逻辑）
    test_scores_magic = [55, -8, 40, 65, 80]   # 利他为 -8 → 自动修正为 0
    print(f"[2] 魔幻风      分数: {test_scores_magic}（利他 -8 → 修正为 0）")
    png2 = generate_radar(test_scores_magic, theme="magic")

    # 测试数据 3：动漫清新风（均衡型）
    test_scores_anime = [50, 50, 50, 50, 50]
    print(f"[3] 动漫清新风  分数: {test_scores_anime}（初始均衡型）")
    png3 = generate_radar(test_scores_anime, theme="anime")

    # 写入本地预览文件（仅测试代码行为，核心函数不落地本地）
    output_dir = os.path.dirname(os.path.abspath(__file__))
    for name, png in [("test_radar_cyber.png", png1),
                      ("test_radar_magic.png", png2),
                      ("test_radar_anime.png", png3)]:
        path = os.path.join(output_dir, name)
        with open(path, "wb") as f:
            f.write(png)
        print(f"  ✅ 已生成 {name}（{len(png)/1024:.1f} KB）")

    # 校验：确认返回的是 bytes 类型
    print(f"\n返回类型检查: {type(png1).__name__} → {isinstance(png1, bytes)}")

    # 与 parser.py 维度对齐校验（容错导入，避免与标准库冲突）
    try:
        # 优先尝试项目内的自定义 parser，避免与 Python 标准库 parser 冲突
        import sys
        _parser_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "parser.py")
        if os.path.exists(_parser_path):
            import importlib.util
            _spec = importlib.util.spec_from_file_location("project_parser", _parser_path)
            _parser = importlib.util.module_from_spec(_spec)
            _spec.loader.exec_module(_parser)
            align = _parser.DIMENSIONS == DIMENSIONS
            print(f"维度对齐 parser.py: {'✅ 一致' if align else '❌ 不一致'}")
            print(f"维度顺序: {DIMENSIONS}")
        else:
            print("⚠️ 未找到项目内 parser.py，跳过维度对齐校验")
    except Exception as e:
        print(f"⚠️ parser 导入异常（{e}），跳过维度对齐校验")

    print("\n" + "=" * 60)
    print("  雷达图测试完成，可在项目目录查看三张 test_radar_*.png 预览图")
    print("=" * 60)

    # ============================================================
    # 【新增区域】get_style_analysis 自测调用
    # ============================================================
    print("\n" + "=" * 60)
    print("  get_style_analysis 角色决策分析测试")
    print("=" * 60)

    # 测试1：科幻·黑客帝国·激进主导（复合型）
    print("\n--- 测试1: 科幻 / 黑客帝国 / 激进主导复合型 ---")
    analysis1 = get_style_analysis([62, 45, 78, 70, 30], theme="cyber", movie_name="黑客帝国")
    print(analysis1)

    # 测试2：科幻·黑客帝国·理性主导（单一型）
    print("\n--- 测试2: 科幻 / 黑客帝国 / 理性主导单一型 ---")
    analysis2 = get_style_analysis([88, 45, 50, 40, 30], theme="cyber", movie_name="黑客帝国")
    print(analysis2)

    # 测试3：含负数，验证归零（利他 -8 → 0）
    print("\n--- 测试3: 含负数归零验证 ---")
    analysis3 = get_style_analysis([55, -8, 40, 65, 80], theme="cyber", movie_name="黑客帝国")
    print(analysis3)

    print("\n" + "=" * 60)
    print("  get_style_analysis 测试完成")
    print("=" * 60)
