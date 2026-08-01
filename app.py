import datetime
import time
import os
import threading
import logging
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from streamlit_autorefresh import st_autorefresh

# Configure logging for professional error tracking
logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(levelname)s - %(message)s')

# ---------------------------------------------------------
# 1. CONFIGURATION & CONSTANTS
# ---------------------------------------------------------
NIFTY_LOT_SIZE = 25
RISK_FREE_RATE = 0.07
API_TIMEOUT = 10
MAX_RETRIES = 3

# Graceful fallback for dhanhq
try:
    from dhanhq import marketfeed
    DHAN_WS_AVAILABLE = True
except ImportError:
    DHAN_WS_AVAILABLE = False
    logging.warning("dhanhq not installed. WebSocket features will be disabled.")

# ---------------------------------------------------------
# 2. PAGE SETUP & INSTITUTIONAL CSS
# ---------------------------------------------------------
st.set_page_config(
    page_title="Prince PAX | Institutional Volatility Desk",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    /* Base Theme */
    .stApp { background-color: #0B0C10; color: #C5C6C7; font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; }
    section[data-testid="stSidebar"] { background-color: #1F2833 !important; border-right: 1px solid #45A29E; }
    
    /* Metric Cards */
    .metric-card {
        background: #1F2833;
        border: 1px solid #45A29E;
        border-radius: 8px;
        padding: 12px 16px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
        margin-bottom: 12px;
        border-top: 3px solid #66FCF1;
        position: relative;
    }
    .metric-card-green { border-top-color: #00E676; }
    .metric-card-red { border-top-color: #FF5252; }
    .metric-card-amber { border-top-color: #FFD700; }
    .metric-card-purple { border-top-color: #AB47BC; }
    
    .metric-title { color: #8A93A6; font-size: 0.7rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.8px; }
    .metric-value { color: #FFFFFF; font-size: 1.4rem; font-weight: 800; margin-top: 4px; }
    .metric-sub { font-size: 0.75rem; font-weight: 600; margin-top: 4px; }
    
    .sub-green { color: #00E676; } .sub-red { color: #FF5252; } 
    .sub-amber { color: #FFD700; } .sub-blue { color: #29B6F6; } .sub-purple { color: #AB47BC; }

    /* Chart Containers */
    .chart-container {
        background: #1F2833;
        border: 1px solid #45A29E;
        border-radius: 8px;
        padding: 16px;
        margin-bottom: 16px;
    }
    .chart-title {
        font-size: 0.85rem; font-weight: 700; color: #66FCF1;
        text-transform: uppercase; margin-bottom: 12px;
        border-bottom: 1px solid #45A29E; padding-bottom: 6px;
        display: flex; justify-content: space-between; align-items: center;
    }

    /* Tooltips */
    .info-tooltip { position: relative; display: inline-block; cursor: help; color: #8A93A6; font-size: 0.9rem; }
    .info-tooltip .tooltip-text {
        visibility: hidden; width: 280px; background-color: #0B0C10; color: #C5C6C7;
        text-align: left; border-radius: 6px; padding: 12px; position: absolute;
        top: 150%; right: 0; opacity: 0; transition: opacity 0.2s;
        border: 1px solid #45A29E; font-size: 0.75rem; font-weight: 500;
        box-shadow: 0px 6px 20px rgba(0,0,0,0.8); z-index: 9999;
    }
    .info-tooltip:hover .tooltip-text { visibility: visible; opacity: 1; }
    .info-tooltip:hover { color: #66FCF1; }

    /* Status & Tables */
    .status-badge { padding: 6px 12px; border-radius: 4px; font-weight: 700; font-size: 0.75rem; display: inline-block; }
    .status-live { background-color: rgba(0, 230, 118, 0.15); border: 1px solid #00E676; color: #00E676; }
    .status-closed { background-color: rgba(255, 167, 38, 0.15); border: 1px solid #FFA726; color: #FFA726; }
    
    .playbook-table { width: 100%; border-collapse: collapse; font-size: 0.8rem; margin-top: 10px; }
    .playbook-table th { background-color: #0B0C10; color: #66FCF1; text-align: left; padding: 10px; border: 1px solid #45A29E; }
    .playbook-table td { padding: 10px; border: 1px solid #45A29E; color: #C5C6C7; }
    
    /* Tab Styling */
    button[data-baseweb="tab"] { background-color: #1F2833 !important; color: #8A93A6 !important; border-radius: 6px 6px 0 0 !important; }
    button[data-baseweb="tab"][aria-selected="true"] { background-color: #45A29E !important; color: #0B0C10 !important; font-weight: 700 !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

# Clean API Credentials
CLIENT_ID = str(st.secrets.get("DHAN_CLIENT_ID", "")).strip().replace('"', "").replace("'", "")
ACCESS_TOKEN = str(st.secrets.get("DHAN_ACCESS_TOKEN", "")).strip().replace('"', "").replace("'", "")

if not CLIENT_ID or not ACCESS_TOKEN:
    st.error("⚠️ **CRITICAL:** API credentials missing. Please update your Streamlit Secrets (`.streamlit/secrets.toml`).")
    st.stop()

# ---------------------------------------------------------
# 3. ADVANCED VECTORIZED MATH ENGINE (NumPy)
# ---------------------------------------------------------
def norm_cdf(x):
    """Vectorized Cumulative Distribution Function"""
    return 0.5 * (1 + np.erf(x / np.sqrt(2.0)))

def norm_pdf(x):
    """Vectorized Probability Density Function"""
    return np.exp(-0.5 * x**2) / np.sqrt(2 * np.pi)

def calculate_bs_greeks_vectorized(S, K, T, sigma, r=RISK_FREE_RATE):
    """
    Institutional-grade vectorized Black-Scholes Greek calculator.
    Returns: Gamma, Vanna, Charm, Speed, Vomma (Volga), Veta
    """
    T = np.maximum(T, 1e-5)
    sigma = np.maximum(sigma, 1e-4)
    S = np.maximum(S, 1e-5)
    K = np.maximum(K, 1e-5)
    
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    
    pdf_d1 = norm_pdf(d1)
    
    gamma = pdf_d1 / (S * sigma * np.sqrt(T))
    vanna = -pdf_d1 * d2 / sigma
    charm = -pdf_d1 * (2 * r * np.sqrt(T) - d2 * sigma) / (2 * T * sigma)
    speed = -gamma / S * (1 + d1 / (sigma * np.sqrt(T)))
    vomma = gamma * S * np.sqrt(T) * d1 * d2 / sigma
    veta = -S * pdf_d1 * np.sqrt(T) * (r * d2 / (sigma * np.sqrt(T)) + (1 + d1 * d2) / (2 * T))
    
    return gamma, vanna, charm, speed, vomma, veta

def calculate_max_pain_vectorized(strikes, ce_oi, pe_oi):
    """O(N²) vectorized matrix calculation for Max Pain (executes in <1ms)"""
    K = strikes.reshape(-1, 1)  # Column vector
    S = strikes.reshape(1, -1)  # Row vector
    
    ce_loss = ce_oi * np.maximum(K - S, 0)
    pe_loss = pe_oi * np.maximum(S - K, 0)
    
    total_loss = np.sum(ce_loss + pe_loss, axis=1)
    return strikes[np.argmin(total_loss)]

# ---------------------------------------------------------
# 4. RESILIENT DATA ENGINES
# ---------------------------------------------------------
@st.cache_data(ttl=120)
def fetch_expiry_list_direct():
    url = "https://api.dhan.co/v2/optionchain/expirylist"
    headers = {"client-id": CLIENT_ID, "access-token": ACCESS_TOKEN, "Content-Type": "application/json"}
    for _ in range(MAX_RETRIES):
        try:
            res = requests.post(url, headers=headers, json={"UnderlyingScrip": 13, "UnderlyingSeg": "IDX_I"}, timeout=API_TIMEOUT)
            if res.status_code == 200 and res.json().get("status") == "success":
                return res.json().get("data", [])
        except requests.exceptions.RequestException as e:
            logging.warning(f"Expiry fetch failed, retrying... {e}")
            time.sleep(1)
    return []

@st.cache_data(ttl=3)
def fetch_gex_option_chain(expiry_date):
    url = "https://api.dhan.co/v2/optionchain"
    headers = {"client-id": CLIENT_ID, "access-token": ACCESS_TOKEN, "Content-Type": "application/json"}
    payload = {"UnderlyingScrip": 13, "UnderlyingSeg": "IDX_I", "Expiry": expiry_date}

    for _ in range(MAX_RETRIES):
        try:
            res = requests.post(url, headers=headers, json=payload, timeout=API_TIMEOUT)
            data = res.json()
            if res.status_code == 200 and data.get("status") == "success":
                raw_data = data.get("data", {})
                spot_price = float(raw_data.get("last_price", 0.0))
                oc_raw = raw_data.get("oc", {})
                if not oc_raw: return None, spot_price, "No contracts returned."

                T_years = max((datetime.datetime.strptime(expiry_date, "%Y-%m-%d").date() - datetime.date.today()).days, 1) / 365.0
                
                # Vectorized Data Extraction
                strikes = np.array([int(float(k)) for k in oc_raw.keys()])
                ce_oi = np.array([float(oc_raw[k].get("ce", {}).get("oi", 0)) for k in oc_raw.keys()])
                pe_oi = np.array([float(oc_raw[k].get("pe", {}).get("oi", 0)) for k in oc_raw.keys()])
                ce_vol = np.array([float(oc_raw[k].get("ce", {}).get("volume", 0) or 0.0) for k in oc_raw.keys()])
                pe_vol = np.array([float(oc_raw[k].get("pe", {}).get("volume", 0) or 0.0) for k in oc_raw.keys()])
                ce_ltp = np.array([float(oc_raw[k].get("ce", {}).get("last_price", 0)) for k in oc_raw.keys()])
                pe_ltp = np.array([float(oc_raw[k].get("pe", {}).get("last_price", 0)) for k in oc_raw.keys()])
                
                ce_iv = np.array([float(oc_raw[k].get("ce", {}).get("implied_volatility", 0) or 0)/100.0 for k in oc_raw.keys()])
                pe_iv = np.array([float(oc_raw[k].get("pe", {}).get("implied_volatility", 0) or 0)/100.0 for k in oc_raw.keys()])
                
                ce_delta = np.array([float(oc_raw[k].get("ce", {}).get("greeks", {}).get("delta", 0)) for k in oc_raw.keys()])
                pe_delta = np.array([float(oc_raw[k].get("pe", {}).get("greeks", {}).get("delta", 0)) for k in oc_raw.keys()])

                # Vectorized Greek Calculation (Fallback if API gamma is invalid)
                ce_gamma, ce_vanna, ce_charm, ce_speed, ce_vomma, ce_veta = calculate_bs_greeks_vectorized(spot_price, strikes, T_years, np.maximum(ce_iv, 0.15))
                pe_gamma, pe_vanna, pe_charm, pe_speed, pe_vomma, pe_veta = calculate_bs_greeks_vectorized(spot_price, strikes, T_years, np.maximum(pe_iv, 0.15))

                # Vectorized Exposure Calculations
                call_gex = (ce_oi * ce_gamma * (spot_price**2) * 0.01 * NIFTY_LOT_SIZE / 1e5)
                put_gex = (-pe_oi * pe_gamma * (spot_price**2) * 0.01 * NIFTY_LOT_SIZE / 1e5)
                net_gex = call_gex + put_gex
                abs_gex = call_gex + np.abs(put_gex)

                ce_dex = ce_oi * ce_delta * spot_price * NIFTY_LOT_SIZE / 1e5
                pe_dex = pe_oi * pe_delta * spot_price * NIFTY_LOT_SIZE / 1e5
                net_dex = ce_dex + pe_dex
                abs_dex = ce_dex + np.abs(pe_dex)
                net_delta_oi = (ce_oi * ce_delta) + (pe_oi * pe_delta)

                df = pd.DataFrame({
                    "Strike": strikes, "CE_LTP": ce_ltp, "PE_LTP": pe_ltp, 
                    "CE_OI": ce_oi, "PE_OI": pe_oi, "CE_Vol": ce_vol, "PE_Vol": pe_vol,
                    "CE_Delta": ce_delta, "PE_Delta": pe_delta, "Net_Delta_OI": net_delta_oi, 
                    "Net_DEX": net_dex, "ABS_DEX": abs_dex,
                    "Call_GEX": call_gex, "Put_GEX": put_gex, "Net_GEX": net_gex, "ABS_GEX": abs_gex,
                    "Net_VEX": ((ce_oi * ce_vanna) - (pe_oi * pe_vanna)) * NIFTY_LOT_SIZE / 1e3, 
                    "Net_CHEX": ((ce_oi * ce_charm) - (pe_oi * pe_charm)) * NIFTY_LOT_SIZE / 1e3,
                    "Net_SPEX": ((ce_oi * ce_speed) - (pe_oi * pe_speed)) * NIFTY_LOT_SIZE / 1e3,
                    "Net_VOMMA": ((ce_oi * ce_vomma) - (pe_oi * pe_vomma)) * NIFTY_LOT_SIZE / 1e3,
                    "Net_VETA": ((ce_oi * ce_veta) - (pe_oi * pe_veta)) * NIFTY_LOT_SIZE / 1e3,
                    "CE_IV": ce_iv * 100.0, "PE_IV": pe_iv * 100.0, "IV_Spread": (ce_iv - pe_iv) * 100.0,
                })
                return df.sort_values("Strike").reset_index(drop=True), spot_price, None
            else:
                return None, 0.0, str(data.get("remarks") or data.get("message") or f"HTTP {res.status_code}")
        except requests.exceptions.RequestException as e:
            logging.warning(f"Option chain fetch failed, retrying... {e}")
            time.sleep(1)
    return None, 0.0, "Connection Error: Max retries exceeded."

# ---------------------------------------------------------
# 5. WEBSOCKET DAEMON (Graceful & Thread-Safe)
# ---------------------------------------------------------
@st.cache_resource
def start_dhan_websocket(client_id, access_token):
    ws_data = {
        "RELIANCE_LTP": 0.0, "RELIANCE_PREV": 0.0,
        "HDFCBANK_LTP": 0.0, "HDFCBANK_PREV": 0.0,
        "ICICIBANK_LTP": 0.0, "ICICIBANK_PREV": 0.0,
        "NIFTY_FUT_LTP": 0.0, "CVD": 0.0, "CONNECTED": False, "ERROR": None
    }

    if not DHAN_WS_AVAILABLE:
        ws_data["ERROR"] = "dhanhq library not installed"
        return ws_data

    CURRENT_NIFTY_FUT_ID = "58756" 
    instruments = [(1, "2885"), (1, "1333"), (1, "4963"), (2, CURRENT_NIFTY_FUT_ID)]
    sub_code = getattr(marketfeed, 'Ticker', 15)

    def on_connect(instance): ws_data["CONNECTED"] = True
    def on_disconnect(instance): ws_data["CONNECTED"] = False

    def on_message(instance, message):
        if isinstance(message, dict):
            sec_id = str(message.get('security_id', ''))
            ltp = float(message.get('LTP', 0.0))
            ltq = float(message.get('last_trade_quantity', 0.0))
            
            if ltp > 0:
                if sec_id == CURRENT_NIFTY_FUT_ID: 
                    ws_data["NIFTY_FUT_LTP"] = ltp
                elif sec_id in ["2885", "1333", "4963"]:
                    symbol = "RELIANCE" if sec_id == "2885" else "HDFCBANK" if sec_id == "1333" else "ICICIBANK"
                    prev_ltp = ws_data[f"{symbol}_PREV"]
                    if prev_ltp > 0:
                        if ltp > prev_ltp: ws_data["CVD"] += ltq
                        elif ltp < prev_ltp: ws_data["CVD"] -= ltq
                    ws_data[f"{symbol}_LTP"] = ltp
                    ws_data[f"{symbol}_PREV"] = ltp

    def run_ws():
        try:
            feed = marketfeed.DhanFeed(client_id, access_token, instruments, sub_code, on_connect=on_connect, on_message=on_message)
            feed.run_forever()
        except Exception as e:
            ws_data["ERROR"] = str(e)
            ws_data["CONNECTED"] = False

    t = threading.Thread(target=run_ws, daemon=True)
    t.start()
    return ws_data

live_ws_data = start_dhan_websocket(CLIENT_ID, ACCESS_TOKEN)

# ---------------------------------------------------------
# 6. STATE MANAGEMENT & CONTROLS
# ---------------------------------------------------------
st.sidebar.header("⚙️ Command Center")
auto_refresh = st.sidebar.checkbox("Live Auto-Refresh (5s)", value=True)
if auto_refresh: st_autorefresh(interval=5000, key="datarefresh")

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
now_ist = datetime.datetime.now(IST)
today_date_str = now_ist.strftime("%Y-%m-%d")
now_time_str = now_ist.strftime("%H:%M:%S")

is_weekday = now_ist.weekday() < 5
m_open = now_ist.replace(hour=9, minute=15, second=0, microsecond=0)
m_close = now_ist.replace(hour=15, minute=30, second=0, microsecond=0)
is_market_live = is_weekday and (m_open <= now_ist <= m_close)

valid_expiries = fetch_expiry_list_direct()
if valid_expiries: 
    selected_expiry = st.sidebar.selectbox("Primary Expiry", valid_expiries)
else:
    days_until_thursday = (3 - now_ist.weekday()) % 7
    default_expiry = (now_ist + datetime.timedelta(days=days_until_thursday)).strftime("%Y-%m-%d")
    selected_expiry = st.sidebar.date_input("Primary Expiry", datetime.datetime.strptime(default_expiry, "%Y-%m-%d")).strftime("%Y-%m-%d")

with st.spinner("Fetching institutional option chain data..."):
    df_oc, spot_price, error_remark = fetch_gex_option_chain(selected_expiry)

if error_remark:
    st.error(f"⚠️ **Dhan Server Error:** {error_remark}")
    st.stop()

# Synthetic Future & ATM Calculation
synthetic_future = spot_price
if df_oc is not None and not df_oc.empty:
    spot_atm = int(round(spot_price / 50) * 50)
    spot_row = df_oc[df_oc["Strike"] == spot_atm]
    if not spot_row.empty: 
        synthetic_future = spot_atm + spot_row["CE_LTP"].values[0] - spot_row["PE
