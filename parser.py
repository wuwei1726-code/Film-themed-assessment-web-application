"""影视世界观测评题库解析器（V0.04）。

将 Markdown 题库解析成可直接供 Flask 使用的结构化数据。支持：
阶段一三道 A/B 题、沙盘1资源分配、沙盘2 A/B 博弈、沙盘3五选三。
"""

from __future__ import annotations

import json
import os
import random
import re
from typing import Any

PARSER_VERSION = "V0.04"
DIMENSIONS = ["理性", "利他", "激进", "效率", "谨慎"]
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
QUESTION_BANK = os.path.join(BASE_DIR, "影视世界观决策测评总题库.md")

DIM_SCORE_RE = re.compile(r"(理性|利他|激进|效率|谨慎)\s*([+-]?\d+)")
BLOCK_RE = re.compile(r"^##\s+第[一二三]板块\s+(\S+?)世界观")
MOVIE_RE = re.compile(r"^###\s+《(.+?)》")
QTYPE_RE = re.compile(r"^####\s+(.+)")
WARMUP_RE = re.compile(r"^#####\s+热身题\s*(\d+)[：:]?\s*(.*)")
CHOICE_RE = re.compile(r"^\*\*([AB])\.\s*(.+?)\*\*\s*$")
NUMBERED_RE = re.compile(r"^(\d+)\.\s*(.+)")
SIMPLE_CHOICE_RE = re.compile(r"^([AB])[、.]\s*(.+?)\s*$")
INLINE_SCORE_RE = re.compile(r"^([AB])[：:]\s*(.+)$")

# 动漫三部影片的原始沙盘1只有定性描述。V0.04 补齐可复现的数值规则。
ANIME_ALLOCATION_RULES: dict[str, list[dict[str, int]]] = {
    "千与千寻": [
        {"效率": 12, "理性": 8, "利他": -6},
        {"利他": 13, "谨慎": 8, "效率": -8},
        {"谨慎": 13, "理性": 8, "激进": -10},
        {"激进": 12, "效率": 10, "谨慎": -8},
    ],
    "天气之子": [
        {"利他": 13, "效率": 9, "谨慎": -8},
        {"谨慎": 12, "理性": 10, "效率": -8},
        {"谨慎": 13, "理性": 8, "激进": -10},
        {"理性": 13, "效率": 10, "激进": -8},
    ],
    "疯狂动物城": [
        {"激进": 12, "效率": 10, "谨慎": -10},
        {"利他": 12, "谨慎": 9, "效率": -8},
        {"理性": 12, "效率": 10, "激进": -8},
        {"利他": 13, "谨慎": 8, "效率": -8},
    ],
}
ANIME_BALANCED = {"理性": 10, "谨慎": 8, "效率": 6, "激进": -8}
ANIME_SINGLE = {"激进": 12, "效率": 10, "谨慎": -14, "理性": -8}


def normalize_qtype(heading: str) -> str:
    match = re.match(r"^(沙盘\d|阶段[一二三四五六七八九十])", heading)
    return match.group(1) if match else heading.strip()


def empty_scores() -> dict[str, int]:
    return {dimension: 0 for dimension in DIMENSIONS}


def parse_scores(text: str) -> dict[str, int]:
    scores = empty_scores()
    for dimension, value in DIM_SCORE_RE.findall(text):
        scores[dimension] = int(value)
    return scores


def _option(option_id: str | int, text: str, scores: dict[str, int]) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": str(option_id),
        "seq": int(option_id) if str(option_id).isdigit() else str(option_id),
        "text": text.strip(),
        "scores": scores,
    }
    item.update(scores)
    return item


def _value_after_label(line: str, label: str) -> str | None:
    for pattern in (
        rf"^\*\*{re.escape(label)}\*\*[：:]\s*(.+)$",
        rf"^{re.escape(label)}[：:]\s*(.+)$",
    ):
        match = re.match(pattern, line.strip())
        if match:
            return match.group(1).strip()
    return None


def _split_sections(lines: list[str]) -> dict[tuple[str, str, str], list[str]]:
    sections: dict[tuple[str, str, str], list[str]] = {}
    block: str | None = None
    movie: str | None = None
    qtype: str | None = None
    for line in lines:
        match = BLOCK_RE.match(line)
        if match:
            block, movie, qtype = match.group(1), None, None
            continue
        match = MOVIE_RE.match(line)
        if match and block:
            movie, qtype = match.group(1), None
            continue
        match = QTYPE_RE.match(line)
        if match and block and movie:
            qtype = normalize_qtype(match.group(1))
            sections[(block, movie, qtype)] = []
            continue
        if block and movie and qtype:
            sections[(block, movie, qtype)].append(line.rstrip())
    return sections


