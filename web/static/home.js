const matchesList = document.getElementById("matches-list");
const bracketList = document.getElementById("bracket-list");
const bracketSection = document.getElementById("bracket-section");
const matchesSection = document.getElementById("matches-section");
const emptyState = document.getElementById("empty-state");
const refreshButton = document.getElementById("refresh");

function formatTime(mtime) {
  return new Date(mtime * 1000).toLocaleString();
}

function makeCard(title, subtitle, href) {
  const a = document.createElement("a");
  a.href = href;
  a.className = "block border border-arena-line rounded p-4 hover:border-gold hover:text-gold transition-colors";
  a.innerHTML = "";
  const titleDiv = document.createElement("div");
  titleDiv.className = "font-bold";
  titleDiv.textContent = title;
  const subtitleDiv = document.createElement("div");
  subtitleDiv.className = "text-sm text-ink-muted mt-1";
  subtitleDiv.textContent = subtitle;
  a.appendChild(titleDiv);
  a.appendChild(subtitleDiv);
  return a;
}

async function loadBrowse() {
  matchesList.innerHTML = "";
  bracketList.innerHTML = "";

  const response = await fetch("/api/browse");
  const data = await response.json();

  if (data.logs.length === 0 && data.results.length === 0) {
    emptyState.classList.remove("hidden");
    matchesSection.classList.add("hidden");
    bracketSection.classList.add("hidden");
    return;
  }
  emptyState.classList.add("hidden");

  if (data.results.length > 0) {
    bracketSection.classList.remove("hidden");
    for (const result of data.results) {
      const href = `/bracket?results=${encodeURIComponent(result.path)}`;
      bracketList.appendChild(makeCard(result.path, formatTime(result.mtime), href));
    }
  } else {
    bracketSection.classList.add("hidden");
  }

  matchesSection.classList.remove("hidden");
  for (const log of data.logs) {
    const href = `/viewer?log=${encodeURIComponent(log.path)}&mode=replay`;
    matchesList.appendChild(makeCard(log.path, formatTime(log.mtime), href));
  }
}

refreshButton.addEventListener("click", loadBrowse);
loadBrowse();
