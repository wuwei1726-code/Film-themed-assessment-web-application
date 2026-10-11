"""影视世界观决策测评系统 Flask 后端（V0.04）。"""

from __future__ import annotations

import os
from copy import deepcopy
from typing import Any

from flask import (
    Flask,
    Response,
    jsonify,
    request,
    session,
    url_for,
)

import parser
from score_draw import DIMENSIONS, generate_radar, get_style_analysis


VERSION = "V0.04"
INITIAL_SCORE = 50
STAGES = ("stage1", "sandbox1", "sandbox2", "sandbox3")
STAGE_LABELS = {
    "stage1": "阶段一 · 基础决策",
    "sandbox1": "沙盘1 · 资源分配",
    "sandbox2": "沙盘2 · 情景博弈",
    "sandbox3": "沙盘3 · 信息筛选",
}
STAGE_DATA_KEYS = {
    "stage1": "阶段一",
    "sandbox1": "沙盘1",
    "sandbox2": "沙盘2",
    "sandbox3": "沙盘3",
}

WORLD_META = {
    "科幻": {"theme": "cyber", "slug": "scifi", "description": "赛博霓虹与未来抉择"},
    "魔幻": {"theme": "magic", "slug": "fantasy", "description": "暗金魔法与命运考验"},
    "动漫": {"theme": "anime", "slug": "anime", "description": "清新色彩与成长选择"},
}
MOVIE_SLUGS = {
    "黑客帝国": "matrix",
    "银翼杀手": "blade-runner",
    "沙丘": "dune",
    "哈利波特": "harry-potter",
    "指环王": "lord-of-the-rings",
    "爱丽丝漫游仙境": "alice",
    "千与千寻": "spirited-away",
    "天气之子": "weathering-with-you",
    "疯狂动物城": "zootopia",
}

WORLD_SLUG_TO_NAME = {v["slug"]: k for k, v in WORLD_META.items()}
MOVIE_SLUG_TO_NAME = {v: k for k, v in MOVIE_SLUGS.items()}