def _parse_stage_one(lines: list[str]) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    current_option: dict[str, Any] | None = None

    def flush() -> None:
        nonlocal current
        if current:
            questions.append(current)
        current = None

    for raw in lines:
        line = raw.strip()
        match = WARMUP_RE.match(line)
        if match:
            flush()
            suffix = match.group(2).strip()
            current = {
                "id": f"warmup-{match.group(1)}",
                "title": f"热身题 {match.group(1)}" + (f"：{suffix}" if suffix else ""),
                "background": "",
                "options": [],
            }
            current_option = None
            continue
        if not current:
            continue
        background = _value_after_label(line, "背景")
        if background is not None:
            current["background"] = background
            continue
        match = CHOICE_RE.match(line)
        if match:
            current_option = _option(match.group(1), match.group(2), empty_scores())
            current["options"].append(current_option)
            continue
        match = SIMPLE_CHOICE_RE.match(line)
        if match:
            current_option = _option(match.group(1), match.group(2), empty_scores())
            current["options"].append(current_option)
            continue
        match = INLINE_SCORE_RE.match(line)
        if match:
            selected = next((option for option in current["options"] if option["id"] == match.group(1)), None)
            if selected:
                parsed = parse_scores(match.group(2))
                selected["scores"].update(parsed)
                selected.update(parsed)
                current_option = selected
            continue
        if current_option and line.startswith("-"):
            for dimension, value in parse_scores(line).items():
                if value:
                    current_option["scores"][dimension] = value
                    current_option[dimension] = value
    flush()
    return questions


def _parse_choice_section(lines: list[str]) -> dict[str, Any]:
    result: dict[str, Any] = {"theme": "", "scene": "", "options": []}
    current_option: dict[str, Any] | None = None
    options_by_id: dict[str, dict[str, Any]] = {}

    def new_option(option_id: str, text: str) -> dict[str, Any]:
        option = _option(option_id, text, empty_scores())
        option["_detail_lines"] = []
        result["options"].append(option)
        options_by_id[option_id] = option
        return option

    for raw in lines:
        line = raw.strip()
        if not line or line == "---":
            continue
        theme = _value_after_label(line, "主题")
        if theme is not None:
            result["theme"] = theme
            continue
        for label in ("场景", "背景"):
            scene = _value_after_label(line, label)
            if scene is not None:
                result["scene"] = scene
                break
        else:
            scene = None
        if scene is not None:
            continue
        match = CHOICE_RE.match(line)
        if match:
            current_option = new_option(match.group(1), match.group(2))
            continue
        match = SIMPLE_CHOICE_RE.match(line)
        if match:
            current_option = new_option(match.group(1), match.group(2))
            continue
        match = INLINE_SCORE_RE.match(line)
        if match and match.group(1) in options_by_id:
            current_option = options_by_id[match.group(1)]
            parsed = parse_scores(match.group(2))
            current_option["scores"].update(parsed)
            current_option.update(parsed)
            continue
        if current_option and line.startswith("-"):
            if DIM_SCORE_RE.search(line):
                for dimension, value in parse_scores(line).items():
                    if value:
                        current_option["scores"][dimension] = value
                        current_option[dimension] = value
            else:
                detail = line.lstrip("-").strip()
                if detail:
                    current_option["_detail_lines"].append(detail)
            continue
        if current_option and not re.match(r"^\*\*(分值|规则|说明)", line):
            current_option["_detail_lines"].append(line)
            continue
        if result["scene"] and not result["options"] and not line.startswith(("**", "#", "|")):
            result["scene"] += "\n" + line

    for option in result["options"]:
        detail_lines = option.pop("_detail_lines", [])
        option["detail"] = "\n".join(detail_lines)
    return result

def parse_option_line(line: str) -> tuple[int, str, str] | None:
    text = line.strip().strip("|")
    parts = [part.strip() for part in text.split("|")]
    if len(parts) >= 3 and parts[0].isdigit():
        return int(parts[0]), " | ".join(parts[1:-1]), parts[-1]
    return None


