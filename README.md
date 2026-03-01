# LunchMenu

A two-part project that turns a Google Sheets school lunch menu into a clean JSON API consumed by a Chrome extension.

## Project Structure

```
repo/
├── backend/          # FastAPI app (Python)
│   ├── main.py       # FastAPI entry point – /health, /menu, /refresh
│   ├── sheets.py     # Google Sheets fetching & tab selection
│   ├── parser.py     # Merge-aware parsing + EN/TH row pairing
│   ├── auth.py       # OAuth (local dev) and ADC/service-account auth
│   ├── cache.py      # In-memory TTL cache
│   ├── requirements.txt
│   ├── .env.example
│   └── tests/
│       └── test_parser.py   # Unit tests (mocked data, no API calls)
├── extension/        # Chrome Extension (Manifest V3)
│   ├── manifest.json
│   ├── popup.html / popup.js / popup.css   # Today + weekly menu UI
│   ├── options.html / options.js           # Backend URL settings page
│   ├── background.js                       # Service worker
│   └── managed_schema.json                 # Admin-policy key schema
└── README.md
```

---

## Backend – Local Development Setup

### Prerequisites

- Python 3.10+
- A Google Cloud project with the **Google Sheets API** enabled
- The spreadsheet shared with your Google account (or service account)

### 1. Install dependencies

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment variables

```bash
cp .env.example .env
# Edit .env and set:
#   SPREADSHEET_ID=<your Google Sheets spreadsheet ID>
#   REFRESH_TOKEN_SECRET=<a long random secret>
```

### 3. Set up OAuth credentials for local dev

1. Go to [Google Cloud Console → APIs & Services → Credentials](https://console.cloud.google.com/apis/credentials).
2. Click **Create Credentials → OAuth client ID**.
3. Choose **Desktop app**, give it a name, click **Create**.
4. Download the JSON file and save it as `backend/credentials.json`.
5. On first run, a browser window will open for you to authorise access. The token is saved to `backend/token.json` for subsequent runs.

> **Scopes required:** `https://www.googleapis.com/auth/spreadsheets.readonly`

### 4. Run the backend

```bash
cd backend
uvicorn main:app --reload --port 8000
```

The API is now available at `http://localhost:8000`.

---

## Backend – Production (Service Account)

1. In Google Cloud Console, create a **Service Account** and download its JSON key.
2. Set the environment variable `GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json` (Application Default Credentials).
3. **Share the spreadsheet** with the service account email address (e.g. `my-sa@project.iam.gserviceaccount.com`) as a Viewer.
4. Do **not** place `credentials.json` or `token.json` in the production environment – the code will automatically use ADC when those files are absent.

---

## API Endpoints

| Method | Path       | Description                                           |
|--------|------------|-------------------------------------------------------|
| GET    | `/health`  | Returns `{"ok": true}` – use for health checks        |
| GET    | `/menu`    | Returns the current week's normalised menu JSON       |
| POST   | `/refresh` | Forces re-fetch from Sheets (requires `X-Refresh-Token` header) |

### Example `/menu` response

```json
{
  "week": {
    "start": "2026-03-02",
    "end": "2026-03-06",
    "label": "2-6 March, 2026"
  },
  "lastFetched": "2026-03-02T08:00:00+00:00",
  "menus": {
    "alacarte": {
      "days": {
        "monday": [
          {
            "category": "Thai food",
            "items": [
              { "en": "Pad Thai", "th": "ผัดไทย" },
              { "en": "Pad See Ew", "th": "ผัดซีอิ๊ว" }
            ]
          }
        ],
        "tuesday": [ "..." ],
        "wednesday": [ "..." ],
        "thursday": [ "..." ],
        "friday": [ "..." ]
      }
    },
    "program": {
      "days": { "..." }
    }
  },
  "source": {
    "spreadsheetId": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms",
    "selectedSheets": [
      { "title": "Lunch Ala Carte (Mar 2-6)", "sheetId": 0 },
      { "title": "Lunch Program (Mar 2-6)", "sheetId": 1 }
    ]
  }
}
```

### Forcing a refresh

```bash
curl -X POST http://localhost:8000/refresh \
  -H "X-Refresh-Token: your_secret_here"
```

---

## Running Tests

```bash
cd backend
pip install pytest python-dateutil
python -m pytest tests/ -v
```

The test suite uses mocked/static data – no real Google Sheets API calls are made.

---

## Chrome Extension – Loading in Chrome

1. Open Chrome and go to `chrome://extensions`.
2. Enable **Developer mode** (top-right toggle).
3. Click **Load unpacked** and select the `extension/` directory.
4. The **Lunch Menu** extension icon will appear in the toolbar.

### Configuring the backend URL

- **Via the Options page:** Click the extension icon → ⚙ Settings → enter your backend URL → Save.
- **Via managed policy (admin):** Deploy a Chrome policy setting the key `MENU_API_URL` to your backend URL. When set, the field is locked and shows a notice.

---

## Spreadsheet Format Assumptions

The parser is resilient to row shifts but assumes:

- **Tab names** contain "ala carte" or "program" (case-insensitive).
- **Row 1** of each tab has merged cells: title on the left, week date range (`2-6 March, 2026` or `30 March – 3 April, 2026`) on the right.
- **Column A** uses merged regions to mark category blocks (≥ 2 rows merged = a category).
- **Columns B–F** (or detected from the header row) hold Mon–Fri data.
- Within each category block, rows alternate: English row then Thai row.

> **TODO:** If your spreadsheet uses a different column layout or row structure, adjust the `_detect_day_columns()` function in `backend/parser.py` and tune the merge detection thresholds.

---

## Caching

The backend caches parsed menu data in memory with a TTL (default **6 hours**). Configure via the `CACHE_TTL_SECONDS` environment variable. Call `POST /refresh` to force a re-fetch at any time.
