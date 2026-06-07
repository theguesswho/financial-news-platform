# Quick Start Guide

Get the Financial News Platform running in 5 minutes.

---

## Prerequisites

- Python 3.13+
- PostgreSQL 12+ (running locally or remote)
- Git

## One-Time Setup

### 1. Clone & Navigate
```bash
cd ~/Desktop/financial-news-platform
```

### 2. Create Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment
Create `.env` file (if not exists):
```env
DB_HOST_IP=localhost
DB_USER=postgres
DB_PASSWORD=your_db_password
DB_NAME=postgres
JWT_SECRET_KEY=your-random-secret-key
```

### 5. Verify Database Setup
```bash
python3 test_api.py
# Should show: ✓ All tests passed!
```

---

## Run Development Server

### Start the API
```bash
python3 start_api.py
```

Output:
```
╔════════════════════════════════════════════════════════════════════════╗
║       Financial News Platform API                                      ║
╚════════════════════════════════════════════════════════════════════════╝
```

### Access API Documentation
```
http://localhost:8000/docs          ← Try API endpoints here
http://localhost:8000/openapi.json  ← OpenAPI spec
http://localhost:8000/health        ← Health check
```

---

## Common Commands

### Run Tests
```bash
python3 test_api.py
```

### View Database Tables
```bash
psql -h localhost -U postgres -d postgres -c "SELECT * FROM users LIMIT 5;"
```

### Run Daily Score Archiver
```bash
python3 pipeline/daily_score_archiver.py
```

### Check API Logs
```bash
python3 start_api.py --log-level debug
```

### Search for Stocks
```bash
curl "http://localhost:8000/api/stocks/search/Technology"
```

---

## API Example: Register & Login

### 1. Register
```bash
TOKEN_RESPONSE=$(curl -s -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "SecurePass123",
    "name": "John Investor"
  }')

# Extract token
TOKEN=$(echo $TOKEN_RESPONSE | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)
echo "Token: $TOKEN"
```

### 2. Get Watchlist
```bash
curl -X GET http://localhost:8000/api/watchlist \
  -H "Authorization: Bearer $TOKEN"
```

### 3. Add to Watchlist
```bash
curl -X POST http://localhost:8000/api/watchlist \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "AAPL",
    "entry_price": 180.50,
    "notes": "Strong fundamentals"
  }'
```

### 4. Screen Stocks
```bash
curl "http://localhost:8000/api/stocks/screener?min_score=0.70&limit=10"
```

---

## File Locations

| File | Purpose |
|------|---------|
| `api/app.py` | Main FastAPI application |
| `api/routes/*.py` | API endpoint implementations |
| `api/auth.py` | JWT & password hashing |
| `api/schemas.py` | Request/response validation |
| `db/models.py` | Database ORM models |
| `pipeline/daily_score_archiver.py` | V2 score archiver |
| `test_api.py` | Comprehensive test suite |
| `start_api.py` | API server startup script |
| `API_README.md` | Full API documentation |
| `IMPLEMENTATION_STATUS.md` | Implementation details |
| `BUILD_SUMMARY.md` | Build overview |

---

## Troubleshooting

### PostgreSQL Not Running
```bash
# Start PostgreSQL
brew services start postgresql
```

### Port 8000 Already in Use
```bash
python3 start_api.py --port 8001
```

### Database Connection Error
```bash
# Check credentials in .env
# Verify PostgreSQL is running
pg_isready -h localhost
```

### Import Errors
```bash
# Make sure you're in the venv
source venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt --force-reinstall
```

---

## Next Steps

1. **Try API Endpoints:** Visit http://localhost:8000/docs
2. **Read Documentation:** Check `API_README.md` for detailed endpoint docs
3. **Run Tests:** Execute `python3 test_api.py` to verify setup
4. **Integration:** When ready, frontend will consume these APIs

---

## Useful Resources

- **API Docs:** http://localhost:8000/docs (Swagger UI)
- **OpenAPI Spec:** http://localhost:8000/openapi.json
- **Health Check:** http://localhost:8000/health
- **Database:** Connect with `psql -h localhost -U postgres`

---

## Quick API Reference

### Auth Endpoints
```
POST   /api/auth/register          Create account
POST   /api/auth/login             Login
GET    /api/auth/me                Get current user
```

### Watchlist Endpoints
```
GET    /api/watchlist              List watchlist
POST   /api/watchlist              Add stock
DELETE /api/watchlist/{symbol}     Remove stock
```

### Portfolio Endpoints
```
GET    /api/portfolio              List holdings
GET    /api/portfolio/summary      Portfolio summary
POST   /api/portfolio              Add holding
DELETE /api/portfolio/{symbol}     Remove holding
```

### Stock Endpoints
```
GET    /api/stocks/screener        Screen stocks
GET    /api/stocks/{symbol}        Stock detail
GET    /api/stocks/search/{query}  Search
```

---

## Database Info

**Tables Created:**
- `users` — User accounts
- `watchlist_entries` — Stock watchlists
- `portfolio_holdings` — User holdings
- `daily_scores` — V2 score history
- `user_activity_log` — Action audit trail
- `fundamentals` — Stock fundamentals (with sector/analyst data)
- Plus 7 other existing tables

**Connection String:**
```
postgresql+psycopg2://postgres:password@localhost/postgres
```

---

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `DB_HOST_IP` | localhost | Database host |
| `DB_USER` | postgres | Database user |
| `DB_PASSWORD` | - | Database password |
| `DB_NAME` | postgres | Database name |
| `JWT_SECRET_KEY` | - | JWT signing key (change!) |
| `JWT_EXPIRE_MINUTES` | 1440 | Token expiration (24h) |

---

## Performance Tips

- **Screener is slow?** Add indexes: `CREATE INDEX ON fundamentals(sector, pe_trailing);`
- **API lag?** Check database connection: `pg_isready -h localhost`
- **High memory?** Reduce concurrent connections in `.env`

---

## Getting Help

1. **API Documentation:** http://localhost:8000/docs (try endpoints interactively)
2. **Test Suite:** `python3 test_api.py` (diagnose setup issues)
3. **Logs:** Run with `--log-level debug`
4. **Database:** Query directly with `psql`

---

**Ready to go!** 🚀

```bash
python3 start_api.py
# Then visit http://localhost:8000/docs
```
