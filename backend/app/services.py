"""缫丝盆门槛：

- 标成已缫完：只须最近一次汤温落在 38～42℃（帚次不得掺进此判断）。
- 改成缫丝中：该盆必须挂着一把未报废且剩余次数大于 0 的索绪帚，
  成功后在同一事务里把该帚剩余次数减 1。
"""

from app.models import Basin

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


def needs_brush_to_reel(basin: Basin, new_status: str) -> bool:
    """从非缫丝中改成缫丝中，须先挂可用的索绪帚；其余转换不看帚。"""
    return new_status == Basin.STATUS_REELING and basin.status != Basin.STATUS_REELING
