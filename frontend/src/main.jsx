import { render } from "preact";
import { useEffect, useState } from "preact/hooks";
import { api, clearToken, setToken, token } from "./api.js";
import "./app.css";

const STATUS_LABEL = { soaking: "浸茧", reeling: "缫丝中", reeled: "已缫完" };

function Login({ onOk }) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("123456");
  const [err, setErr] = useState("");
  async function submit(e) {
    e.preventDefault();
    setErr("");
    try {
      const data = await api("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      setToken(data.access_token);
      onOk();
    } catch (ex) {
      setErr(ex.message);
    }
  }
  return (
    <div class="login">
      <h1>江口缫丝坞</h1>
      <p>汤温环盆作业台，不是列表台账。</p>
      <form onSubmit={submit} autocomplete="off">
        <label>
          用户名
          <input name="username" autocomplete="off" value={username} onInput={(e) => setUsername(e.target.value)} />
        </label>
        <label>
          密码
          <input name="password" type="password" autocomplete="off" value={password} onInput={(e) => setPassword(e.target.value)} />
        </label>
        <p class="hint">已预填 admin / 123456，另有 worker / 123456</p>
        <button type="submit">登录</button>
      </form>
      {err && <p class="err">{err}</p>}
    </div>
  );
}

function Yard() {
  const [board, setBoard] = useState(null);
  const [picked, setPicked] = useState(null);
  const [temp, setTemp] = useState("40");
  const [err, setErr] = useState("");

  async function refresh() {
    const data = await api("/api/board");
    setBoard(data);
    if (picked) {
      setPicked(data.basins.find((b) => b.id === picked.id) || data.basins[0]);
    }
  }

  useEffect(() => {
    refresh().catch((e) => setErr(e.message));
  }, []);

  if (!board) {
    return (
      <div>
        {err || "装载环盆…"}
      </div>
    );
  }

  const n = board.basins.length;
  async function writeTemp() {
    setErr("");
    try {
      const row = await api(`/api/basins/${picked.id}/readings`, {
        method: "POST",
        body: JSON.stringify({ waterTempC: Number(temp) }),
      });
      await refresh();
      setPicked(row);
    } catch (ex) {
      setErr(ex.message);
    }
  }
  async function setStatus(status) {
    setErr("");
    try {
      const row = await api(`/api/basins/${picked.id}/status`, {
        method: "POST",
        body: JSON.stringify({ status }),
      });
      await refresh();
      setPicked(row);
    } catch (ex) {
      setErr(ex.message);
    }
  }

  return (
    <div>
      <p class="hint">{board.riverside} · 点盆登记汤温；已缫完须最近汤温 38～42℃；浸茧改缫丝中须先挂索绪帚</p>
      <div class="ring">
        {board.basins.map((b, i) => {
          const angle = (Math.PI * 2 * i) / n - Math.PI / 2;
          const left = 50 + Math.cos(angle) * 38;
          const top = 50 + Math.sin(angle) * 38;
          return (
            <button
              key={b.id}
              class={`basin ${b.status}`}
              style={{ left: `${left}%`, top: `${top}%` }}
              onClick={() => setPicked(b)}
            >
              <strong>{b.code}</strong>
              <span>{STATUS_LABEL[b.status]}</span>
            </button>
          );
        })}
      </div>
      {picked && (
        <div class="drawer">
          <h3>
            {picked.code} · {STATUS_LABEL[picked.status]}
          </h3>
          <p>最近汤温：{picked.latestTempC ?? "无"} ℃ · 记录 {picked.readingCount} 次</p>
          <p>
            索绪帚：
            {picked.brush
              ? `${picked.brush.brushNo} · 剩 ${picked.brush.remaining} 次`
              : "未挂帚"}
          </p>
          <input value={temp} onInput={(e) => setTemp(e.target.value)} />
          <button onClick={writeTemp}>登记汤温</button>
          <div>
            <button onClick={() => setStatus("soaking")}>浸茧</button>
            <button onClick={() => setStatus("reeling")}>缫丝中</button>
            <button onClick={() => setStatus("reeled")}>已缫完</button>
          </div>
          {err && <p class="err">{err}</p>}
        </div>
      )}
    </div>
  );
}

