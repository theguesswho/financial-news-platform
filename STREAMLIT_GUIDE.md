# FinanceIQ Streamlit App - User Guide

Your personal stock research and portfolio management tool.

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements-streamlit.txt
```

### 2. Make Sure PostgreSQL is Running

Verify your database is running:
```bash
psql -U postgres -d financialnewsplatform -c "SELECT COUNT(*) FROM fundamentals;"
```

### 3. Start the App

```bash
streamlit run streamlit_app.py
```

The app will open in your browser at `http://localhost:8501`

---

## 📊 Features

### Dashboard
- Quick overview of your stock database
- Key statistics and metrics
- Navigation to other features

### 🔍 Stock Screener
Find stocks matching your criteria:
- **V2 Score Filter**: Minimum score for opportunity quality
- **Quality Score**: Profitability & efficiency (ROE, margins)
- **Value Score**: Valuation metrics (P/E, P/B, FCF)
- **Trajectory Score**: Growth & momentum trends
- **P/E Ratio Filter**: Maximum P/E to consider
- **Sector Filter**: Find stocks in specific sectors
- **Results Display**: See distribution charts and full data

**Color Coding:**
- 🟢 Green (≥0.8): Excellent
- 🟡 Yellow (≥0.6): Good
- 🟠 Orange (≥0.4): Fair
- 🔴 Red (<0.4): Poor

### ⚙️ Customize Scoring
Adjust the V2 scoring weights to match YOUR investment style:

**Default Weights:**
- Quality: 40%
- Value: 35%
- Trajectory: 25%

**How to Use:**
1. Move the sliders to adjust each component's importance
2. See your custom weights update in real-time
3. Example calculation shows how your new weights affect scores
4. Screener automatically uses your custom weights

**Customization Examples:**
- **Growth Investor**: Increase Trajectory (50%), decrease Value (20%)
- **Value Investor**: Increase Value (60%), decrease Quality (20%)
- **Balanced**: Keep defaults (40/35/25)
- **Quality First**: Increase Quality (60%), decrease Trajectory (10%)

### 👁️ Watchlist
Track stocks you want to monitor:
- Add stocks by symbol
- See real-time scores and metrics
- Remove stocks with one click
- Your watchlist persists during the session

---

## 💡 How the V2 Score Works

**V2 Score = ∛(Quality × Value × Trajectory)**

### Components

**Quality Score** (Default 40%)
- ROE (Return on Equity)
- ROIC (Return on Invested Capital)
- Gross, Operating, Net Margins
- FCF Margin (Free Cash Flow / Revenue)

Measures: How profitable and efficient is the business?

**Value Score** (Default 35%)
- P/E Ratio (Price-to-Earnings)
- P/B Ratio (Price-to-Book)
- EV/EBITDA (Enterprise Value / EBITDA)
- Price-to-FCF

Measures: Is the stock trading at a discount?

**Trajectory Score** (Default 25%)
- Revenue Growth YoY
- Earnings Growth YoY
- FCF Growth Trends
- Momentum & Acceleration

Measures: Are fundamentals improving?

---

## 🎯 Usage Examples

### Example 1: Find High-Quality Dividend Stocks
1. Go to **Customize Scoring**
   - Quality: 60%
   - Value: 30%
   - Trajectory: 10%
2. Go to **Screener**
   - Min V2 Score: 0.75
   - Max P/E: 20
   - Min Value Score: 0.60
3. Look for stocks with high Quality & low P/E

### Example 2: Find Growth Opportunities
1. Go to **Customize Scoring**
   - Quality: 30%
   - Value: 20%
   - Trajectory: 50%
2. Go to **Screener**
   - Min V2 Score: 0.60
   - Min Trajectory: 0.70
3. Find companies with strong growth trends

### Example 3: Find Undervalued Gems
1. Go to **Customize Scoring**
   - Quality: 40%
   - Value: 50%
   - Trajectory: 10%
2. Go to **Screener**
   - Min V2 Score: 0.65
   - Max P/E: 15
   - Min Value Score: 0.75
3. Discover undervalued quality companies

---

## ⚙️ Configuration

Make sure your `.env` file has:

```
DB_HOST_IP=localhost
DB_PASSWORD=your_password
DB_USER=postgres
DB_NAME=financialnewsplatform
```

---

## 🐛 Troubleshooting

**Error: "Database connection error"**
- Make sure PostgreSQL is running
- Check your .env file is correct
- Test connection: `psql -U postgres -d financialnewsplatform`

**Error: "No stocks match your criteria"**
- Adjust filters to be less restrictive
- Check that you have data in the fundamentals table
- Try lowering the minimum V2 score

**App won't start**
- Install dependencies: `pip install -r requirements-streamlit.txt`
- Check Python version (3.8+)
- Try: `streamlit run streamlit_app.py --logger.level=debug`

---

## 💾 Customization Tips

### Add More Metrics
The screener queries the `fundamentals` and `daily_scores` tables. You can add columns like:
- Debt-to-Equity
- Current Ratio
- Short Interest
- Analyst Ratings

### Modify Colors
In the `page_screener()` function, adjust the color thresholds:
```python
if val >= 0.8:  # Change these thresholds
    return 'background-color: #90EE90'
```

### Change Default Weights
Edit `compute_v2_score()` function:
```python
weights = {"quality": 0.40, "value": 0.35, "trajectory": 0.25}
```

---

## 📈 Next Steps

1. **Populate Data**: Load stock fundamentals and daily scores
2. **Run Backtests**: Test your custom weights on historical data
3. **Set Alerts**: Get notified when stocks meet your criteria
4. **Export Results**: Save screener results to CSV

---

## 🎓 Learning Resources

- **Streamlit Docs**: streamlit.io/docs
- **Plotly Visualization**: plotly.com
- **Stock Metrics Explained**: investopedia.com
- **Investment Strategies**: sec.gov/investor

---

**Last Updated**: June 2026  
**Version**: 1.0.0
