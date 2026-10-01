# Art Roots

**A little art. A lot of feeling.**

Art Roots is a web gallery where artists share their work and visitors find art by mood. When an artist uploads a piece, Google Gemini looks at the image and writes a short story about it, picks mood tags, and writes accessible alt text. Visitors can search, like artworks, and ask questions about any piece.

## Features

- **AI artwork stories.** Each upload gets a story of 120 to 180 words, 4 to 8 mood tags, and alt text for screen readers. The AI is told to base cultural facts only on what the artist wrote, and to label everything else as interpretation.
- **Ask the artwork.** A chat box on every artwork answers visitors' questions using the artist's description.
- **Search.** Matches titles, artists, descriptions, stories and tags.
- **Accounts with two roles:**
  - **Artists** can post artwork, like pieces, and use their dashboard.
  - **Art lovers** can browse, like and chat.
  - Anyone can browse without logging in.
- **No posting under someone else's name.** The artist name comes from the logged-in account, not from the upload form, and artist names are unique.
- **Likes and views.** One like per user per artwork (click again to unlike). A view is counted each time someone opens an artwork.
- **Artist dashboard.** Total artworks, views and likes, the most-viewed piece, a views-per-artwork chart, top mood tags, and the upload form.
- **Handles a busy Gemini.** If Gemini is overloaded, the app retries and then switches to a backup model.

## Tech stack

| Part | Tools |
|---|---|
| Backend | Python, Flask |
| Database | SQLite (`art_roots.db`) |
| Images | Saved in `uploads/`; checked and resized with Pillow |
| AI | Google Gemini via the `google-genai` SDK |
| Frontend | Plain HTML, CSS and JavaScript (no framework) |
| Auth | Flask sessions; passwords hashed with Werkzeug |
| Tests | Python `unittest` with a fake AI service |

## Getting started

You need **Python 3.12 or newer** and a **Gemini API key** from [Google AI Studio](https://aistudio.google.com/apikey).

**1. Clone the repo and install the packages**

```bash
git clone https://github.com/subhashsangondi/Art-Roots.git
cd Art-Roots
python -m venv .venv
```

Activate the environment:

```bash
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
```

Then install:

```bash
pip install -r requirements.txt
```

**2. Create a `.env` file** in the project folder:

```env
GEMINI_API_KEY=your-gemini-api-key
GEMINI_MODEL=gemini-3.5-flash
SECRET_KEY=any-long-random-text
```

**3. Run the app**

```bash
python app.py
```

Open http://127.0.0.1:5000. The database and `uploads/` folder are created automatically on first run.

**4. Try it out**

1. Go to `/login`, click **Sign up**, and choose **An artist**.
2. You'll land on your dashboard. Upload an artwork and wait about 15 seconds for the AI story.
3. In a private window, sign up as **An art lover**. Open the artwork, like it, and ask it a question.
4. Back on the artist's dashboard, the view and like appear in the stats.

## Configuration

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `GEMINI_API_KEY` | Yes | none | Gemini API key (`GOOGLE_API_KEY` also works) |
| `GEMINI_MODEL` | No | `gemini-3.6-flash` | Main model for stories and chat |
| `GEMINI_FALLBACK_MODELS` | No | `gemini-3.5-flash` | Comma-separated backup models to use when the main model is busy |
| `SECRET_KEY` | Recommended | random each start | Signs login cookies. Without it, everyone is logged out on restart |
| `GEMINI_BASE_URL` | No | none | Send Gemini calls through a proxy (e.g. LiteLLM). `NEXUS_BASE_URL` also works |
| `FLASK_DEBUG` | No | off | Set to `1` for auto-reload while developing |

## Project structure

```
Art-Roots/
├── app.py              # Flask app: routes, auth, database
├── ai_service.py       # Gemini calls: stories, chat, retry and fallback
├── requirements.txt
├── templates/
│   ├── index.html      # Home page: gallery and search
│   ├── login.html      # Log in / sign up
│   └── dashboard.html  # Artist dashboard and upload form
├── static/
│   ├── app.js          # Gallery, search, likes, chat
│   ├── login.js
│   ├── dashboard.js
│   └── style.css
└── tests/
    └── test_app.py
```

## API

| Method | Endpoint | Who | What it does |
|---|---|---|---|
| POST | `/api/auth/signup` | anyone | Create an account (`username`, `password`, `role`, `display_name`) |
| POST | `/api/auth/login` | anyone | Log in |
| POST | `/api/auth/logout` | anyone | Log out |
| GET | `/api/auth/me` | anyone | The current user, or `null` |
| GET | `/api/artworks` | anyone | All artworks with like counts |
| POST | `/api/artworks` | artists | Upload an artwork (`title`, `description`, `image`) |
| GET | `/api/artworks/<id>` | anyone | One artwork |
| POST | `/api/artworks/<id>/view` | anyone | Count a view |
| POST | `/api/artworks/<id>/like` | logged in | Like or unlike |
| POST | `/api/artworks/<id>/chat` | anyone | Ask a question about the artwork |
| POST | `/api/search` | anyone | Search by text (`query`) |
| GET | `/api/dashboard` | artists | The logged-in artist's stats and artworks |

## Running the tests

```bash
python -m unittest discover -s tests
```

The tests use a fake AI service, so they don't need an API key or network access.

## Troubleshooting

- **"Gemini is very busy right now"**: Google's servers are overloaded. Wait a few seconds and try again, or set `GEMINI_MODEL=gemini-3.5-flash` in `.env`.
- **"Incorrect username or password" on a fresh setup**: the database starts with no accounts. Sign up first.
- **"Please match the requested format" on login**: usernames can't contain spaces. Use the username, not the artist name.
- **Old pages after updating the code**: stop every running copy of the app (Ctrl+C) and start one fresh. Two servers on the same port will confuse each other.

## Data and privacy

- `.env`, `art_roots.db` and `uploads/` are in `.gitignore`, so API keys, accounts and images never reach GitHub.
- Passwords are stored as one-way hashes and can't be read back.
- For production, the plan is to move data to PostgreSQL and images to cloud storage such as Cloudinary or S3. The code already stores images apart from the data, so that's a small change.
