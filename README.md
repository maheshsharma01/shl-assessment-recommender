# SHL Assessment Recommender

Conversational FastAPI agent for recommending SHL Individual Test Solutions.

## Endpoints

- `GET /health` → `{"status": "ok"}`
- `POST /chat` → conversational recommender

## Quick Start (Local)

```bash
# 1. Clone / unzip the project
cd shl-recommender

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set your API key
cp .env.example .env
# Edit .env and set ANTHROPIC_API_KEY=sk-ant-...

# 5. Run
uvicorn main:app --reload --port 8000

# 6. Test
curl http://localhost:8000/health
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"I need to hire a Java developer"}]}'
```

## Deployment on Render (Free)

1. Push this folder to a GitHub repository
2. Go to https://render.com → New Web Service
3. Connect your repo
4. Set environment variable: `ANTHROPIC_API_KEY=sk-ant-...`
5. Build command: `pip install -r requirements.txt`
6. Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
7. Click Deploy

Your API will be at `https://your-service-name.onrender.com`

## Deployment on Railway

```bash
# Install Railway CLI
npm install -g @railway/cli
railway login
railway new
railway add
# Set env var in Railway dashboard: ANTHROPIC_API_KEY
railway up
```

## Docker

```bash
docker build -t shl-recommender .
docker run -p 8000:8000 -e ANTHROPIC_API_KEY=sk-ant-... shl-recommender
```

## API Example

**Request:**
```json
POST /chat
{
  "messages": [
    {"role": "user", "content": "Hiring a Java developer who works with stakeholders"},
    {"role": "assistant", "content": "Sure. What seniority level is this role?"},
    {"role": "user", "content": "Mid-level, around 4 years"}
  ]
}
```

**Response:**
```json
{
  "reply": "Here are 5 assessments suited for a mid-level Java developer with stakeholder interaction:",
  "recommendations": [
    {"name": "Java 8 (New)", "url": "https://www.shl.com/solutions/products/product-catalog/view/java-8-new/", "test_type": "K"},
    {"name": "OPQ32r", "url": "https://www.shl.com/solutions/products/product-catalog/view/opq32r/", "test_type": "P"}
  ],
  "end_of_conversation": false
}
```

## Files

```
shl-recommender/
├── main.py              # FastAPI application
├── catalog.json         # SHL product catalog (99 products)
├── scrape_catalog.py    # Catalog scraper (re-run to refresh)
├── requirements.txt
├── Dockerfile
├── render.yaml          # Render deployment config
├── .env.example
├── approach_document.md # 2-page approach doc for submission
└── README.md
```

## Refreshing the Catalog

```bash
python scrape_catalog.py
# Outputs updated catalog.json
```
