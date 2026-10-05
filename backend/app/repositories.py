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
                selectinload(Filature.basins).selectinload(Basin.readings),
                selectinload(Filature.basins).selectinload(Basin.brushes),
            )
        )
        return result.scalars().first()

    async def get(self, basin_id: int) -> Basin | None:
        result = await self.session.execute(
            select(Basin)
            .options(selectinload(Basin.readings), selectinload(Basin.brushes))
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

    async def list_active(self, basin_id: int | None = None) -> list[Brush]:
        stmt = (
            select(Brush)
            .options(selectinload(Brush.basin))
            .where(Brush.scrapped_at.is_(None))
            .order_by(Brush.id)
        )
        if basin_id is not None:
            stmt = stmt.where(Brush.basin_id == basin_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def active_for_basin(self, basin_id: int) -> Brush | None:
        result = await self.session.execute(
            select(Brush).where(Brush.basin_id == basin_id, Brush.scrapped_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def by_id(self, brush_id: int) -> Brush | None:
        result = await self.session.execute(
            select(Brush)
            .options(selectinload(Brush.basin))
            .where(Brush.id == brush_id)
        )
        return result.scalar_one_or_none()

    async def hang(self, basin: Basin, brush_no: str, remaining: int) -> Brush:
        row = Brush(basin=basin, brush_no=brush_no, remaining=remaining)
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def scrap(self, brush: Brush) -> None:
        brush.scrapped_at = utcnow()
        await self.session.commit()

    async def consume_one(self, basin_id: int) -> int | None:
        """原子地把该盆未报废帚的剩余次数减 1，返回帚 id；无帚或次数为 0 返回 None。

        不在此提交——必须与盆状态修改落在同一事务里，由调用方提交。
        并发下靠 `remaining > 0` 条件与行锁保证只剩 1 次时只有一笔能扣成功。
        """
        result = await self.session.execute(
            update(Brush)
            .where(
                Brush.basin_id == basin_id,
                Brush.scrapped_at.is_(None),
                Brush.remaining > 0,
            )
            .values(remaining=Brush.remaining - 1)
            .returning(Brush.id)
        )
        return result.scalar_one_or_none()
