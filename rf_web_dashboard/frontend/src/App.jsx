import { useEffect, useMemo, useRef, useState } from "react";
import { Bar } from "react-chartjs-2";
import {
  BarElement,
  CategoryScale,
  Chart as ChartJS,
  LinearScale,
  Tooltip,
} from "chart.js";

ChartJS.register(BarElement, CategoryScale, LinearScale, Tooltip);

const EMPTY_CHANNELS = Array(125).fill(0);

const chartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  animation: { duration: 180 },
  interaction: { mode: "nearest", intersect: true },
  plugins: {
    legend: { display: false },
    tooltip: {
      displayColors: false,
      backgroundColor: "#16262e",
      borderColor: "#38515b",
      borderWidth: 1,
      titleColor: "#e8eef2",
      bodyColor: "#63d9e8",
      callbacks: {
        title: (items) => `Channel ${items[0].label}`,
        label: (item) => (item.raw ? "Signal active" : "Channel quiet"),
      },
    },
  },
  scales: {
    x: {
      grid: { display: false },
      ticks: { color: "#82929d", maxTicksLimit: 11 },
    },
    y: {
      min: 0,
      max: 1,
      grid: { display: false },
      ticks: {
        stepSize: 1,
        color: "#82929d",
        callback: (value) => (value ? "ACTIVE" : "QUIET"),
      },
    },
  },
};

function useSpectrumStream() {
  const [connected, setConnected] = useState(false);
  const [health, setHealth] = useState({
    model_loaded: false,
    serial_connected: false,
    sequence: 0,
  });
  const [frame, setFrame] = useState(null);

  useEffect(() => {
    let socket;
    let reconnectTimer;
    let disposed = false;
    let healthTimer;

    const connect = () => {
      if (disposed) return;
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      socket = new WebSocket(`${protocol}//${window.location.host}/ws`);
      socket.onopen = () => setConnected(true);
      socket.onmessage = (event) => {
        try {
          setFrame(JSON.parse(event.data));
        } catch (error) {
          console.error("Received invalid spectrum data:", error);
        }
      };
      socket.onclose = () => {
        setConnected(false);
        if (!disposed) reconnectTimer = window.setTimeout(connect, 1500);
      };
      socket.onerror = () => socket.close();
    };

    const refreshHealth = async () => {
      try {
        const response = await fetch("/api/health");
        if (!response.ok) {
          throw new Error(`Health request failed (${response.status})`);
        }
        setHealth(await response.json());
      } catch (error) {
        console.error("Could not load backend health:", error);
      }
    };

    connect();
    refreshHealth();
    healthTimer = window.setInterval(refreshHealth, 3000);
    return () => {
      disposed = true;
      window.clearTimeout(reconnectTimer);
      window.clearInterval(healthTimer);
      socket?.close();
    };
  }, []);

  useEffect(() => {
    if (frame) {
      setHealth((current) => ({
        ...current,
        model_loaded: frame.model_loaded,
        sequence: frame.sequence,
      }));
    }
  }, [frame]);

  return { connected, health, frame };
}

function Waterfall({ frame }) {
  const canvasRef = useRef(null);
  const framesRef = useRef([]);

  useEffect(() => {
    if (!frame?.channels) return;
    framesRef.current = [...framesRef.current, frame.channels].slice(-40);
    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d");
    if (!canvas || !context) return;

    const draw = () => {
      const bounds = canvas.getBoundingClientRect();
      const ratio = window.devicePixelRatio || 1;
      canvas.width = Math.round(bounds.width * ratio);
      canvas.height = Math.round(bounds.height * ratio);
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      context.fillStyle = "#0b151a";
      context.fillRect(0, 0, bounds.width, bounds.height);
      const rowHeight = bounds.height / 40;
      const cellWidth = bounds.width / 125;
      const rows = framesRef.current.length;
      framesRef.current.forEach((channels, row) => {
        channels.forEach((active, channel) => {
          if (!active) return;
          const age = rows - row;
          context.fillStyle = `rgba(99, 217, 232, ${Math.max(0.2, 1 - age / 42)})`;
          context.fillRect(
            channel * cellWidth,
            row * rowHeight,
            Math.ceil(cellWidth) + 0.3,
            Math.ceil(rowHeight) + 0.3,
          );
        });
      });
    };

    draw();
    const observer = new ResizeObserver(draw);
    observer.observe(canvas);
    return () => observer.disconnect();
  }, [frame]);

  return <canvas ref={canvasRef} className="waterfall-canvas" aria-label="Recent channel activity" />;
}

function Probability({ label, value, tone }) {
  const probability = Number(value || 0);
  return (
    <div className="prob-row">
      <div className="prob-top">
        <span>{label}</span>
        <span className="prob-value">{probability.toFixed(1)}%</span>
      </div>
      <div className="track">
        <div className={`fill ${tone}`} style={{ width: `${probability}%` }} />
      </div>
    </div>
  );
}

