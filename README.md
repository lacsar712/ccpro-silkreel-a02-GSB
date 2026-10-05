# SilkReel-01 · 江口缫丝坞

缫丝盆环状作业台。登录后看到的是沿汤池围成一圈的盆位，点盆登记汤温并改状态——不是侧栏双列表 CRUD。

## 技术栈

| 层 | 技术 |
| --- | --- |
| Web API | Quart（异步 Flask 族）· Hypercorn |
| 结构 | `repositories.py` 仓储 + `services.py` 门槛，路由不直接拼 SQL |
| 数据 | SQLAlchemy 2 async · asyncpg · PostgreSQL 15 |
| 前端 | Preact 10 · Vite |
| 部署 | Docker Compose |

## 路径与端口

- 前端：http://localhost:4760
- API：http://localhost:8760
- PostgreSQL：localhost:6160

## 演示账号

| 用户名 | 密码 | 角色 |
| --- | --- | --- |
| `admin` | `123456` | 管理员 |
| `worker` | `123456` | 缫丝工 |

## 业务规则

- 盆状态不可标成「已缫完」，除非该盆**最近一条**汤温记录落在 **38～42℃**。已缫完只看汤温带，帚次不掺进判断。
- 「浸茧」要改成「缫丝中」，该盆必须挂着一把**未报废且剩余次数 > 0** 的索绪帚；改成功会在**同一事务**里把剩余次数减 1，减到 0 后再改会被挡住。规则在 `backend/app/services.py`。
- 索绪帚字段：盆、帚号、剩余次数（正整数）、挂出时刻、报废时刻（可空）；同一盆最多一把未报废帚。缫丝工可在「索绪帚」专页挂出与报废，可按盆筛选。
- 种子数据里浸茧盆一把帚都没有，需先在帚专页挂出才能改缫丝中。

## 快速启动

```bash
cd SilkReel/SilkReel-01
docker compose up --build
```