function Brushes() {
  const [basins, setBasins] = useState([]);
  const [brushes, setBrushes] = useState([]);
  const [filter, setFilter] = useState("");
  const [basinId, setBasinId] = useState("");
  const [brushNo, setBrushNo] = useState("");
  const [remaining, setRemaining] = useState("3");
  const [err, setErr] = useState("");

  async function loadBrushes(basinFilter) {
    const q = basinFilter ? `?basinId=${basinFilter}` : "";
    const data = await api(`/api/brushes${q}`);
    setBrushes(data.brushes);
  }

  useEffect(() => {
    (async () => {
      try {
        const board = await api("/api/board");
        setBasins(board.basins);
        await loadBrushes("");
      } catch (ex) {
        setErr(ex.message);
      }
    })();
  }, []);

  async function changeFilter(e) {
    const value = e.target.value;
    setFilter(value);
    setErr("");
    try {
      await loadBrushes(value);
    } catch (ex) {
      setErr(ex.message);
    }
  }

  async function hang(e) {
    e.preventDefault();
    setErr("");
    try {
      await api("/api/brushes", {
        method: "POST",
        body: JSON.stringify({
          basinId: Number(basinId),
          brushNo,
          remaining: Number(remaining),
        }),
      });
      setBrushNo("");
      await loadBrushes(filter);
    } catch (ex) {
      setErr(ex.message);
    }
  }

  async function discard(id) {
    setErr("");
    try {
      await api(`/api/brushes/${id}/discard`, { method: "POST" });
      await loadBrushes(filter);
    } catch (ex) {
      setErr(ex.message);
    }
  }

  return (
    <div class="drawer">
      <h3>索绪帚</h3>
      <p class="hint">浸茧改成缫丝中前，该盆须挂着未报废且剩余次数大于 0 的帚；每改一次扣一次。</p>
      <form class="brush-form" onSubmit={hang}>
        <select value={basinId} onChange={(e) => setBasinId(e.target.value)} required>
          <option value="">选盆</option>
          {basins.map((b) => (
            <option key={b.id} value={b.id}>
              {b.code}（{STATUS_LABEL[b.status]}）
            </option>
          ))}
        </select>
        <input
          placeholder="帚号"
          value={brushNo}
          onInput={(e) => setBrushNo(e.target.value)}
          required
        />
        <input
          type="number"
          min="1"
          step="1"
          placeholder="剩余次数"
          value={remaining}
          onInput={(e) => setRemaining(e.target.value)}
          required
        />
        <button type="submit">挂出</button>
      </form>
      <p>
        <label class="inline">
          按盆筛：
          <select value={filter} onChange={changeFilter}>
            <option value="">全部盆</option>
            {basins.map((b) => (
              <option key={b.id} value={b.id}>
                {b.code}
              </option>
            ))}
          </select>
        </label>
      </p>
      <table class="brush-table">
        <thead>
          <tr>
            <th>帚号</th>
            <th>盆</th>
            <th>剩余次数</th>
            <th>挂出时刻</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {brushes.length === 0 && (
            <tr>
              <td colspan="5">暂无未报废的帚</td>
            </tr>
          )}
          {brushes.map((b) => (
            <tr key={b.id}>
              <td>{b.brushNo}</td>
              <td>{b.basinCode}</td>
              <td>{b.remaining}</td>
              <td>{b.hungAt ? new Date(b.hungAt).toLocaleString() : ""}</td>
              <td>
                <button onClick={() => discard(b.id)}>报废</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {err && <p class="err">{err}</p>}
    </div>
  );
}

function App() {
  const [ready, setReady] = useState(Boolean(token()));
  const [view, setView] = useState("yard");
  if (!ready) {
    return <Login onOk={() => setReady(true)} />;
  }
  return (
    <div class="yard">
      <div class="topbar">
        <div>
          <h1>江口缫丝坞</h1>
          <nav class="tabs">
            <button class={view === "yard" ? "on" : ""} onClick={() => setView("yard")}>
              环盆作业台
            </button>
            <button class={view === "brushes" ? "on" : ""} onClick={() => setView("brushes")}>
              索绪帚
            </button>
          </nav>
        </div>
        <button
          onClick={() => {
            clearToken();
            location.reload();
          }}
        >
          退出
        </button>
      </div>
      {view === "yard" ? <Yard /> : <Brushes />}
    </div>
  );
}

render(<App />, document.getElementById("app"));