def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    parser.assert_ready()

    app = Flask(__name__, static_folder='../frontend', static_url_path='')

    app.config.from_mapping(
        SECRET_KEY=os.environ.get(
            "SECRET_KEY",
            "v0.04-local-api-key-change-before-release",
        ),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        JSON_AS_ASCII=False,
        FRONTEND_ORIGIN=os.environ.get(
            "FRONTEND_ORIGIN",
            "http://127.0.0.1:5500",
        ),
    )

    if test_config:
        app.config.update(test_config)

    app.json.ensure_ascii = False

    @app.after_request
    def add_cors_headers(response: Response) -> Response:
        origin = str(app.config.get("FRONTEND_ORIGIN", "")).strip()

        if origin:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Headers"] = (
                "Content-Type, Accept"
            )
            response.headers["Access-Control-Allow-Methods"] = (
                "GET, POST, OPTIONS"
            )
            response.headers["Vary"] = "Origin"

        return response


    # 下面继续保留你原来的其他路由



    def error(message: str, status: int = 400):
        return jsonify({"ok": False, "error": message}), status
    def style_context() -> dict[str, Any]:
        world = session.get("world")
        movie = session.get("movie")
        meta = WORLD_META.get(world, {})
        return {
            "version": VERSION,
            "world": world,
            "movie": movie,
            "theme": meta.get("theme", "neutral"),
            "world_slug": meta.get("slug", "neutral"),
            "movie_slug": MOVIE_SLUGS.get(movie, "none"),
        }

    def selected_data() -> dict[str, Any] | None:
        world = session.get("world")
        movie = session.get("movie")
        return parser.parsed_data.get(world, {}).get(movie)

    def require_world():
        if session.get("world") not in parser.parsed_data:
            return error("请先选择世界观", 409)
        return None

    def require_movie():
        world_check = require_world()
        if world_check:
            return world_check
        world = session["world"]
        if session.get("movie") not in parser.parsed_data[world]:
            return error("请先选择影片", 409)
        return None
    def answers() -> dict[str, Any]:
        return deepcopy(session.get("answers", {}))

    def save_answer(stage: str, value: Any) -> None:
        stored = answers()
        stored[stage] = value
        session["answers"] = stored
        session.modified = True

    def first_incomplete() -> str | None:
        stored = answers()
        return next((stage for stage in STAGES if stage not in stored), None)

    def public_option(option: dict[str, Any]) -> dict[str, Any]:
        public = {"id": option["id"], "text": option["text"]}
        if option.get("detail"):
            public["detail"] = option["detail"]
        return public

    def public_stage(stage: str, stage_data: Any) -> Any:
        if stage == "stage1":
            return [
                {
                    "id": question["id"],
                    "title": question["title"],
                    "background": question["background"],
                    "options": [public_option(option) for option in question["options"]],
                }
                for question in stage_data
            ]
        if stage == "sandbox1":
            return {
                "theme": stage_data["theme"],
                "scene": stage_data["scene"],
                "items": stage_data["items"],
                "total": 100,
            }
        if stage == "sandbox2":
            return {
                "theme": stage_data["theme"],
                "scene": stage_data["scene"],
                "options": [public_option(option) for option in stage_data["options"]],
            }
        return {
            "theme": stage_data["theme"],
            "background": stage_data["background"],
            "instruction": stage_data.get("instruction", ""),
            "select_count": stage_data["select_count"],
            "options": [public_option(option) for option in stage_data["options"]],
        }

    def add_scores(target: dict[str, int], delta: dict[str, Any]) -> None:
        for dimension in DIMENSIONS:
            target[dimension] += int(delta.get(dimension, 0))

    def find_option(options: list[dict[str, Any]], option_id: str) -> dict[str, Any]:
        for option in options:
            if str(option["id"]) == str(option_id):
                return option
        raise ValueError(f"无效选项：{option_id}")

    def allocation_delta(stage_data: dict[str, Any], values: list[int]) -> dict[str, int]:
        if len(values) != 4 or any(value < 0 or value > 100 for value in values):
            raise ValueError("四项资源必须是 0 到 100 的整数")
        if sum(values) != 100:
            raise ValueError("四项资源百分比相加必须等于 100")
        rules = stage_data["rules"]
        maximum = max(values)
        highest_index = values.index(maximum)
        single = rules.get("single")
        if single and maximum > single["threshold"]:
            return single["scores"]
        balanced = rules.get("balanced")
        if balanced and all(balanced["min"] <= value <= balanced["max"] for value in values):
            return balanced["scores"]
        focus_rules = rules.get("focus", [])
        if highest_index < len(focus_rules):
            focus = focus_rules[highest_index]
            if maximum > focus["threshold"]:
                return focus["scores"]
        return rules["default"]

    def calculate_scores() -> tuple[dict[str, int], dict[str, int]]:
        data = selected_data()
        if not data:
            raise ValueError("尚未选择有效影片")
        stored = answers()
        raw = {dimension: INITIAL_SCORE for dimension in DIMENSIONS}

        for question in data["阶段一"]:
            choice = stored.get("stage1", {}).get(question["id"])
            if choice is not None:
                add_scores(raw, find_option(question["options"], choice)["scores"])
        if "sandbox1" in stored:
            add_scores(raw, allocation_delta(data["沙盘1"], stored["sandbox1"]))
        if "sandbox2" in stored:
            add_scores(raw, find_option(data["沙盘2"]["options"], stored["sandbox2"])["scores"])
        for choice in stored.get("sandbox3", []):
            add_scores(raw, find_option(data["沙盘3"]["options"], choice)["scores"])
        final = {dimension: max(0, min(100, value)) for dimension, value in raw.items()}
        return raw, final

    def stage_submission(stage: str, stage_data: Any) -> Any:
        payload = request.get_json(silent=True) if request.is_json else None
        payload = payload or request.form
        if stage == "stage1":
            submitted = payload.get("answers") if isinstance(payload, dict) else None
            if submitted is None:
                submitted = {question["id"]: request.form.get(question["id"]) for question in stage_data}
            if not isinstance(submitted, dict):
                raise ValueError("阶段一答案格式错误")
            cleaned: dict[str, str] = {}
            for question in stage_data:
                choice = submitted.get(question["id"])
                if choice is None:
                    raise ValueError("阶段一的 3 道题都必须作答")
                find_option(question["options"], str(choice))
                cleaned[question["id"]] = str(choice)
            return cleaned
        if stage == "sandbox1":
            submitted = (payload.get("answers") or payload.get("allocations")) if isinstance(payload, dict) else None
            if submitted is None:
                submitted = [request.form.get(f"allocation_{index}") for index in range(1, 5)]
            if not isinstance(submitted, (list, tuple)) or len(submitted) != 4:
                raise ValueError("需要提交 4 项资源百分比")
            try:
                values = [int(value) for value in submitted]
            except (TypeError, ValueError) as exc:
                raise ValueError("资源百分比必须为整数") from exc
            allocation_delta(stage_data, values)
            return values
        if stage == "sandbox2":
            choice = (payload.get("answers") or payload.get("choice"))
            if not choice:
                raise ValueError("请选择一个博弈方案")
            find_option(stage_data["options"], str(choice))
            return str(choice)
        submitted = (payload.get("answers") or payload.get("choices")) if request.is_json and isinstance(payload, dict) else request.form.getlist("choices")
        if not isinstance(submitted, (list, tuple)):
            raise ValueError("信息筛选答案格式错误")
        choices = [str(choice) for choice in submitted]
        if len(choices) != stage_data["select_count"] or len(set(choices)) != len(choices):
            raise ValueError(f"必须选择 {stage_data['select_count']} 条不同的信息")
        for choice in choices:
            find_option(stage_data["options"], choice)
        return choices


    from flask import send_from_directory
    
    @app.get("/")
    def index():
        from flask import send_from_directory
        return send_from_directory(app.static_folder, "index.html")

    @app.get("/api/info")  # 改个路径，或者直接删掉这个路由
    def api_info():
        return jsonify({
            "ok": True,
            "service": "影视世界观决策测评后端 API",
            "version": VERSION,
            "health": "/health",
            "worlds": "/api/worlds",
            "documentation": "后端接口文档.md",
        })

    @app.route("/api/quiz/<stage>", methods=["GET", "POST"])
    def quiz(stage: str):
        if stage not in STAGES:
            return error("不存在的答题阶段", 404)
        blocked = require_movie()
        if blocked:
            return blocked
        data = selected_data()
        assert data is not None
        current_index = STAGES.index(stage)
        incomplete = first_incomplete()
        if request.method == "GET" and incomplete and current_index > STAGES.index(incomplete):
            return error(f"请先完成 {STAGE_LABELS[incomplete]}", 409)
        stage_data = data[STAGE_DATA_KEYS[stage]]
        if request.method == "POST":
            try:
                save_answer(stage, stage_submission(stage, stage_data))
            except ValueError as exc:
                return error(str(exc), 400)
            next_stage = STAGES[current_index + 1] if current_index + 1 < len(STAGES) else None
            raw, final = calculate_scores()
            return jsonify({
                "ok": True,
                "saved": stage,
                "next": f"/api/quiz/{next_stage}" if next_stage else "/api/result",
                "current_scores": final,
                "raw_scores": raw,
            })
        response_data = public_stage(stage, stage_data)
        return jsonify({
            "ok": True,
            "stage": stage,
            "label": STAGE_LABELS[stage],
            "step": current_index + 1,
            "total_steps": len(STAGES),
            "style": style_context(),
            "data": response_data,
            "saved_answer": answers().get(stage),
        })
    def result_payload() -> dict[str, Any]:
        raw, final = calculate_scores()
        score_list = [final[dimension] for dimension in DIMENSIONS]
        context = style_context()
        return {
            "ok": True,
            "version": VERSION,
            "world": context["world"],
            "movie": context["movie"],
            "theme": context["theme"],
            "movie_slug": context["movie_slug"],
            "dimensions": DIMENSIONS,
            "scores": final,
            "score_list": score_list,
            "raw_scores": raw,
            "analysis": get_style_analysis(score_list, context["theme"], context["movie"]),
            "radar_url": url_for("radar_png"),
        }

    @app.get("/api/result")
    def result():
        blocked = require_movie()
        if blocked:
            return blocked
        incomplete = first_incomplete()
        if incomplete:
            return error(f"请先完成 {STAGE_LABELS[incomplete]}", 409)
        return jsonify(result_payload())
    @app.get("/radar.png")
    def radar_png():
        blocked = require_movie()
        if blocked:
            return blocked
        if first_incomplete():
            return error("完成全部答题后才能生成雷达图", 409)
        payload = result_payload()
        png = generate_radar(payload["score_list"], payload["theme"], title=f"{payload['movie']} · 决策倾向")
        response = Response(png, mimetype="image/png")
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/worlds")
    def api_worlds():
        worlds = []
        for world, movies in parser.parsed_data.items():
            worlds.append({
                "name": world,
                **WORLD_META[world],
                "movies": [{"name": movie, "slug": MOVIE_SLUGS[movie]} for movie in movies],
            })
        return jsonify({"ok": True, "version": VERSION, "worlds": worlds})

    @app.post("/api/selection")
    def api_selection():
        payload = request.get_json(silent=True) or {}
        world_slug = payload.get("world")
        movie_slug = payload.get("movie")

        # 把前端传来的 slug 转换成后端内部使用的中文 key
        world = WORLD_SLUG_TO_NAME.get(world_slug, world_slug)
        movie = MOVIE_SLUG_TO_NAME.get(movie_slug, movie_slug) if movie_slug else None

        if world not in parser.parsed_data:
            return error("无效的世界观")
        if movie is not None and movie not in parser.parsed_data[world]:
            return error("该影片不属于当前世界观")
        session.clear()
        session["world"] = world
        if movie:
            session["movie"] = movie
            session["answers"] = {}
        return jsonify({"ok": True, "selection": style_context(), "next": "/api/quiz/stage1" if movie else None})

    
    @app.post("/api/reset")
    def reset():
        session.clear()
        return jsonify({"ok": True})
    @app.get("/health")
    def health():
        return jsonify({
            "ok": True,
            "version": VERSION,
            "worlds": len(parser.parsed_data),
            "movies": sum(len(movies) for movies in parser.parsed_data.values()),
            "parser_warnings": parser.warnings,
        })

    @app.errorhandler(404)
    def not_found(_exc):
        return error("页面不存在", 404)

    @app.errorhandler(405)
    def method_not_allowed(_exc):
        return error("请求方法不允许", 405)

    @app.errorhandler(500)
    def server_error(_exc):
        return error("服务器内部错误，请检查终端日志", 500)

    return app


app = create_app()


if __name__ == "__main__":
    print(app.url_map)
    app.run(
        host="127.0.0.1",
        port=int(os.environ.get("APP_PORT", "5002")),
        debug=os.environ.get("FLASK_DEBUG") == "1",
    )

