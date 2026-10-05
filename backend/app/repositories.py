from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Basin, BathReading, Brush, Filature, User, utcnow


class UserRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def by_username(self, username: str) -> User | None:
        result = await self.session.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()


class BasinRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def board(self) -> Filature | None:
        result = await self.session.execute(
            select(Filature).options(
                selectinload(Filature.basins).selectinload(Basin.readings)
            )
        )
        return result.scalars().first()

    async def get(self, basin_id: int) -> Basin | None:
        result = await self.session.execute(
            select(Basin)
            .options(selectinload(Basin.readings))
            .where(Basin.id == basin_id)
        )
        return result.scalar_one_or_none()

    async def add_reading(self, basin: Basin, temp_c: float, operator: str) -> BathReading:
        row = BathReading(basin=basin, water_temp_c=temp_c, operator=operator)
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def save_status(self, basin: Basin, status: str) -> None:
        basin.status = status
        await self.session.commit()


class BrushRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, brush_id: int) -> Brush | None:
        result = await self.session.execute(select(Brush).where(Brush.id == brush_id))
        return result.scalar_one_or_none()

    async def list_active(self, basin_id: int | None = None) -> list[Brush]:
        stmt = (
            select(Brush)
            .where(Brush.discarded_at.is_(None))
            .order_by(Brush.hung_at.desc(), Brush.id.desc())
        )
        if basin_id is not None:
            stmt = stmt.where(Brush.basin_id == basin_id)
        result = await self.session.execute(stmt)
        return list(result.scalars())

    async def active_for_basin(self, basin_id: int) -> Brush | None:
        result = await self.session.execute(
            select(Brush).where(
                Brush.basin_id == basin_id,
                Brush.discarded_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def hang(self, basin: Basin, brush_no: str, remaining: int) -> Brush:
        row = Brush(basin=basin, brush_no=brush_no, remaining=remaining)
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def discard(self, brush: Brush) -> Brush:
        if brush.discarded_at is None:
            brush.discarded_at = utcnow()
            await self.session.commit()
        return brush

    async def consume_for_reeling(self, basin_id: int) -> Brush | None:
        """原子扣减：仅当该盆有未报废且剩余次数大于 0 的帚时减 1。

        单条 UPDATE 带 WHERE remaining > 0，并发下只有一个事务能把
        最后 1 次减成 0，其余匹配不到行而失败。
        """
        result = await self.session.execute(
            update(Brush)
            .where(
                Brush.basin_id == basin_id,
                Brush.discarded_at.is_(None),
                Brush.remaining > 0,
            )
            .values(remaining=Brush.remaining - 1)
            .returning(Brush)
        )
        return result.scalar_one_or_none()
