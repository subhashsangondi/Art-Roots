const form = document.getElementById("auth-form");
const statusEl = document.getElementById("auth-status");
const submit = document.getElementById("auth-submit");
const tabs = document.querySelectorAll(".auth-tabs button");
let mode = "login";

function nextUrl(user) {
  const next = new URLSearchParams(location.search).get("next");
  // Only follow same-site paths so the redirect can't be abused.
  if (next && next.startsWith("/") && !next.startsWith("//")) return next;
  return user.role === "artist" ? "/dashboard" : "/";
}

function syncArtistField() {
  const isArtist = form.elements.role.value === "artist";
  document.querySelector(".artist-only").hidden = mode !== "signup" || !isArtist;
}

function setMode(newMode) {
  mode = newMode;
  for (const tab of tabs) tab.setAttribute("aria-selected", String(tab.dataset.mode === mode));
  for (const el of document.querySelectorAll(".signup-only")) el.hidden = mode !== "signup";
  form.elements.password.autocomplete = mode === "signup" ? "new-password" : "current-password";
  submit.firstChild.textContent = mode === "signup" ? "Create account " : "Log in ";
  statusEl.textContent = "";
  syncArtistField();
}

for (const tab of tabs) tab.addEventListener("click", () => setMode(tab.dataset.mode));
for (const radio of form.elements.role) radio.addEventListener("change", syncArtistField);

form.addEventListener("submit", async event => {
  event.preventDefault();
  const values = Object.fromEntries(new FormData(form));
  submit.disabled = true; statusEl.className = "form-status"; statusEl.textContent = mode === "signup" ? "Creating your account…" : "Logging you in…";
  try {
    const response = await fetch(`/api/auth/${mode}`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(values)});
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
    location.href = nextUrl(data.user);
  } catch (error) {
    statusEl.className = "form-status error"; statusEl.textContent = error.message;
  } finally { submit.disabled = false; }
});

if (new URLSearchParams(location.search).get("mode") === "signup") setMode("signup");
