const statusEl = document.getElementById("dash-status");
const body = document.getElementById("dash-body");

function text(value, fallback = "") { return value == null ? fallback : String(value); }
function setStatus(message, kind = "") { statusEl.textContent = message; statusEl.className = `status${kind ? ` ${kind}` : ""}`; }
function plural(count, word) { return `${count} ${word}${count === 1 ? "" : "s"}`; }

function renderChart(artworks) {
  const chart = document.getElementById("views-chart");
  chart.replaceChildren();
  const max = Math.max(1, ...artworks.map(item => item.views));
  for (const artwork of artworks) {
    const row = document.createElement("div"); row.className = "bar-row";
    row.title = `${text(artwork.title, "Untitled")}: ${plural(artwork.views, "view")}, ${plural(artwork.likes, "like")}`;
    const label = document.createElement("span"); label.className = "bar-label"; label.textContent = text(artwork.title, "Untitled");
    const track = document.createElement("span"); track.className = "bar-track";
    const bar = document.createElement("span"); bar.className = "bar"; bar.style.width = `${(artwork.views / max) * 100}%`;
    track.append(bar);
    const value = document.createElement("span"); value.className = "bar-value"; value.textContent = artwork.views;
    row.append(label, track, value); chart.append(row);
  }
}

function renderTags(tags) {
  const list = document.getElementById("top-tags");
  list.replaceChildren();
  if (!tags.length) { list.textContent = "No tags yet."; return; }
  for (const { tag, count } of tags) {
    const chip = document.createElement("span"); chip.className = "tag"; chip.textContent = `${tag} · ${count}`; list.append(chip);
  }
}

function renderGrid(artworks) {
  const grid = document.getElementById("dash-grid");
  grid.replaceChildren();
  for (const artwork of artworks) {
    const card = document.createElement("article"); card.className = "art-card dash-card";
    const img = document.createElement("img"); img.className = "card-image"; img.src = text(artwork.image_url); img.alt = text(artwork.alt_text, text(artwork.title, "Artwork")); img.loading = "lazy";
    const cardBody = document.createElement("div"); cardBody.className = "card-body";
    const title = document.createElement("h3"); title.textContent = text(artwork.title, "Untitled");
    const meta = document.createElement("p"); meta.className = "artist-name";
    meta.textContent = `👁 ${plural(artwork.views, "view")} · ♥ ${plural(artwork.likes, "like")}${artwork.created_at ? ` · shared ${new Date(`${artwork.created_at.replace(" ", "T")}Z`).toLocaleDateString()}` : ""}`;
    const tagList = document.createElement("div"); tagList.className = "tag-list";
    for (const tag of artwork.tags || []) { const chip = document.createElement("span"); chip.className = "tag"; chip.textContent = tag; tagList.append(chip); }
    cardBody.append(title, meta, tagList); card.append(img, cardBody); grid.append(card);
  }
}

async function loadDashboard() {
  setStatus("Gathering your collection…");
  try {
    const response = await fetch("/api/dashboard");
    if (response.status === 401 || response.status === 403) { location.href = "/login?next=/dashboard"; return; }
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(text(data.error, `Request failed (${response.status})`));

    document.getElementById("dash-title").replaceChildren(document.createTextNode(`${data.artist}’s `), Object.assign(document.createElement("em"), { textContent: "studio" }));
    if (!data.artworks.length) {
      setStatus("You haven't shared any artwork yet. Post your first piece from the home page.");
      return;
    }
    document.getElementById("stat-artworks").textContent = data.stats.artworks;
    document.getElementById("stat-views").textContent = data.stats.views;
    document.getElementById("stat-likes").textContent = data.stats.likes;
    const top = data.stats.top_artwork;
    document.getElementById("stat-top").textContent = top && top.views > 0 ? `${top.title} (${top.views})` : "No views yet";
    renderChart(data.artworks); renderTags(data.top_tags); renderGrid(data.artworks);
    setStatus(""); body.hidden = false;
  } catch (error) { setStatus(`We couldn't load the dashboard. ${error.message}`, "error"); }
}

document.getElementById("logout-button").addEventListener("click", async () => {
  await fetch("/api/auth/logout", { method: "POST" });
  location.href = "/";
});

loadDashboard();