def _parse_sandbox_three(lines: list[str]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "theme": "",
        "background": "",
        "instruction": "",
        "select_count": 3,
        "options": [],
    }
    context_target: str | None = None
    for raw in lines:
        line = raw.strip()
        if not line or line == "---":
            continue
        theme = _value_after_label(line, "主题")
        if theme is not None:
            result["theme"] = theme
            context_target = None
            continue
        background = _value_after_label(line, "背景")
        if background is not None:
            result["background"] = background
            context_target = "background"
            continue
        instruction = _value_after_label(line, "规则")
        if instruction is not None:
            result["instruction"] = instruction
            context_target = "instruction"
            continue
        if _value_after_label(line, "信息池") is not None or re.match(r"^\*\*信息池\*\*[：:]?", line):
            context_target = None
            continue
        parsed = parse_option_line(line)
        if parsed:
            seq, text, score_text = parsed
            result["options"].append(_option(seq, text, parse_scores(score_text)))
            context_target = None
            continue
        if context_target and not line.startswith(("**", "#", "|")):
            result[context_target] += "\n" + line
    return result

def _parse_allocation(lines: list[str], movie: str) -> dict[str, Any]:
    result: dict[str, Any] = {"theme": "", "scene": "", "items": [], "rules": {}}
    collecting_items = False
    numeric_rule_lines: list[str] = []
    default_scores: dict[str, int] | None = None
    for raw in lines:
        line = raw.strip()
        theme = _value_after_label(line, "主题")
        if theme is not None:
            result["theme"] = theme
            continue
        scene = _value_after_label(line, "场景")
        if scene is not None:
            result["scene"] = scene
            continue
        if re.match(r"^\*\*四[项个]分配维度\*\*[：:]", line) or re.match(r"^四[项个]分配维度[：:]", line):
            collecting_items = True
            continue
        if re.match(r"^(\*\*)?规则(\*\*)?[：:]", line):
            collecting_items = False
            continue
        if collecting_items:
            match = NUMBERED_RE.match(line)
            if match:
                result["items"].append({"id": int(match.group(1)), "text": match.group(2).strip()})
            continue
        if line.startswith("-") and DIM_SCORE_RE.search(line):
            numeric_rule_lines.append(line)
        if "均衡方案计分" in line and DIM_SCORE_RE.search(line):
            default_scores = parse_scores(line.split("均衡方案计分", 1)[1])

    focus_rules: list[dict[str, Any]] = []
    balanced: dict[str, Any] | None = None
    single: dict[str, Any] | None = None
    for line in numeric_rule_lines:
        scores = parse_scores(line)
        balanced_match = re.search(r"四项分配较平均（每项\s*(\d+)\s*[-%至到]+\s*(\d+)%?）", line)
        single_match = re.search(r"单一领域超过\s*(\d+)%", line)
        threshold_match = re.search(r"[（(]>\s*(\d+)%[）)]", line)
        if balanced_match:
            balanced = {"min": int(balanced_match.group(1)), "max": int(balanced_match.group(2)), "scores": scores}
        elif single_match:
            single = {"threshold": int(single_match.group(1)), "scores": scores}
        elif threshold_match and len(focus_rules) < 4:
            focus_rules.append({"item_index": len(focus_rules), "threshold": int(threshold_match.group(1)), "scores": scores})

    if movie in ANIME_ALLOCATION_RULES:
        focus_rules = [
            {"item_index": index, "threshold": 35, "scores": {**empty_scores(), **scores}}
            for index, scores in enumerate(ANIME_ALLOCATION_RULES[movie])
        ]
        balanced = {"min": 20, "max": 30, "scores": {**empty_scores(), **ANIME_BALANCED}}
        single = {"threshold": 50, "scores": {**empty_scores(), **ANIME_SINGLE}}
    if default_scores is None and balanced:
        default_scores = dict(balanced["scores"])
    result["rules"] = {
        "priority": ["single", "balanced", "focus", "default"],
        "single": single,
        "balanced": balanced,
        "focus": focus_rules,
        "default": default_scores or empty_scores(),
    }
    return result


