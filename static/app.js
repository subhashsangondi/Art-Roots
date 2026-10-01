// Set to false to use the Flask API endpoints.
const SAMPLE_MODE = false;

const sampleArtworks = [
  {id:"sample-1",title:"Where the Rain Rests",artist:"Mira Sen",image:"https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?auto=format&fit=crop&w=900&q=80",description:"The last light slips through rain-heavy clouds, turning an ordinary path into somewhere worth lingering.",story:"I wanted to remember the hush just after a storm, when every leaf seems to be holding its breath. The path is familiar, but the light makes it feel like a place you have only just discovered.",alt_text:"A winding path disappearing into a green forest beneath a soft, cloudy sky.",mood:["quiet", "renewal", "green"]},
  {id:"sample-2",title:"Sunday in Saffron",artist:"Arun Mehta",image:"https://images.unsplash.com/photo-1470252649378-9c29740c9fa8?auto=format&fit=crop&w=900&q=80",description:"Warm fields and a low sun, painted from the memory of a slow afternoon at home.",story:"This began with the colour of my grandmother's curtains at sunset. I kept the shapes loose so the painting could feel like a memory rather than a map.",alt_text:"A golden sun setting over a wide meadow with distant hills.",mood:["warm", "nostalgic", "gold"]},
  {id:"sample-3",title:"Blue Hour Letters",artist:"Leela Rao",image:"https://images.unsplash.com/photo-1518837695005-2083093ee35b?auto=format&fit=crop&w=900&q=80",description:"A small study of the sea in that brief moment between day and night.",story:"I made this after a long walk with a letter in my pocket. The waves kept their own time, and slowly the words I had been trying to write stopped mattering.",alt_text:"Deep blue ocean water folding into a foamy wave beneath a pale sky.",mood:["calm", "blue", "reflection"]},
  {id:"sample-4",title:"Things That Bloom Back",artist:"Nico Alvarez",image:"https://images.unsplash.com/photo-1490750967868-88aa4486c946?auto=format&fit=crop&w=900&q=80",description:"Wildflowers leaning toward the sun, each one finding its own way up.",story:"These flowers reminded me that beginning again does not have to be grand. Sometimes it is just a small patch of colour that decides to stay.",alt_text:"A cluster of delicate pink and white flowers in soft sunlight.",mood:["hopeful", "tender", "spring"]},
  {id:"sample-5",title:"The Long Way Home",artist:"Farah Ali",image:"https://images.unsplash.com/photo-1470770841072-f978cf4d019e?auto=format&fit=crop&w=900&q=80",description:"A landscape inspired by the mountain road that always seemed to take us somewhere better.",story:"We took this road every summer, and no one ever asked how much longer. The going was the point: open windows, cool air, and all the time in the world.",alt_text:"A quiet mountain lake reflecting forested slopes and a cloudy sky.",mood:["open", "wandering", "still"]},
  {id:"sample-6",title:"Small Bright Things",artist:"Jules Kim",image:"https://images.unsplash.com/photo-1490730141103-6cac27aaab94?auto=format&fit=crop&w=900&q=80",description:"A little colour for the days that need reminding that there is more ahead.",story:"I made this for a friend who was learning to look forward again. We talked about nothing in particular and noticed the sun had moved across the whole room.",alt_text:"A bright sunrise spreading warm pink and orange light across the horizon.",mood:["bright", "gentle", "optimistic"]}
];

const grid = document.getElementById("artwork-grid");
const statusEl = document.getElementById("gallery-status");
const resultsLabel = document.getElementById("results-label");
const dialog = document.getElementById("detail-dialog");
const detailContent = document.getElementById("detail-content");
let currentArtworks = [];

