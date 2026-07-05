const params = new URLSearchParams(window.location.search);
const logPath = params.get("log");
const mode = params.get("mode") || "replay"; // "live" or "replay"

const canvas = document.getElementById("board");
const ctx = canvas.getContext("2d");
const TILE = 20; // pixels per arena tile (18 wide x 32 tall -> 360x640)
const ARENA_WIDTH = 360;
const ARENA_HEIGHT = 640;

function drawMessage(lines) {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#fff";
  ctx.font = "13px monospace";
  lines.forEach((line, i) => ctx.fillText(line, 16, 30 + i * 18));
}

function drawArenaBackground() {
  const bgGradient = ctx.createLinearGradient(0, 0, 0, ARENA_HEIGHT);
  bgGradient.addColorStop(0, "#1b3a2e");
  bgGradient.addColorStop(0.5, "#173322");
  bgGradient.addColorStop(1, "#1b3a2e");
  ctx.fillStyle = bgGradient;
  ctx.fillRect(0, 0, ARENA_WIDTH, ARENA_HEIGHT);

  const riverGradient = ctx.createLinearGradient(0, ARENA_HEIGHT / 2 - 18, 0, ARENA_HEIGHT / 2 + 18);
  riverGradient.addColorStop(0, "rgba(74, 144, 217, 0.15)");
  riverGradient.addColorStop(0.5, "rgba(74, 144, 217, 0.35)");
  riverGradient.addColorStop(1, "rgba(74, 144, 217, 0.15)");
  ctx.fillStyle = riverGradient;
  ctx.fillRect(0, ARENA_HEIGHT / 2 - 18, ARENA_WIDTH, 36);

  ctx.strokeStyle = "rgba(255, 255, 255, 0.06)";
  ctx.lineWidth = 1;
  [ARENA_WIDTH * 0.3, ARENA_WIDTH * 0.7].forEach((x) => {
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, ARENA_HEIGHT);
    ctx.stroke();
  });
}

const ELIXIR_MAX = 10;
const elixirSegments = [document.getElementById("elixir-0"), document.getElementById("elixir-1")].map(
  (container) => {
    const segments = [];
    for (let i = 0; i < ELIXIR_MAX; i++) {
      const seg = document.createElement("div");
      seg.className = "w-4 h-5 rounded-sm border border-arena-line bg-arena";
      container.appendChild(seg);
      segments.push(seg);
    }
    return segments;
  }
);

function updateElixirBars(players) {
  players.forEach((player, i) => {
    const filled = Math.floor(player.elixir + 1e-6);
    elixirSegments[i].forEach((seg, idx) => {
      seg.classList.toggle("bg-elixir", idx < filled);
      seg.classList.toggle("bg-arena", idx >= filled);
    });
  });
}

function drawHpBar(x, y, radius, hp, maxHp) {
  if (!maxHp) return; // older logs recorded before max_hp existed — skip rather than crash
  const barWidth = radius * 2.5;
  const barHeight = 3;
  const barX = x - barWidth / 2;
  const barY = y - radius - 8;
  const ratio = Math.max(0, Math.min(1, hp / maxHp));

  ctx.fillStyle = "rgba(0, 0, 0, 0.55)";
  ctx.fillRect(barX, barY, barWidth, barHeight);

  let fillColor;
  if (ratio > 0.5) fillColor = "#3fbf5f";
  else if (ratio > 0.2) fillColor = "#e0c040";
  else fillColor = "#d9484a";

  ctx.fillStyle = fillColor;
  ctx.fillRect(barX, barY, barWidth * ratio, barHeight);
}

function draw(snapshot) {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  drawArenaBackground();
  if (!snapshot) return;

  updateElixirBars(snapshot.players);

  for (const entity of snapshot.entities) {
    const x = entity.x * TILE;
    const y = (32 - entity.y) * TILE; // flip so player 0 renders at the bottom
    const teamColor = entity.player_id === 0 ? "#4a90d9" : "#d94a4a";
    const radius = entity.is_tower ? 12 : 8;

    ctx.save();
    ctx.shadowColor = teamColor;
    ctx.shadowBlur = entity.is_tower ? 14 : 8;
    ctx.fillStyle = teamColor;
    ctx.beginPath();
    ctx.arc(x, y, radius, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();

    drawHpBar(x, y, radius, entity.hp, entity.max_hp);

    ctx.fillStyle = "#fff";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.font = `${entity.is_tower ? 14 : 11}px sans-serif`;
    ctx.fillText(getCardIcon(entity.card), x, y);
    ctx.textAlign = "left";
    ctx.textBaseline = "alphabetic";

    ctx.fillStyle = "#fff";
    ctx.font = "9px monospace";
    ctx.fillText(entity.card, x + radius + 3, y + 3);
  }

  ctx.fillStyle = "#f5f5f0";
  ctx.font = "bold 13px monospace";
  ctx.fillText(`tick ${snapshot.tick}`, 10, 18);

  snapshot.players.forEach((p, i) => {
    const color = i === 0 ? "#4a90d9" : "#d94a4a";
    const y = 36 + i * 16;
    ctx.fillStyle = color;
    ctx.font = "11px sans-serif";
    ctx.fillText("💧", 10, y);
    ctx.fillStyle = "#f5f5f0";
    ctx.font = "11px monospace";
    ctx.fillText(`${p.elixir.toFixed(1)}  king ${Math.round(p.king_hp)}`, 26, y);
  });
}

if (!logPath) {
  drawMessage([
    "No match log specified.",
    "Add ?log=<path>&mode=replay to the URL, e.g.:",
    "?log=logs/example_match.jsonl&mode=replay",
  ]);
} else if (mode === "live") {
  setInterval(async () => {
    const res = await fetch(`/snapshot/latest?log=${encodeURIComponent(logPath)}`);
    if (res.ok) {
      draw(await res.json());
    } else {
      drawMessage([`Could not load log: ${logPath}`, `(status ${res.status})`]);
    }
  }, 250);
} else {
  fetch(`/replay?log=${encodeURIComponent(logPath)}`)
    .then((res) => {
      if (!res.ok) throw new Error(`status ${res.status}`);
      return res.json();
    })
    .then((snapshots) => {
      if (!Array.isArray(snapshots) || snapshots.length === 0) {
        throw new Error("empty or invalid replay data");
      }
      const scrub = document.getElementById("scrub");
      const playPause = document.getElementById("playPause");
      const speed = document.getElementById("speed");
      scrub.max = snapshots.length - 1;

      let index = 0;
      let playing = false;
      let timer = null;

      function render() {
        draw(snapshots[index]);
        scrub.value = index;
      }

      function tick() {
        if (index >= snapshots.length - 1) {
          playing = false;
          playPause.textContent = "Play";
          clearInterval(timer);
          return;
        }
        index += 1;
        render();
      }

      function restartTimer() {
        clearInterval(timer);
        if (playing) timer = setInterval(tick, Number(speed.value));
      }

      playPause.addEventListener("click", () => {
        playing = !playing;
        playPause.textContent = playing ? "Pause" : "Play";
        restartTimer();
      });
      speed.addEventListener("change", restartTimer);
      scrub.addEventListener("input", () => {
        index = Number(scrub.value);
        render();
      });

      render();
    })
    .catch((err) => {
      drawMessage([`Could not load log: ${logPath}`, err.message]);
    });
}
