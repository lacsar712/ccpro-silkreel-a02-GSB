from quart import Quart, g, jsonify, request
from sqlalchemy.exc import IntegrityError

from app.db import SessionLocal
from app.models import Basin, Brush
from app.repositories import BasinRepo, BrushRepo, UserRepo
from app.security import make_token, parse_token, verify_password
from app.services import RuleError, assert_can_set_status, latest_temp, needs_brush_to_reel

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


def _brush_json(brush: Brush, basin_code: str | None = None) -> dict:
    return {
        "id": brush.id,
        "basinId": brush.basin_id,
        "basinCode": basin_code,
        "brushNo": brush.brush_no,
        "remaining": brush.remaining,
        "hungAt": brush.hung_at.isoformat() if brush.hung_at else None,
        "discardedAt": brush.discarded_at.isoformat() if brush.discarded_at else None,
    }


def _basin_json(basin: Basin, brush: Brush | None = None) -> dict:
    return {
        "id": basin.id,
        "code": basin.code,
        "status": basin.status,
        "ringIndex": basin.ring_index,
        "latestTempC": latest_temp(basin),
        "readingCount": len(basin.readings or []),
        "brush": _brush_json(brush, basin.code) if brush else None,
    }


async def _basin_payload(session, basin: Basin) -> dict:
    brush = await BrushRepo(session).active_for_basin(basin.id)
    return _basin_json(basin, brush)


@app.route("/api/board")
async def board():
    denied = require_user()
    if denied:
        return denied
    async with SessionLocal() as session:
        mill = await BasinRepo(session).board()
        if mill is None:
            return jsonify({"detail": "尚无缫丝坞"}), 404
        brushes = await BrushRepo(session).list_active()
        brush_by_basin = {b.basin_id: b for b in brushes}
        basins = sorted(mill.basins, key=lambda b: b.ring_index)
        return {
            "filature": mill.name,
            "riverside": mill.riverside,
            "basins": [_basin_json(b, brush_by_basin.get(b.id)) for b in basins],
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
        return await _basin_payload(session, basin)


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
        except RuleError as exc:
            return jsonify({"detail": str(exc)}), 400
        if needs_brush_to_reel(basin, status):
            # 同一事务：先原子扣该盆未报废帚的剩余次数，扣不动就挡住。
            brush = await BrushRepo(session).consume_for_reeling(basin_id)
            if brush is None:
                await session.rollback()
                return jsonify(
                    {"detail": "该盆未挂未报废且剩余次数大于 0 的索绪帚，不能改成缫丝中"}
                ), 400
        await repo.save_status(basin, status)
        basin = await repo.get(basin_id)
        return await _basin_payload(session, basin)


@app.route("/api/brushes")
async def list_brushes():
    denied = require_user()
    if denied:
        return denied
    basin_id = request.args.get("basinId", type=int)
    async with SessionLocal() as session:
        brushes = await BrushRepo(session).list_active(basin_id)
        mill = await BasinRepo(session).board()
        codes = {b.id: b.code for b in (mill.basins if mill else [])}
        return {"brushes": [_brush_json(b, codes.get(b.basin_id)) for b in brushes]}


@app.route("/api/brushes", methods=["POST"])
async def hang_brush():
    denied = require_user()
    if denied:
        return denied
    body = await request.get_json(force=True) or {}
    basin_id = body.get("basinId")
    brush_no = body.get("brushNo")
    remaining = body.get("remaining")
    if isinstance(basin_id, bool) or not isinstance(basin_id, int):
        return jsonify({"detail": "盆必填"}), 400
    if not isinstance(brush_no, str) or not brush_no.strip():
        return jsonify({"detail": "帚号必填"}), 400
    if isinstance(remaining, bool) or not isinstance(remaining, int) or remaining < 1:
        return jsonify({"detail": "剩余次数须为正整数"}), 400
    async with SessionLocal() as session:
        basin = await BasinRepo(session).get(basin_id)
        if basin is None:
            return jsonify({"detail": "盆不存在"}), 404
        brepo = BrushRepo(session)
        if await brepo.active_for_basin(basin_id) is not None:
            return jsonify({"detail": "该盆已挂着一把未报废的索绪帚"}), 400
        try:
            row = await brepo.hang(basin, brush_no.strip(), remaining)
        except IntegrityError:
            await session.rollback()
            return jsonify({"detail": "该盆已挂着一把未报废的索绪帚"}), 400
        return _brush_json(row, basin.code), 201


@app.route("/api/brushes/<int:brush_id>/discard", methods=["POST"])
async def discard_brush(brush_id: int):
    denied = require_user()
    if denied:
        return denied
    async with SessionLocal() as session:
        brepo = BrushRepo(session)
        brush = await brepo.get(brush_id)
        if brush is None:
            return jsonify({"detail": "帚不存在"}), 404
        await brepo.discard(brush)
        return _brush_json(brush)