export default function App() {
  const { connected, health, frame } = useSpectrumStream();
  const channels = frame?.channels ?? EMPTY_CHANNELS;
  const probabilities = frame?.probabilities ?? {};
  const active = Number(frame?.active_channels ?? 0);
  const confidence = Number(frame?.confidence ?? 0);
  const detected = Boolean(frame?.drone_detected);
  const inferenceError = Boolean(frame?.inference_error);
  const className = frame?.class_name ?? (health.model_loaded ? "Warming up" : "Model unavailable");

  const chartData = useMemo(
    () => ({
      labels: Array.from({ length: 125 }, (_, index) => index),
      datasets: [
        {
          data: channels,
          backgroundColor: channels.map((value) =>
            value ? (detected ? "#ff647c" : "#63d9e8") : "rgba(99,217,232,.13)",
          ),
          borderColor: channels.map((value) =>
            value ? (detected ? "#ff9aaa" : "#b4f5f1") : "transparent",
          ),
          borderWidth: 1,
          borderRadius: 3,
          borderSkipped: false,
          barPercentage: 0.9,
          categoryPercentage: 0.98,
        },
      ],
    }),
    [channels, detected],
  );

  return (
    <main className="shell">
      <header>
        <div>
          <p className="eyebrow">RF / SENTINEL 01</p>
          <h1>Live spectrum monitor</h1>
          <p className="subhead">Random forest classification · 125-channel scan field</p>
        </div>
        <div className="connection">
          <span className={`dot ${connected ? "live" : ""}`} />
          <span>{connected ? "Connected" : "Offline"}</span>
        </div>
      </header>

      <section className={`status ${detected || inferenceError ? "alert" : frame ? "clear" : ""}`}>
        <div>
          <div className="status-title">
            {inferenceError
              ? "Model inference failed"
              : detected
              ? "Target RF source detected"
              : frame
                ? "Spectrum clear"
                : "Waiting for signal"}
          </div>
          <div className="status-copy">
            {!health.model_loaded
              ? "The model could not be loaded. Check the backend log and model file."
              : !health.serial_connected
                ? "Waiting for a serial connection and a live spectrum stream."
                : inferenceError
                  ? "The backend logged the inference error; predictions will not be trusted."
                  : detected
                    ? "The rolling classifier has crossed the detection threshold."
                  : frame
                    ? `Current class: ${className}. Monitoring continues in real time.`
                    : "Listening for a serial stream and warming the temporal model window."}
          </div>
        </div>
        <div className="status-badge">
          {detected || inferenceError ? "Attention required" : frame ? "Monitoring" : "Standby"}
        </div>
      </section>

      <section className="metrics">
        <article className="metric">
          <div className="label">Model confidence</div>
          <div className="metric-value accent">{confidence}<small>%</small></div>
        </article>
        <article className="metric">
          <div className="label">Active channels</div>
          <div className="metric-value">{active}<small> / 125</small></div>
        </article>
        <article className="metric">
          <div className="label">Scan sequence</div>
          <div className="metric-value green">{frame?.sequence ?? "—"}</div>
        </article>
        <article className="metric">
          <div className="label">Current class</div>
          <div className="metric-value amber class-value">{className}</div>
        </article>
      </section>

      <section className="layout">
        <div>
          <article className="panel">
            <div className="panel-head">
              <div className="panel-title">Signal activity</div>
              <div className="panel-note">LIVE / 125 CHANNELS</div>
            </div>
            <div className="chart-wrap">
              <Bar data={chartData} options={chartOptions} />
            </div>
            <div className="channel-axis">
              <span>CH 0</span><span>25</span><span>50</span><span>75</span><span>100</span><span>CH 124</span>
            </div>
          </article>
          <article className="panel waterfall-panel">
            <div className="panel-head">
              <div className="panel-title">Channel waterfall</div>
              <div className="panel-note">125 CHANNELS / 40 FRAMES</div>
            </div>
            <div className="waterfall-wrap"><Waterfall frame={frame} /></div>
            <div className="footer">
              <span>older ← history</span>
              <span>newest → scan <b>{frame?.sequence ?? "—"}</b></span>
            </div>
          </article>
        </div>

        <aside className="panel">
          <div className="panel-head">
            <div className="panel-title">Classification</div>
            <div className="panel-note">PROBABILITY</div>
          </div>
          <Probability label="Background / non-target" value={probabilities["0"]} tone="ambient" />
          <Probability label="Target RF source (RC proxy)" value={probabilities["1"]} tone="drone" />
          <div className="footer"><span>Model output</span><span>2 classes</span></div>
          <div className="footer"><span>Temporal window</span><span>5 frames</span></div>
          <div className="footer"><span>Alert threshold</span><span>30% / 15 frames</span></div>
          <div className="footer"><span>Serial port</span><span>{health.serial_connected ? "Connected" : "Offline"}</span></div>
        </aside>
      </section>
    </main>
  );
}
