# SEC Filing Tracker

A Streamlit dashboard that pulls the latest ~100 SEC EDGAR filings and ranks them by market cap and stock price using live Yahoo Finance data.

## Features
- Fetches live filings from SEC EDGAR (10-K, 10-Q, 8-K, Form 4, S-1, and more)
- Enriches each filing with the company's stock ticker via SEC's submissions API
- Pulls real-time price, day % change, and market cap via yfinance
- Ranks filings by market cap, price, or % change (your choice)
- Search/filter by company name
- Company detail panel with 1-month price chart
- Direct links to each filing on EDGAR

## Setup

```bash
pip install -r requirements.txt
streamlit run app.py
```

Then open http://localhost:8501 in your browser.

## Notes
- Requires a live internet connection to reach SEC.gov and Yahoo Finance
- Market data is cached for 3 minutes; filing list is cached for 5 minutes
- Not all filings have a matching stock ticker (private companies, funds, etc.)
- Not financial advice