def validate_data(data: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if len(data) != 3:
        issues.append(f"应有 3 个世界观，实际为 {len(data)}")
    movie_count = sum(len(movies) for movies in data.values())
    if movie_count != 9:
        issues.append(f"应有 9 部影片，实际为 {movie_count}")
    for block, movies in data.items():
        for movie, stages in movies.items():
            prefix = f"{block}/{movie}"
            if len(stages.get("阶段一", [])) != 3:
                issues.append(f"{prefix}/阶段一不是 3 道题")
            elif any(len(question.get("options", [])) != 2 for question in stages["阶段一"]):
                issues.append(f"{prefix}/阶段一存在不是 2 个选项的题目")
            elif any(not question.get("background", "").strip() for question in stages["阶段一"]):
                issues.append(f"{prefix}/阶段一存在空背景")
            sandbox1 = stages.get("沙盘1", {})
            if len(sandbox1.get("items", [])) != 4 or len(sandbox1.get("rules", {}).get("focus", [])) != 4:
                issues.append(f"{prefix}/沙盘1资源或规则不完整")
            elif not sandbox1.get("scene", "").strip():
                issues.append(f"{prefix}/沙盘1场景为空")
            sandbox2 = stages.get("沙盘2", {})
            if len(sandbox2.get("options", [])) != 2:
                issues.append(f"{prefix}/沙盘2不是 2 个选项")
            elif not sandbox2.get("scene", "").strip():
                issues.append(f"{prefix}/沙盘2背景为空")
            sandbox3 = stages.get("沙盘3", {})
            if len(sandbox3.get("options", [])) != 5:
                issues.append(f"{prefix}/沙盘3不是 5 个选项")
            elif not sandbox3.get("background", "").strip():
                issues.append(f"{prefix}/沙盘3背景为空")
    return issues

def parse_file(filepath: str = QUESTION_BANK) -> tuple[dict[str, Any], list[tuple[str, dict[str, Any]]], list[str]]:
    with open(filepath, encoding="utf-8") as file:
        content = file.read()
    sections = _split_sections(content.splitlines())
    data: dict[str, Any] = {}
    for (block, movie, qtype), lines in sections.items():
        movie_data = data.setdefault(block, {}).setdefault(movie, {})
        if qtype == "阶段一":
            movie_data[qtype] = _parse_stage_one(lines)
        elif qtype == "沙盘1":
            movie_data[qtype] = _parse_allocation(lines, movie)
        elif qtype == "沙盘2":
            movie_data[qtype] = _parse_choice_section(lines)
        elif qtype == "沙盘3":
            movie_data[qtype] = _parse_sandbox_three(lines)
    flat_options: list[tuple[str, dict[str, Any]]] = []
    for block, movies in data.items():
        for movie, stages in movies.items():
            for question in stages.get("阶段一", []):
                for option in question["options"]:
                    flat_options.append((f"{block}/{movie}/阶段一/{question['id']}", option))
            for stage_name in ("沙盘2", "沙盘3"):
                for option in stages.get(stage_name, {}).get("options", []):
                    flat_options.append((f"{block}/{movie}/{stage_name}", option))
    return data, flat_options, validate_data(data)


parsed_data: dict[str, Any] = {}
all_options: list[tuple[str, dict[str, Any]]] = []
warnings: list[str] = []
load_error: Exception | None = None


def _load() -> None:
    global parsed_data, all_options, warnings, load_error
    try:
        parsed_data, all_options, warnings = parse_file()
        load_error = None
    except Exception as exc:
        parsed_data, all_options = {}, []
        warnings = [f"题库解析失败：{exc}"]
        load_error = exc


def assert_ready() -> None:
    if load_error:
        raise RuntimeError(f"题库加载失败：{load_error}") from load_error
    if warnings:
        raise RuntimeError("题库结构校验失败：" + "；".join(warnings))


def get_parsed_data() -> dict[str, Any]:
    return parsed_data


def get_warnings() -> list[str]:
    return warnings


_load()


def _print_debug() -> None:
    print(f"题库解析器 {PARSER_VERSION}")
    print(json.dumps({
        block: {
            movie: {
                "阶段一": len(stages["阶段一"]),
                "沙盘1": len(stages["沙盘1"]["items"]),
                "沙盘2": len(stages["沙盘2"]["options"]),
                "沙盘3": len(stages["沙盘3"]["options"]),
            }
            for movie, stages in movies.items()
        }
        for block, movies in parsed_data.items()
    }, ensure_ascii=False, indent=2))
    print(f"可计分选项：{len(all_options)}")
    if all_options:
        print("随机样例：", random.choice(all_options))
    print("校验：", "通过" if not warnings else warnings)


if __name__ == "__main__":
    _print_debug()
