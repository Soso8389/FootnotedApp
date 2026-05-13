"""
SEC Filing Tracker — Streamlit App
Run locally:
    pip install -r requirements.txt
    streamlit run app.py
"""

import streamlit as st
import requests
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
import re

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="SEC Filing Tracker",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=Syne:wght@700;800&display=swap');

html, body, [class*="css"] { font-family: 'IBM Plex Mono', monospace; }

.stApp { background: #0a0c0f; color: #e8eaf0; }

section[data-testid="stSidebar"] {
    background: #111318 !important;
    border-right: 1px solid rgba(255,255,255,0.07);
}
section[data-testid="stSidebar"] * { color: #e8eaf0 !important; }

.stApp::before {
    content: '';
    position: fixed; inset: 0;
    background-image:
        linear-gradient(rgba(0,229,160,0.018) 1px, transparent 1px),
        linear-gradient(90deg, rgba(0,229,160,0.018) 1px, transparent 1px);
    background-size: 48px 48px;
    pointer-events: none; z-index: 0;
}

/* Header */
.sec-header { display:flex; align-items:center; gap:14px; margin-bottom:1.5rem; }
.sec-logo {
    width:44px; height:44px; background:#00e5a0; border-radius:5px;
    display:flex; align-items:center; justify-content:center;
    font-family:'Syne',sans-serif; font-weight:800; font-size:13px;
    color:#000; letter-spacing:-0.5px; flex-shrink:0;
}
.sec-title {
    font-family:'Syne',sans-serif; font-size:1.6rem;
    font-weight:800; color:#e8eaf0; letter-spacing:-0.5px;
}
.sec-sub {
    font-size:10px; color:#6b7280; text-transform:uppercase;
    letter-spacing:0.8px; margin-top:3px;
}

/* Status bar */
.status-bar {
    font-size:10px; color:#6b7280; letter-spacing:0.3px;
    padding:8px 0 18px;
    border-bottom:1px solid rgba(255,255,255,0.07);
    margin-bottom:1.2rem;
}
.live-dot {
    display:inline-block; width:7px; height:7px; border-radius:50%;
    background:#00e5a0; box-shadow:0 0 6px #00e5a0;
    animation:blink 2s infinite; margin-right:6px; vertical-align:middle;
}
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:0.4} }

.section-head {
    font-family:'Syne',sans-serif; font-size:1rem; font-weight:700;
    color:#e8eaf0; margin:1.5rem 0 0.75rem; letter-spacing:-0.3px;
}

