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

function Topbar({ view, onNav }) {
  return (
    <div class="topbar">
      <div class="brand">江口缫丝坞</div>
      <nav class="tabs">
        <button class={view === "yard" ? "on" : ""} onClick={() => onNav("yard")}>
          环盆作业台
        </button>
        <button class={view === "brushes" ? "on" : ""} onClick={() => onNav("brushes")}>
          索绪帚
        </button>
      </nav>
      <button
        onClick={() => {
          clearToken();
          location.reload();
        }}
      >
        退出
      </button>
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
      <div class="yardhead">
        <h1>{board.filature}</h1>
        <p>
          {board.riverside} · 点盆登记汤温；已缫完须最近汤温 38～42℃；浸茧改缫丝中须先挂未报废且有余次的索绪帚
        </p>
      </div>
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
              ? `${picked.brush.brushNo} · 剩余 ${picked.brush.remaining} 次`
              : "未挂"}
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
  const [remaining, setRemaining] = useState("1");
  const [err, setErr] = useState("");
  const [ok, setOk] = useState("");

  async function loadBrushes(f) {
    const want = f === undefined ? filter : f;
    const data = await api(`/api/brushes${want ? `?basinId=${want}` : ""}`);
    setBrushes(data.brushes);
  }

  useEffect(() => {
    api("/api/board")
      .then((d) => setBasins(d.basins))
      .catch((e) => setErr(e.message));
  }, []);

  useEffect(() => {
    loadBrushes().catch((e) => setErr(e.message));
  }, [filter]);

  async function hang(e) {
    e.preventDefault();
    setErr("");
    setOk("");
    if (!basinId) {
      setErr("请选择盆位");
      return;
    }
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
      setRemaining("1");
      setOk("已挂出");
      await loadBrushes();
    } catch (ex) {
      setErr(ex.message);
    }
  }

  async function scrap(id) {
    setErr("");
    setOk("");
    try {
      await api(`/api/brushes/${id}/scrap`, { method: "POST" });
      setOk("已报废");
      await loadBrushes();
    } catch (ex) {
      setErr(ex.message);
    }
  }

  return (
    <div>
      <div class="yardhead">
        <h1>索绪帚</h1>
        <p>浸茧改缫丝中须该盆挂着未报废且剩余次数大于 0 的帚；同一盆最多挂一把未报废帚。</p>
      </div>
      <form class="brush-form" onSubmit={hang} autocomplete="off">
        <label>
          盆
          <select value={basinId} onInput={(e) => setBasinId(e.target.value)}>
            <option value="">选择盆位</option>
            {basins.map((b) => (
              <option key={b.id} value={b.id}>
                {b.code}（{STATUS_LABEL[b.status]}）
              </option>
            ))}
          </select>
        </label>
        <label>
          帚号
          <input value={brushNo} onInput={(e) => setBrushNo(e.target.value)} placeholder="如 帚-01" />
        </label>
        <label>
          剩余次数
          <input type="number" min="1" step="1" value={remaining} onInput={(e) => setRemaining(e.target.value)} />
        </label>
        <button type="submit">挂出</button>
      </form>
      <div class="brush-filter">
        按盆筛：
        <select value={filter} onInput={(e) => setFilter(e.target.value)}>
          <option value="">全部盆位</option>
          {basins.map((b) => (
            <option key={b.id} value={b.id}>
              {b.code}
            </option>
          ))}
        </select>
      </div>
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
          {brushes.map((br) => (
            <tr key={br.id}>
              <td>{br.brushNo}</td>
              <td>{br.basinCode}</td>
              <td>{br.remaining}</td>
              <td>{br.hungAt ? new Date(br.hungAt).toLocaleString() : ""}</td>
              <td>
                <button onClick={() => scrap(br.id)}>报废</button>
              </td>
            </tr>
          ))}
          {brushes.length === 0 && (
            <tr>
              <td colSpan="5">暂无未报废的索绪帚</td>
            </tr>
          )}
        </tbody>
      </table>
      {err && <p class="err">{err}</p>}
      {ok && <p class="ok">{ok}</p>}
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
    <div class="page">
      <Topbar view={view} onNav={setView} />
      {view === "yard" ? <Yard /> : <Brushes />}
    </div>
  );
}

render(<App />, document.getElementById("app"));
