from quart import Quart, g, jsonify, request

from sqlalchemy.exc import IntegrityError

from app.db import SessionLocal
from app.models import Basin, Brush
from app.repositories import BasinRepo, BrushRepo, UserRepo
from app.security import make_token, parse_token, verify_password
from app.services import (
    RuleError,
    assert_can_set_status,
    consume_brush_for_reeling,
    latest_temp,
)

app = Quart(__name__)


def _bearer() -> str | None:
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[7:]
    return None


@app.before_request
async def load_user():
    g.user = None
    token = _bearer()
    if not token:
        return
    username = parse_token(token)
    if not username:
        return
    async with SessionLocal() as session:
        g.user = await UserRepo(session).by_username(username)


def require_user():
    if g.user is None:
        return jsonify({"detail": "未登录"}), 401
    return None


@app.route("/api/health")
async def health():
    return {"status": "ok", "service": "SilkReel"}


@app.route("/api/auth/login", methods=["POST"])
async def login():
    body = await request.get_json(force=True)
    username = (body or {}).get("username", "")
    password = (body or {}).get("password", "")
    async with SessionLocal() as session:
        user = await UserRepo(session).by_username(username)
        if user is None or not verify_password(password, user.password_hash):
            return jsonify({"detail": "用户名或密码错误"}), 401
        return {
            "access_token": make_token(user.username),
            "user": {"username": user.username, "role": user.role},
        }


@app.route("/api/auth/me")
async def me():
    denied = require_user()
    if denied:
        return denied
    return {"username": g.user.username, "role": g.user.role}


def _active_brush(basin: Basin) -> Brush | None:
    for brush in basin.brushes or []:
        if brush.scrapped_at is None:
            return brush
    return None


def _basin_json(basin: Basin) -> dict:
    brush = _active_brush(basin)
    return {
        "id": basin.id,
        "code": basin.code,
        "status": basin.status,
        "ringIndex": basin.ring_index,
        "latestTempC": latest_temp(basin),
        "readingCount": len(basin.readings or []),
        "brush": (
            {"id": brush.id, "brushNo": brush.brush_no, "remaining": brush.remaining}
            if brush is not None
            else None
        ),
    }


def _brush_json(brush: Brush) -> dict:
    return {
        "id": brush.id,
        "basinId": brush.basin_id,
        "basinCode": brush.basin.code if brush.basin is not None else None,
        "brushNo": brush.brush_no,
        "remaining": brush.remaining,
        "hungAt": brush.hung_at.isoformat() if brush.hung_at else None,
        "scrappedAt": brush.scrapped_at.isoformat() if brush.scrapped_at else None,
    }


@app.route("/api/board")
async def board():
    denied = require_user()
    if denied:
        return denied
    async with SessionLocal() as session:
        mill = await BasinRepo(session).board()
        if mill is None:
            return jsonify({"detail": "尚无缫丝坞"}), 404
        basins = sorted(mill.basins, key=lambda b: b.ring_index)
        return {
            "filature": mill.name,
            "riverside": mill.riverside,
            "basins": [_basin_json(b) for b in basins],
        }


@app.route("/api/basins/<int:basin_id>/readings", methods=["POST"])
async def add_reading(basin_id: int):
    denied = require_user()
    if denied:
        return denied
    body = await request.get_json(force=True)
    try:
        temp = float((body or {}).get("waterTempC"))
    except (TypeError, ValueError):
        return jsonify({"detail": "汤温必须是数字"}), 400
    async with SessionLocal() as session:
        repo = BasinRepo(session)
        basin = await repo.get(basin_id)
        if basin is None:
            return jsonify({"detail": "盆不存在"}), 404
        await repo.add_reading(basin, temp, g.user.username)
        basin = await repo.get(basin_id)
        return _basin_json(basin)


@app.route("/api/basins/<int:basin_id>/status", methods=["POST"])
async def set_status(basin_id: int):
    denied = require_user()
    if denied:
        return denied
    body = await request.get_json(force=True)
    status = (body or {}).get("status", "")
    async with SessionLocal() as session:
        repo = BasinRepo(session)
        basin = await repo.get(basin_id)
        if basin is None:
            return jsonify({"detail": "盆不存在"}), 404
        try:
            assert_can_set_status(basin, status)
            if status == Basin.STATUS_REELING:
                # 改成缫丝中：先扣该盆未报废帚的剩余次数，与状态修改同一事务提交
                await consume_brush_for_reeling(BrushRepo(session), basin)
        except RuleError as exc:
            return jsonify({"detail": str(exc)}), 400
        await repo.save_status(basin, status)
        session.expire_all()
        basin = await repo.get(basin_id)
        return _basin_json(basin)


def _as_int(value) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    return None


def _positive_int(value) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        num = value
    elif isinstance(value, float) and value.is_integer():
        num = int(value)
    elif isinstance(value, str) and value.strip().isdigit():
        num = int(value.strip())
    else:
        return None
    return num if num > 0 else None


@app.route("/api/brushes")
async def list_brushes():
    denied = require_user()
    if denied:
        return denied
    raw = request.args.get("basinId") or request.args.get("basin_id")
    basin_id = None
    if raw not in (None, ""):
        basin_id = _as_int(raw)
        if basin_id is None:
            return jsonify({"detail": "basinId 必须是整数"}), 400
    async with SessionLocal() as session:
        brushes = await BrushRepo(session).list_active(basin_id)
        return {"brushes": [_brush_json(b) for b in brushes]}


@app.route("/api/brushes", methods=["POST"])
async def hang_brush():
    denied = require_user()
    if denied:
        return denied
    body = await request.get_json(force=True) or {}
    basin_id = _as_int(body.get("basinId", body.get("basin_id")))
    if basin_id is None:
        return jsonify({"detail": "盆位无效"}), 400
    brush_no = str(body.get("brushNo") or body.get("brush_no") or "").strip()
    if not brush_no:
        return jsonify({"detail": "帚号不能为空"}), 400
    remaining = _positive_int(
        body.get("remaining", body.get("remainingUses", body.get("remaining_uses")))
    )
    if remaining is None:
        return jsonify({"detail": "剩余次数须为正整数"}), 400
    async with SessionLocal() as session:
        basin = await BasinRepo(session).get(basin_id)
        if basin is None:
            return jsonify({"detail": "盆不存在"}), 404
        repo = BrushRepo(session)
        if await repo.active_for_basin(basin.id) is not None:
            return jsonify({"detail": "该盆已挂着未报废的索绪帚"}), 400
        try:
            brush = await repo.hang(basin, brush_no, remaining)
        except IntegrityError:
            # 并发挂同一只盆：局部唯一索引兜底，只许一把未报废帚
            await session.rollback()
            return jsonify({"detail": "该盆已挂着未报废的索绪帚"}), 400
        return jsonify(_brush_json(brush)), 201


@app.route("/api/brushes/<int:brush_id>/scrap", methods=["POST"])
async def scrap_brush(brush_id: int):
    denied = require_user()
    if denied:
        return denied
    async with SessionLocal() as session:
        repo = BrushRepo(session)
        brush = await repo.by_id(brush_id)
        if brush is None:
            return jsonify({"detail": "帚不存在"}), 404
        if brush.scrapped_at is not None:
            return jsonify({"detail": "该帚已报废"}), 400
        await repo.scrap(brush)
        return jsonify(_brush_json(brush))