/* Sidebar button */
.stButton > button {
    background:#00e5a0 !important; color:#000 !important;
    border:none !important; border-radius:4px !important;
    font-family:'IBM Plex Mono',monospace !important;
    font-size:12px !important; font-weight:500 !important;
    width:100%; padding:10px !important; cursor:pointer;
}
.stButton > button:hover { background:#00c98a !important; }

/* Metric cards */
[data-testid="metric-container"] {
    background:#111318 !important;
    border:1px solid rgba(255,255,255,0.07) !important;
    border-radius:5px !important; padding:14px 18px !important;
}
[data-testid="metric-container"] label {
    color:#6b7280 !important; font-size:10px !important;
    text-transform:uppercase; letter-spacing:0.8px;
}
[data-testid="metric-container"] [data-testid="stMetricValue"] {
    color:#e8eaf0 !important; font-size:1.35rem !important;
}

/* Sidebar input labels */
.stSelectbox label, .stMultiSelect label, .stSlider label,
.stRadio label, .stTextInput label {
    color:#9ca3af !important; font-size:10px !important;
    text-transform:uppercase; letter-spacing:0.5px;
}

hr { border-color:rgba(255,255,255,0.07) !important; }
</style>
""", unsafe_allow_html=True)

# ── Constants ──────────────────────────────────────────────────────────────────
HEADERS = {
    "User-Agent": "SEC-Dashboard-App contact@yourdomain.com",
    "Accept-Encoding": "gzip, deflate",
    "Accept": "application/json, text/html, */*",
}
NS = {"atom": "http://www.w3.org/2005/Atom"}
FORM_TYPES_ALL = ["10-K", "10-Q", "8-K", "4", "S-1", "DEF 14A", "SC 13G", "SC 13D"]

# ── Formatters ─────────────────────────────────────────────────────────────────
def fmt_mcap(v):
    if v is None or (isinstance(v, float) and v != v): return "—"
    if v >= 1e12: return f"${v/1e12:.2f}T"
    if v >= 1e9:  return f"${v/1e9:.2f}B"
    if v >= 1e6:  return f"${v/1e6:.2f}M"
    return f"${v:,.0f}"

def fmt_price(v):
    if v is None or (isinstance(v, float) and v != v): return "—"
    return f"${v:,.2f}"

def fmt_chg(v):
    if v is None or (isinstance(v, float) and v != v): return "—"
    arrow = "▲ +" if v >= 0 else "▼ "
    return f"{arrow}{v:.2f}%"

# ── Data functions ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def fetch_edgar_rss(form_type: str, count: int = 40) -> list:
    """Fetch recent filings from SEC EDGAR Atom feed."""
    url = (
        "https://www.sec.gov/cgi-bin/browse-edgar"
        f"?action=getcurrent&type={requests.utils.quote(form_type)}"
        f"&dateb=&owner=include&count={count}&search_text=&output=atom"
    )
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        rows = []
        for entry in root.findall("atom:entry", NS):
            title_el   = entry.find("atom:title",   NS)
            updated_el = entry.find("atom:updated", NS)
            link_el    = entry.find("atom:link",    NS)

            title   = (title_el.text   or "").strip()
            updated = (updated_el.text or "").strip()
            link    = link_el.get("href", "") if link_el is not None else ""

            # Parse "FORM - ENTITY (CIK XXXXXXXXXX)" or "FORM - ENTITY"
            entity, cik = title, ""
            m = re.match(r"^[^\-]+-\s*(.+?)\s*\(CIK\s*(\d+)\)\s*$", title, re.I)
            if m:
                entity = m.group(1).strip()
                cik    = m.group(2).zfill(10)
            else:
                parts = title.split(" - ", 1)
                if len(parts) == 2:
                    entity = parts[1].strip()

            rows.append({
                "entity_name": entity,
                "form_type":   form_type,
                "file_date":   updated[:10],
                "cik":         cik,
                "link":        link,
            })
        return rows
    except Exception:
        return []

@st.cache_data(ttl=300, show_spinner=False)
def get_ticker_for_cik(cik: str):
    if not cik:
        return None
    try:
        r = requests.get(
            f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json",
            headers=HEADERS, timeout=8,
        )
        r.raise_for_status()
        tickers = r.json().get("tickers", [])
        return tickers[0].upper() if tickers else None
    except Exception:
        return None

@st.cache_data(ttl=180, show_spinner=False)
def get_market_data(ticker: str):
    if not ticker:
        return None, None, None
    try:
        info   = yf.Ticker(ticker).fast_info
        price  = getattr(info, "last_price",     None)
        mcap   = getattr(info, "market_cap",     None)
        prev   = getattr(info, "previous_close", None)
        chg    = ((price - prev) / prev * 100) if (price and prev) else None
        return price, chg, mcap
    except Exception:
        return None, None, None

@st.cache_data(ttl=180, show_spinner=False)
def get_price_history(ticker: str):
    try:
        hist = yf.Ticker(ticker).history(period="1mo", interval="1d")
        if hist.empty:
            return None
        return hist[["Close"]].rename(columns={"Close": "Price ($)"})
    except Exception:
        return None

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙ Controls")
    st.markdown("---")

    selected_forms = st.multiselect(
        "Filing Types",
        FORM_TYPES_ALL,
        default=["10-K", "10-Q", "8-K"],
    )

    sort_by = st.selectbox("Sort By", [
        "Market Cap ↓", "Market Cap ↑",
        "Stock Price ↓", "Stock Price ↑",
        "% Change ↓", "% Change ↑",
        "Filing Date ↓",
    ])

    search_term = st.text_input("Search Company", placeholder="e.g. Tesla")
    show_n      = st.slider("Max rows", 10, 100, 40, step=5)

    st.markdown("---")
    refresh = st.button("🔄  Refresh Data")
    st.markdown(
        "<div style='font-size:10px;color:#6b7280;line-height:1.8;margin-top:8px'>"
        "📡 SEC EDGAR + Yahoo Finance<br>"
        "⏱ Market data cached 3 min<br>"
        "📋 Filings cached 5 min"
        "</div>",
        unsafe_allow_html=True,
    )

# ── Header ─────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="sec-header">
  <div class="sec-logo">SEC</div>
  <div>
    <div class="sec-title">SEC Filing Tracker</div>
    <div class="sec-sub">Live EDGAR filings · Ranked by market cap &amp; price · Yahoo Finance</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Fetch ──────────────────────────────────────────────────────────────────────
if refresh:
    st.cache_data.clear()

forms_to_fetch = selected_forms if selected_forms else ["10-K", "10-Q", "8-K"]

with st.spinner("Fetching SEC EDGAR filings…"):
    all_filings = []
    per_form = max(20, 120 // len(forms_to_fetch))
    for form in forms_to_fetch:
        all_filings.extend(fetch_edgar_rss(form, count=per_form))

if not all_filings:
    st.error(
        "⚠️ Could not reach SEC EDGAR. "
        "Run this app **locally** with an internet connection:\n\n"
        "```\nstreamlit run app.py\n```"
    )
    st.stop()

# ── Enrich ─────────────────────────────────────────────────────────────────────
pb = st.progress(0, text="Fetching market data…")
cik_cache: dict = {}

for i, f in enumerate(all_filings):
    cik = f["cik"]
    if cik not in cik_cache:
        ticker           = get_ticker_for_cik(cik)
        price, chg, mcap = get_market_data(ticker) if ticker else (None, None, None)
        cik_cache[cik]   = (ticker, price, chg, mcap)
    ticker, price, chg, mcap = cik_cache[cik]
    f.update({"ticker": ticker, "price": price, "chg": chg, "mcap": mcap})
    pb.progress((i + 1) / len(all_filings), text=f"Market data… {i+1}/{len(all_filings)}")

pb.empty()
df = pd.DataFrame(all_filings)

# ── Filter ─────────────────────────────────────────────────────────────────────
if search_term:
    df = df[df["entity_name"].str.contains(search_term, case=False, na=False)]

# ── Sort ───────────────────────────────────────────────────────────────────────
sort_map = {
    "Market Cap ↓":  ("mcap",      False),
    "Market Cap ↑":  ("mcap",      True),
    "Stock Price ↓": ("price",     False),
    "Stock Price ↑": ("price",     True),
    "% Change ↓":    ("chg",       False),
    "% Change ↑":    ("chg",       True),
    "Filing Date ↓": ("file_date", False),
}
scol, sasc = sort_map.get(sort_by, ("mcap", False))

if scol == "file_date":
    df_sorted = df.sort_values(scol, ascending=sasc)
else:
    df_sorted = pd.concat([
        df[df["mcap"].notna()].sort_values(scol, ascending=sasc),
        df[df["mcap"].isna()],
    ])
df_sorted = df_sorted.head(show_n).reset_index(drop=True)

# ── Metrics ────────────────────────────────────────────────────────────────────
avg_chg  = df["chg"].mean()
top_mcap = df["mcap"].max()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Filings Fetched",  f"{len(df):,}")
c2.metric("With Market Data", f"{int(df['mcap'].notna().sum()):,}")
c3.metric("Avg Day Change",   f"{avg_chg:+.2f}%" if avg_chg == avg_chg else "—")
c4.metric("Largest Cap",      fmt_mcap(top_mcap))

st.markdown(
    f"<div class='status-bar'>"
    f"<span class='live-dot'></span>"
    f"Live · {len(all_filings)} filings loaded · "
    f"Updated {datetime.now().strftime('%H:%M:%S')} · "
    f"Forms: {', '.join(forms_to_fetch)}"
    f"</div>",
    unsafe_allow_html=True,
)

# ── Table ──────────────────────────────────────────────────────────────────────
st.markdown("<div class='section-head'>📋 Filings ranked by market data</div>",
            unsafe_allow_html=True)

rows = []
for i, row in df_sorted.iterrows():
    rows.append({
        "Rank":       f"#{i+1}",
        "Company":    row.get("entity_name", "Unknown"),
        "Ticker":     row.get("ticker") or "—",
        "Form":       row.get("form_type", "?"),
        "Filed":      row.get("file_date", ""),
        "Price":      fmt_price(row.get("price")),
        "Day Change": fmt_chg(row.get("chg")),
        "Market Cap": fmt_mcap(row.get("mcap")),
        "_link":      row.get("link", ""),
    })

disp_df = pd.DataFrame(rows)

def style_change(val):
    if "▲" in str(val): return "color: #34d399; font-weight: 500"
    if "▼" in str(val): return "color: #f87171; font-weight: 500"
    return "color: #6b7280"

def style_form(val):
    c = {"10-K":"#00e5a0","10-Q":"#38bdf8","8-K":"#fbbf24","4":"#c084fc","S-1":"#fb923c"}
    return f"color: {c.get(val,'#9ca3af')}; font-weight: 500"

def style_rank(val):
    return "color: #00e5a0; font-weight: 500" if val in ("#1","#2","#3") else "color: #6b7280"

styled = (
    disp_df.drop(columns=["_link"])
    .style
    .map(style_change, subset=["Day Change"])
    .map(style_form,   subset=["Form"])
    .map(style_rank,   subset=["Rank"])
    .set_properties(**{
        "background-color": "#111318",
        "color": "#e8eaf0",
        "border-color": "rgba(255,255,255,0.05)",
        "font-family": "'IBM Plex Mono', monospace",
        "font-size": "12px",
    })
    .set_table_styles([{"selector": "th", "props": [
        ("background-color", "#191c23"),
        ("color", "#6b7280"),
        ("font-size", "10px"),
        ("text-transform", "uppercase"),
        ("letter-spacing", "0.8px"),
        ("border-bottom", "1px solid rgba(255,255,255,0.08)"),
    ]}])
    .hide(axis="index")
)

st.dataframe(styled, use_container_width=True, height=560)

# ── Detail panel ───────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("<div class='section-head'>🔍 Company Detail</div>", unsafe_allow_html=True)

companies = disp_df["Company"].tolist()
selected  = st.selectbox("Pick a company", companies, label_visibility="collapsed")

if selected:
    sel = df_sorted[df_sorted["entity_name"] == selected]
    if not sel.empty:
        r      = sel.iloc[0]
        ticker = r.get("ticker")

        mc1, mc2, mc3, mc4, mc5 = st.columns(5)
        mc1.metric("Ticker",      ticker or "N/A")
        mc2.metric("Form",        r.get("form_type","?"))
        mc3.metric("Price",       fmt_price(r.get("price")))
        mc4.metric("Day Change",  fmt_chg(r.get("chg")))
        mc5.metric("Market Cap",  fmt_mcap(r.get("mcap")))

        ic1, ic2, ic3 = st.columns(3)
        ic1.markdown(f"**Filed:** `{r.get('file_date','—')}`")
        ic2.markdown(f"**CIK:** `{r.get('cik','—')}`")
        if r.get("link"):
            ic3.markdown(f"[📄 View on EDGAR ↗]({r['link']})")

        if ticker:
            with st.spinner(f"Loading {ticker} price history…"):
                hist_df = get_price_history(ticker)
            if hist_df is not None and not hist_df.empty:
                st.markdown(f"**{ticker} — 1 Month Price History**")
                st.line_chart(hist_df, use_container_width=True, height=240)
            else:
                st.info(f"No price history available for {ticker}.")

# ── Footer ─────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    "<div style='font-size:10px;color:#4b5563;text-align:center;padding:8px 0'>"
    "Data: SEC EDGAR (public domain) + Yahoo Finance via yfinance · Not financial advice."
    "</div>",
    unsafe_allow_html=True,
)
