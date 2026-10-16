# AI Travel Advisor

A travel-planning API built with FastAPI and OpenAI. It can create personalized itineraries and, when relevant, retrieve weather forecasts, approximate currency conversions, and current transport information.

## Features

- Trip plans with a summary, day-by-day itinerary, practical tips, and estimated budget
- Weather forecasts for eligible dates within the next 16 days
- Approximate currency conversion
- Web search for current public-transport information
- Follow-up conversations using response IDs

## Requirements

- Python 3.10 or newer
- An OpenAI API key

## Local setup

From the project root, create and activate a virtual environment on macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install the project dependencies:

```bash
pip install -r requirements.txt
```

Create a `.env` file in the project root:

```env
OPENAI_API_KEY=your_openai_api_key
```

Do not commit `.env` or share your API key.

## Run locally

Start the FastAPI server:

```bash
uvicorn app.index:app --reload
```

- API documentation: <http://127.0.0.1:8000/docs>
- Health check: <http://127.0.0.1:8000/health>

The command-line version can be run separately:

```bash
python -m app.main
```

## React frontend

The Vite + React app is in `frontend/` and runs separately from the FastAPI
service. JavaScript dependencies are listed in `frontend/package.json`; install
Node.js 18 or newer, then from the repository root run:

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

Open the local URL printed by Vite. The example environment file points the
frontend at the deployed API; change `VITE_API_BASE_URL` in `.env` to use another
API URL.

### Deploy on Vercel

Create a Vercel project linked to this repository and set **Root Directory** to
`frontend`. Vercel detects Vite automatically; use `npm run build` as the build
command and `dist` as the output directory. Add this environment variable in the
Vercel project settings:

```env
VITE_API_BASE_URL=https://mini-project-ai-travel-advisor.onrender.com
```

Keep `OPENAI_API_KEY` on the FastAPI service in Render. Do not add it to the
React app or Vercel environment.

## API

### `GET /health`

Returns the service status:

```json
{
  "status": "ok"
}
```

### `POST /chat`

Send a JSON request:

```json
{
  "message": "Plan a 3-day trip to Barcelona focused on food and architecture."
}
```

If more trip details are needed, the response contains a follow-up message:

```json
{
  "status": "needs_info",
  "response_id": "...",
  "message": "How many days will you be traveling?"
}
```

When the required details are available, the response contains a structured plan:

```json
{
  "status": "complete",
  "response_id": "...",
  "plan": {
    "title": "A Taste of Barcelona",
    "summary": "Three days of food and architecture.",
    "itinerary": "Day 1: ...",
    "practical_tips": "...",
    "budget": "Estimated per-person budget: EUR 600.",
    "sources": []
  }
}
```

To continue the conversation, send the returned `response_id` as `previous_response_id`:

```json
{
  "message": "What public transport options should I consider?",
  "previous_response_id": "..."
}
```

Example using `curl`:

```bash
curl -X POST "http://127.0.0.1:8000/chat" \
  -H "Content-Type: application/json" \
  -d '{"message":"Plan a 3-day trip to Barcelona focused on food and architecture."}'
```

## Deploy on Render

Create a Render **Web Service** connected to your repository.

- **Build command:** `pip install -r requirements.txt`
- **Start command:** `uvicorn app.index:app --host 0.0.0.0 --port $PORT`
- Add `OPENAI_API_KEY` in the service’s **Environment** settings.

After deployment, use your Render service URL with `/health` or `/chat`. Never put the API key in source code or in a request body.

## Notes

- Weather and exchange-rate information depend on external services and may be unavailable.
- Forecasts are limited to the supported forecast window; longer-range weather should be treated as seasonal guidance.
- Currency conversions are approximate and may differ from rates offered by banks or card providers.
- Requests can take longer when AI tools or web search are used. Render cold starts may also add latency.