function text(value, fallback = "") { return value == null ? fallback : String(value); }
function tagsOf(item) {
  const tags = item.mood || item.tags || [];
  return Array.isArray(tags) ? tags.map(tag => typeof tag === "string" ? tag : text(tag.name || tag.label)).filter(Boolean) : String(tags).split(/[,|]/).map(tag => tag.trim()).filter(Boolean);
}
function imageOf(item) { return text(item.image || item.image_url || item.url); }
function setStatus(message, kind = "") { statusEl.textContent = message; statusEl.className = `status${kind ? ` ${kind}` : ""}`; }
function makeImage(src, alt, className) {
  const img = document.createElement("img"); img.className = className; img.src = src || ""; img.alt = alt; img.loading = "lazy";
  img.addEventListener("error", () => { img.removeAttribute("src"); img.alt = `${alt} (image unavailable)`; img.classList.add("image-unavailable"); });
  return img;
}
function renderArtworks(artworks, label = "") {
  currentArtworks = Array.isArray(artworks) ? artworks : [];
  grid.replaceChildren();
  if (label) resultsLabel.textContent = label;
  if (!currentArtworks.length) {
    const empty = document.createElement("div"); empty.className = "empty-state";
    const heading = document.createElement("strong"); heading.textContent = "No art found this time";
    const detail = document.createElement("span"); detail.textContent = "Try another mood, or come back to explore the collection.";
    empty.append(heading, detail); grid.append(empty); return;
  }
  for (const artwork of currentArtworks) {
    const card = document.createElement("article"); card.className = "art-card"; card.tabIndex = 0; card.setAttribute("role", "button");
    card.setAttribute("aria-label", `View ${text(artwork.title, "untitled artwork")} by ${text(artwork.artist, "unknown artist")}`);
    card.append(makeImage(imageOf(artwork), text(artwork.alt_text, text(artwork.title, "Artwork")), "card-image"));
    const body = document.createElement("div"); body.className = "card-body";
    const title = document.createElement("h3"); title.textContent = text(artwork.title, "Untitled");
    const artist = document.createElement("p"); artist.className = "artist-name"; artist.textContent = `by ${text(artwork.artist, "Unknown artist")}`;
    const tagList = document.createElement("div"); tagList.className = "tag-list";
    for (const tag of tagsOf(artwork)) { const chip = document.createElement("span"); chip.className = "tag"; chip.textContent = tag; tagList.append(chip); }
    body.append(title, artist, tagList); card.append(body);
    const open = () => showDetails(artwork);
    card.addEventListener("click", open); card.addEventListener("keydown", event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); open(); } });
    grid.append(card);
  }
}
async function api(path, options = {}) {
  const response = await fetch(path, options);
  let payload = {};
  try { payload = await response.json(); } catch (_) { /* use friendly fallback below */ }
  if (!response.ok) throw new Error(text(payload.error || payload.message, `Request failed (${response.status})`));
  return payload;
}
async function loadArtworks() {
  setStatus("Gathering a little art for you…");
  try {
    const artworks = SAMPLE_MODE ? sampleArtworks : (await api("/api/artworks")).artworks;
    setStatus(""); renderArtworks(artworks, SAMPLE_MODE ? "A collection for curious hearts · demo" : "A collection for curious hearts");
  } catch (error) { setStatus(`We couldn't load the collection. ${error.message}`, "error"); renderArtworks([]); }
}
function showDetails(artwork) {
  const id = artwork.id;
  detailContent.replaceChildren();
  const imageWrap = document.createElement("div"); imageWrap.className = "detail-image-wrap";
  imageWrap.append(makeImage(imageOf(artwork), text(artwork.alt_text, text(artwork.title, "Artwork")), "detail-image"));
  const copy = document.createElement("div"); copy.className = "detail-copy";
  const title = document.createElement("h2"); title.id = "detail-title"; title.textContent = text(artwork.title, "Untitled");
  const artist = document.createElement("p"); artist.className = "detail-artist"; artist.textContent = `by ${text(artwork.artist, "Unknown artist")}`;
  const description = document.createElement("p"); description.className = "detail-description"; description.textContent = text(artwork.description, "No description has been added yet.");
  const tagList = document.createElement("div"); tagList.className = "tag-list";
  for (const tag of tagsOf(artwork)) { const chip = document.createElement("span"); chip.className = "tag"; chip.textContent = tag; tagList.append(chip); }
  const story = document.createElement("section"); story.className = "story-box";
  const storyHeading = document.createElement("h3"); storyHeading.textContent = "AI-Assisted Story";
  const storyText = document.createElement("p"); storyText.textContent = text(artwork.story || artwork.ai_story, "A story for this artwork will appear here when available."); story.append(storyHeading, storyText);
  const alt = document.createElement("p"); alt.className = "alt-text"; alt.textContent = `Image description: ${text(artwork.alt_text, "Not provided")}`;
  copy.append(title, artist, description, tagList, story, alt, makeChat(id)); detailContent.append(imageWrap, copy);
  if (!dialog.open) dialog.showModal();
  if (!SAMPLE_MODE && id != null) loadDetails(id, {title, artist, description, storyText, alt, tagList, imageWrap, copy});
}
async function loadDetails(id, refs) {
  try {
    const data = await api(`/api/artworks/${encodeURIComponent(id)}`); const item = data.artwork || data;
    refs.title.textContent = text(item.title, "Untitled"); refs.artist.textContent = `by ${text(item.artist, "Unknown artist")}`;
    refs.description.textContent = text(item.description, "No description has been added yet."); refs.storyText.textContent = text(item.story || item.ai_story, "A story for this artwork will appear here when available.");
    refs.alt.textContent = `Image description: ${text(item.alt_text, "Not provided")}`;
    refs.imageWrap.replaceChildren(makeImage(imageOf(item), text(item.alt_text, text(item.title, "Artwork")), "detail-image"));
    refs.tagList.replaceChildren(); for (const tag of tagsOf(item)) { const chip = document.createElement("span"); chip.className = "tag"; chip.textContent = tag; refs.tagList.append(chip); }
  } catch (error) { const note = document.createElement("p"); note.className = "form-status error"; note.textContent = `Some details couldn't be loaded. ${error.message}`; refs.copy.append(note); }
}
function makeChat(id) {
  const section = document.createElement("section"); section.className = "chat-box";
  const heading = document.createElement("h3"); heading.textContent = "Ask the artwork";
  const form = document.createElement("form"); const input = document.createElement("input"); input.name = "message"; input.required = true; input.maxLength = 1000; input.placeholder = "What inspired this artwork?"; input.setAttribute("aria-label", "Ask a question about this artwork");
  const button = document.createElement("button"); button.type = "submit"; button.textContent = "Ask";
  const reply = document.createElement("p"); reply.className = "chat-reply"; reply.setAttribute("aria-live", "polite"); form.append(input, button); section.append(heading, form, reply);
  form.addEventListener("submit", async event => {
    event.preventDefault(); const message = input.value.trim(); if (!message) return;
    button.disabled = true; reply.textContent = "Thinking about it…";
    try {
      if (SAMPLE_MODE) reply.textContent = "This piece grew from the artist's memories and the feeling of noticing a small, beautiful moment. Try live mode to ask the artwork directly.";
      else { const data = await api(`/api/artworks/${encodeURIComponent(id)}/chat`, {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({message})}); reply.textContent = text(data.reply, "The artwork has no reply just yet."); }
    } catch (error) { reply.textContent = `Sorry, we couldn't get a reply. ${error.message}`; }
    finally { button.disabled = false; }
  }); return section;
}
document.getElementById("search-form").addEventListener("submit", async event => {
  event.preventDefault(); const query = document.getElementById("search-input").value.trim(); if (!query) return;
  setStatus("Following that feeling…"); resultsLabel.textContent = `Searching for “${query}”`;
  try {
    let artworks;
    if (SAMPLE_MODE) { const words = query.toLowerCase().split(/\W+/).filter(word => word.length > 3); artworks = sampleArtworks.filter(item => words.some(word => `${item.title} ${item.description} ${item.story} ${tagsOf(item).join(" ")}`.toLowerCase().includes(word))); }
    else artworks = (await api("/api/search", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({query})})).artworks;
    setStatus(""); renderArtworks(artworks, `Results for “${query}”${SAMPLE_MODE ? " · demo" : ""}`);
  } catch (error) { setStatus(`That search didn't come through. ${error.message}`, "error"); renderArtworks([]); }
});
document.getElementById("upload-form").addEventListener("submit", async event => {
  event.preventDefault(); const form = event.currentTarget; const message = document.getElementById("upload-status"); message.className = "form-status";
  if (SAMPLE_MODE) {
    const values = new FormData(form);
    const file = values.get("image");
    const demoArtwork = {
      id: `demo-${Date.now()}`,
      title: text(values.get("title"), "Untitled"),
      artist: text(values.get("artist"), "Unknown artist"),
      description: text(values.get("description")),
      image: file instanceof File && file.size ? URL.createObjectURL(file) : "",
      alt_text: text(values.get("title"), "Uploaded artwork"),
      story: "Your demo upload is in the gallery. Switch to live mode to submit it to the Flask app.",
      mood: ["your upload"]
    };
    sampleArtworks.unshift(demoArtwork);
    message.textContent = "Added to the demo gallery. Your upload is only stored in this browser session.";
    form.reset();
    renderArtworks(sampleArtworks, "A collection for curious hearts · demo");
    return;
  }
  message.textContent = "Sharing your artwork… AI analysis may take up to a minute."; const button = form.querySelector("button[type=submit]"); button.disabled = true;
  try { const data = await api("/api/artworks", {method:"POST",body:new FormData(form)}); message.textContent = text(data.message, "Your artwork has been shared. Thank you!"); form.reset(); await loadArtworks(); }
  catch (error) { message.className = "form-status error"; message.textContent = `We couldn't share your artwork. ${error.message}`; }
  finally { button.disabled = false; }
});
document.querySelector(".dialog-close").addEventListener("click", () => dialog.close());
dialog.addEventListener("click", event => { if (event.target === dialog) dialog.close(); });
document.addEventListener("keydown", event => { if (event.key === "Escape" && dialog.open) dialog.close(); });
loadArtworks();
