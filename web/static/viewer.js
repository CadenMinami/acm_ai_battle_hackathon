const params = new URLSearchParams(window.location.search);
const logPath = params.get("log");
const mode = params.get("mode") || "replay"; // "live" or "replay"

const canvas = document.getElementById("board");
const ctx = canvas.getContext("2d");
const TILE = 20; // pixels per arena tile (18 wide x 32 tall -> 360x640)

function draw(snapshot) {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (!snapshot) return;

  for (const entity of snapshot.entities) {
    const x = entity.x * TILE;
    const y = (32 - entity.y) * TILE; // flip so player 0 renders at the bottom
    ctx.fillStyle = entity.player_id === 0 ? "#4a90d9" : "#d94a4a";
    ctx.beginPath();
    ctx.arc(x, y, entity.is_tower ? 10 : 6, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "#fff";
    ctx.font = "9px monospace";
    ctx.fillText(entity.card, x + 8, y);
  }

  ctx.fillStyle = "#fff";
  ctx.font = "12px monospace";
  ctx.fillText(`tick ${snapshot.tick}`, 10, 16);
  snapshot.players.forEach((p, i) => {
    ctx.fillText(
      `p${i} elixir=${p.elixir.toFixed(1)} king=${Math.round(p.king_hp)}`,
      10,
      32 + i * 14
    );
  });
}

if (mode === "live") {
  setInterval(async () => {
    const res = await fetch(`/snapshot/latest?log=${encodeURIComponent(logPath)}`);
    if (res.ok) draw(await res.json());
  }, 250);
} else {
  fetch(`/replay?log=${encodeURIComponent(logPath)}`)
    .then((res) => res.json())
    .then((snapshots) => {
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
    });
}
