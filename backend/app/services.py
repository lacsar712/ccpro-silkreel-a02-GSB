"""缫丝盆门槛：标成已缫完须最近一次汤温落在 38～42℃；
改成缫丝中须该盆挂着未报废且剩余次数大于 0 的索绪帚，成功则同一事务扣 1 次。
两条门槛互不掺和：已缫完只看汤温带，不看帚次。"""

from app.models import Basin
from app.repositories import BrushRepo

MIN_TEMP = 38.0
MAX_TEMP = 42.0


class RuleError(ValueError):
    pass


def latest_temp(basin: Basin) -> float | None:
    if not basin.readings:
        return None
    latest = max(basin.readings, key=lambda r: r.taken_at)
    return latest.water_temp_c


def assert_can_set_status(basin: Basin, new_status: str) -> None:
    allowed = {Basin.STATUS_SOAKING, Basin.STATUS_REELING, Basin.STATUS_REELED}
    if new_status not in allowed:
        raise RuleError(f"无效状态：{new_status}")
    if new_status != Basin.STATUS_REELED:
        return
    temp = latest_temp(basin)
    if temp is None:
        raise RuleError("该盆尚无汤温记录，不能标已缫完")
    if temp < MIN_TEMP or temp > MAX_TEMP:
        raise RuleError(
            f"最近汤温 {temp}℃ 不在 {MIN_TEMP:.0f}～{MAX_TEMP:.0f}℃，不能标已缫完"
        )


async def consume_brush_for_reeling(brush_repo: BrushRepo, basin: Basin) -> None:
    """改成缫丝中的帚门槛：原子扣 1 次，由调用方与状态修改同一事务提交。

    减到 0 之后（或根本没挂未报废帚）再改一律挡住。
    """
    used = await brush_repo.consume_one(basin.id)
    if used is not None:
        return
    brush = await brush_repo.active_for_basin(basin.id)
    if brush is None:
        raise RuleError("该盆未挂未报废的索绪帚，不能改成缫丝中")
    raise RuleError(f"索绪帚 {brush.brush_no} 剩余次数已用完，不能改成缫丝中")
