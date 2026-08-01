import datetime
import time
import os
import threading
import logging
import math
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
NIFTY_LOT_SIZE = 60
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
# 4. LOCAL PARQUET PERSISTENCE
# ---------------------------------------------------------
def get_persisted_df(name, cols):
    path = f"{name}.parquet"
    if os.path.exists(path):
        try:
            df = pd.read_parquet(path)
            if set(cols).issubset(df.columns): return df
        except Exception: pass
    return pd.DataFrame(columns=cols)

def save_persisted_df(df, name):
    try: df.to_parquet(f"{name}.parquet", engine="pyarrow")
    except Exception: pass

def check_and_reset(df_name, cols, today_date_str, now_time_str):
    df = get_persisted_df(df_name, cols)
    if not df.empty:
        last_date = df.iloc[-1]["Date"]
        if last_date != today_date_str and now_time_str >= "09:15:00":
            df = pd.DataFrame(columns=cols)
            save_persisted_df(df, df_name)
    return df

# ---------------------------------------------------------
# 5. RESILIENT DATA ENGINES
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
                ce_oi = np.array([float(oc_raw[k].get("ce", {}).get("oi", 0) or 0) for k in oc_raw.keys()])
                pe_oi = np.array([float(oc_raw[k].get("pe", {}).get("oi", 0) or 0) for k in oc_raw.keys()])
                ce_vol = np.array([float(oc_raw[k].get("ce", {}).get("volume", 0) or 0.0) for k in oc_raw.keys()])
                pe_vol = np.array([float(oc_raw[k].get("pe", {}).get("volume", 0) or 0.0) for k in oc_raw.keys()])
                ce_ltp = np.array([float(oc_raw[k].get("ce", {}).get("last_price", 0) or 0) for k in oc_raw.keys()])
                pe_ltp = np.array([float(oc_raw[k].get("pe", {}).get("last_price", 0) or 0) for k in oc_raw.keys()])
                
                ce_iv = np.array([float(oc_raw[k].get("ce", {}).get("implied_volatility", 0) or 0)/100.0 for k in oc_raw.keys()])
                pe_iv = np.array([float(oc_raw[k].get("pe", {}).get("implied_volatility", 0) or 0)/100.0 for k in oc_raw.keys()])
                
                ce_delta = np.array([float(oc_raw[k].get("ce", {}).get("greeks", {}).get("delta", 0) or 0) for k in oc_raw.keys()])
                pe_delta = np.array([float(oc_raw[k].get("pe", {}).get("greeks", {}).get("delta", 0) or 0) for k in oc_raw.keys()])
                ce_gamma_api = np.array([float(oc_raw[k].get("ce", {}).get("greeks", {}).get("gamma", 0) or 0) for k in oc_raw.keys()])
                pe_gamma_api = np.array([float(oc_raw[k].get("pe", {}).get("greeks", {}).get("gamma", 0) or 0) for k in oc_raw.keys()])

                # Vectorized Greek Calculation (Fallback if API gamma is invalid)
                ce_gamma_bs, ce_vanna, ce_charm, ce_speed, ce_vomma, ce_veta = calculate_bs_greeks_vectorized(
                    spot_price, strikes, T_years, np.maximum(ce_iv, 0.15)
                )
                pe_gamma_bs, pe_vanna, pe_charm, pe_speed, pe_vomma, pe_veta = calculate_bs_greeks_vectorized(
                    spot_price, strikes, T_years, np.maximum(pe_iv, 0.15)
                )
                
                # Use API gamma if valid, else fallback to BS
                ce_gamma = np.where(ce_gamma_api > 0, ce_gamma_api, ce_gamma_bs)
                pe_gamma = np.where(pe_gamma_api > 0, pe_gamma_api, pe_gamma_bs)

                # Vectorized Exposure Calculations (OpenBull Model Standard)
                # GEX = gamma * open_interest * lot_size
                # Net GEX = CE GEX - PE GEX
                ce_gex = ce_gamma * ce_oi * NIFTY_LOT_SIZE
                pe_gex = pe_gamma * pe_oi * NIFTY_LOT_SIZE
                net_gex = ce_gex - pe_gex
                abs_gex = ce_gex + pe_gex

                # DEX remains dollarized for institutional rupee-value context
                ce_dex = ce_oi * ce_delta * spot_price * NIFTY_LOT_SIZE / 1e5
                pe_dex = pe_oi * pe_delta * spot_price * NIFTY_LOT_SIZE / 1e5
                net_dex = ce_dex + pe_dex
                abs_dex = np.abs(ce_dex) + np.abs(pe_dex)
                net_delta_oi = (ce_oi * ce_delta) + (pe_oi * pe_delta)

                df = pd.DataFrame({
                    "Strike": strikes, "CE_LTP": ce_ltp, "PE_LTP": pe_ltp, 
                    "CE_OI": ce_oi, "PE_OI": pe_oi, "CE_Vol": ce_vol, "PE_Vol": pe_vol,
                    "CE_Delta": ce_delta, "PE_Delta": pe_delta, "Net_Delta_OI": net_delta_oi, 
                    "Net_DEX": net_dex, "ABS_DEX": abs_dex,
                    "CE_GEX": ce_gex, "PE_GEX": pe_gex, "Net_GEX": net_gex, "ABS_GEX": abs_gex,
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
# 6. MULTI-EXPIRY TERM STRUCTURE ENGINE
# ---------------------------------------------------------
@st.cache_data(ttl=120)
def fetch_multi_expiry_vol_structure(spot_price):
    expiries = fetch_expiry_list_direct()
    if not expiries:
        today = datetime.date.today()
        expiries = [(today + datetime.timedelta(days=i)).strftime("%Y-%m-%d") for i in range(1, 45) if (today + datetime.timedelta(days=i)).weekday() == 3][:4]
    else: 
        expiries = expiries[:4]

    vol_data = []

    for idx, exp in enumerate(expiries):
        if idx > 0: time.sleep(1.2)
        df_exp, exp_spot, _ = fetch_gex_option_chain(exp)
        if df_exp is not None and not df_exp.empty:
            temp_spot_atm = int(round(exp_spot / 50) * 50)
            temp_row = df_exp[df_exp["Strike"] == temp_spot_atm]
            if not temp_row.empty: exp_synth = temp_spot_atm + temp_row["CE_LTP"].values[0] - temp_row["PE_LTP"].values[0]
            else: exp_synth = exp_spot
            exp_atm_strike = int(round(exp_synth / 50) * 50)
            
            atm_row = df_exp[df_exp["Strike"] == exp_atm_strike]
            ce_iv = atm_row["CE_IV"].values[0] if not atm_row.empty else df_exp["CE_IV"].mean()
            pe_iv = atm_row["PE_IV"].values[0] if not atm_row.empty else df_exp["PE_IV"].mean()
            mean_iv = (ce_iv + pe_iv) / 2.0
            days_to_exp = max((datetime.datetime.strptime(exp, "%Y-%m-%d").date() - datetime.date.today()).days, 1)

            vol_data.append({"Expiry": datetime.datetime.strptime(exp, "%Y-%m-%d").strftime("%d %b"), "Days": days_to_exp, "Tenor_Years": days_to_exp / 365.0, "Mean_IV": mean_iv})

    df_vol = pd.DataFrame(vol_data)
    if df_vol.empty or len(df_vol) < 2: return pd.DataFrame()

    fwd_vols = []
    for i in range(len(df_vol)):
        if i == 0: fwd_vols.append(df_vol.loc[i, "Mean_IV"])
        else:
            t1, t2 = df_vol.loc[i - 1, "Tenor_Years"], df_vol.loc[i, "Tenor_Years"]
            v1, v2 = df_vol.loc[i - 1, "Mean_IV"] / 100.0, df_vol.loc[i, "Mean_IV"] / 100.0
            var_diff, dt = (v2**2 * t2) - (v1**2 * t1), t2 - t1
            fwd_vols.append(math.sqrt(var_diff / dt) * 100.0 if (var_diff > 0 and dt > 0) else v2 * 100.0)

    df_vol["Forward_Vol"] = fwd_vols
    return df_vol

# ---------------------------------------------------------
# 7. WEBSOCKET DAEMON (Graceful & Thread-Safe)
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
# 8. STATE MANAGEMENT & CONTROLS
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
        synthetic_future = spot_atm + spot_row["CE_LTP"].values[0] - spot_row["PE_LTP"].values[0]
atm_strike = int(round(synthetic_future / 50) * 50)

all_strikes = df_oc["Strike"].tolist()
default_index = all_strikes.index(atm_strike) if atm_strike in all_strikes else len(all_strikes)//2
selected_target_strike = st.sidebar.selectbox("🎯 Target Strike Analysis", all_strikes, index=default_index)

# Data Memory Definitions (Parquet Backed)
REQUIRED_HIST_COLS = ["Date", "Time", "Strike", "CE_IV", "PE_IV", "IV_Spread", "Spot"]
REQUIRED_PCR_COLS = ["Date", "Timestamp_dt", "Time", "PCR", "Vol_PCR", "Delta_PCR_5m", "Delta_PCR_15m", "Total_CE_OI", "Total_PE_OI"]
REQUIRED_GEX_COLS = ["Date", "Timestamp_dt", "Time", "Total_Net_GEX", "Z_GEX", "Flip_Strike", "Spot"]
REQUIRED_SYNTH_COLS = ["Date", "Time", "Spot", "Strike_M50", "Strike_ATM", "Strike_P50", "Synth_M50", "Synth_ATM", "Synth_P50", "PCP_Dev_Mean"]
REQUIRED_DELTA_COLS = ["Date", "Timestamp_dt", "Time", "Total_Net_Delta_OI", "Delta_OI_ROC_1m", "Total_Net_DEX", "DEX_Vel_5m"]
REQUIRED_STRADDLE_COLS = ["Date", "Time", "Elapsed_Mins", "Actual_Straddle", "Expected_Straddle", "Regime"]

if "iv_spread_history" not in st.session_state: st.session_state["iv_spread_history"] = check_and_reset("iv_spread_history", REQUIRED_HIST_COLS, today_date_str, now_time_str)
if "pcr_history" not in st.session_state: st.session_state["pcr_history"] = check_and_reset("pcr_history", REQUIRED_PCR_COLS, today_date_str, now_time_str)
if "gex_history" not in st.session_state: st.session_state["gex_history"] = check_and_reset("gex_history", REQUIRED_GEX_COLS, today_date_str, now_time_str)
if "synth_history" not in st.session_state: st.session_state["synth_history"] = check_and_reset("synth_history", REQUIRED_SYNTH_COLS, today_date_str, now_time_str)
if "delta_oi_history" not in st.session_state: st.session_state["delta_oi_history"] = check_and_reset("delta_oi_history", REQUIRED_DELTA_COLS, today_date_str, now_time_str)
if "straddle_history" not in st.session_state: st.session_state["straddle_history"] = check_and_reset("straddle_history", REQUIRED_STRADDLE_COLS, today_date_str, now_time_str)
if "straddle_anchor_price" not in st.session_state: st.session_state["straddle_anchor_price"] = None

if st.sidebar.button("🗑️ Reset Session Cache"):
    st.session_state["iv_spread_history"] = pd.DataFrame(columns=REQUIRED_HIST_COLS)
    st.session_state["pcr_history"] = pd.DataFrame(columns=REQUIRED_PCR_COLS)
    st.session_state["gex_history"] = pd.DataFrame(columns=REQUIRED_GEX_COLS)
    st.session_state["synth_history"] = pd.DataFrame(columns=REQUIRED_SYNTH_COLS)
    st.session_state["delta_oi_history"] = pd.DataFrame(columns=REQUIRED_DELTA_COLS)
    st.session_state["straddle_history"] = pd.DataFrame(columns=REQUIRED_STRADDLE_COLS)
    st.session_state["straddle_anchor_price"] = None
    st.cache_data.clear()
    st.rerun()

# ---------------------------------------------------------
# 9. CORE ANALYTICS PROCESSING
# ---------------------------------------------------------
# Cumulative Gamma Flip
df_sorted = df_oc.sort_values("Strike").copy()
df_sorted["Cum_Net_GEX"] = df_sorted["Net_GEX"].cumsum()
gamma_flip_strike = int(spot_price)
for i in range(1, len(df_sorted)):
    prev_val, curr_val = df_sorted.iloc[i - 1]["Cum_Net_GEX"], df_sorted.iloc[i]["Cum_Net_GEX"]
    if (prev_val < 0 and curr_val >= 0) or (prev_val > 0 and curr_val <= 0):
        gamma_flip_strike = int((df_sorted.iloc[i - 1]["Strike"] + df_sorted.iloc[i]["Strike"]) / 2.0)
        break

# Max Pain (Vectorized)
max_pain_strike = calculate_max_pain_vectorized(
    df_oc["Strike"].values, df_oc["CE_OI"].values, df_oc["PE_OI"].values
)

# Target Metrics
target_row = df_oc[df_oc["Strike"] == selected_target_strike]
target_ce_iv = target_row["CE_IV"].values[0] if not target_row.empty else 0.0
target_pe_iv = target_row["PE_IV"].values[0] if not target_row.empty else 0.0
target_iv_spread = target_ce_iv - target_pe_iv

# Filtered Range for Charts (ATM ± 550)
df_filtered = df_oc[(df_oc["Strike"] >= atm_strike - 550) & (df_oc["Strike"] <= atm_strike + 550)].copy()
strike_labels = df_filtered["Strike"].astype(str).tolist()

# Aggregate Metrics
total_net_gex = df_oc["Net_GEX"].sum()
total_net_delta_oi = df_oc["Net_Delta_OI"].sum()
total_net_dex_crores = df_oc["Net_DEX"].sum() / 100.0
total_call_oi, total_put_oi = df_oc["CE_OI"].sum(), df_oc["PE_OI"].sum()
current_pcr = total_put_oi / total_call_oi if total_call_oi > 0 else 0.0

# Institutional Walls
call_wall_gex = df_filtered.loc[df_filtered['Net_GEX'].idxmax()]['Strike'] if not df_filtered.empty else atm_strike
put_wall_gex = df_filtered.loc[df_filtered['Net_GEX'].idxmin()]['Strike'] if not df_filtered.empty else atm_strike
call_wall_dex = df_filtered.loc[df_filtered['Net_DEX'].idxmax()]['Strike'] if not df_filtered.empty else atm_strike
put_wall_dex = df_filtered.loc[df_filtered['Net_DEX'].idxmin()]['Strike'] if not df_filtered.empty else atm_strike

# ---------------------------------------------------------
# 10. INTRADAY MEMORY RECORDING
# ---------------------------------------------------------
if is_market_live:
    for hist_key in ["iv_spread_history", "pcr_history", "gex_history", "synth_history", "delta_oi_history", "straddle_history"]:
        h_df = st.session_state[hist_key]
        if not h_df.empty and h_df.iloc[-1].get("Date") != today_date_str:
            st.session_state[hist_key] = h_df.iloc[0:0]
            if hist_key == "straddle_history": st.session_state["straddle_anchor_price"] = None

    # 1. IV Spread Memory
    hist_df = st.session_state["iv_spread_history"]
    if hist_df.empty or hist_df.iloc[-1]["Time"] != now_time_str:
        new_ticks = [{"Date": today_date_str, "Time": now_time_str, "Strike": int(r["Strike"]), "CE_IV": float(r["CE_IV"]), "PE_IV": float(r["PE_IV"]), "IV_Spread": float(r["IV_Spread"]), "Spot": spot_price} for _, r in df_filtered.iterrows()]
        st.session_state["iv_spread_history"] = pd.concat([hist_df, pd.DataFrame(new_ticks)], ignore_index=True)
        save_persisted_df(st.session_state["iv_spread_history"], "iv_spread_history")

    # 2. PCR Velocity Memory
    total_call_vol = df_oc["CE_Vol"].sum() if "CE_Vol" in df_oc.columns else 0.0
    total_put_vol = df_oc["PE_Vol"].sum() if "PE_Vol" in df_oc.columns else 0.0
    vol_pcr = total_put_vol / total_call_vol if total_call_vol > 0 else 0.0
    
    pcr_df = st.session_state["pcr_history"]
    delta_pcr_15m = 0.0
    if pcr_df.empty or pcr_df.iloc[-1]["Time"] != now_time_str:
        if not pcr_df.empty:
            past_15m = pcr_df[pcr_df["Timestamp_dt"] <= (now_ist - datetime.timedelta(minutes=15))]
            if not past_15m.empty: delta_pcr_15m = current_pcr - past_15m.iloc[-1]["PCR"]
        
        st.session_state["pcr_history"] = pd.concat([pcr_df, pd.DataFrame([{
            "Date": today_date_str, "Timestamp_dt": now_ist, "Time": now_time_str, 
            "PCR": current_pcr, "Vol_PCR": vol_pcr, 
            "Delta_PCR_5m": 0.0, "Delta_PCR_15m": delta_pcr_15m,
            "Total_CE_OI": total_call_oi, "Total_PE_OI": total_put_oi
        }])], ignore_index=True)
        save_persisted_df(st.session_state["pcr_history"], "pcr_history")

    # 3. Z-GEX Memory & Gamma Flip Migration
    gex_df = st.session_state["gex_history"]
    current_z_gex = 0.0
    if gex_df.empty or gex_df.iloc[-1]["Time"] != now_time_str:
        if len(gex_df) >= 2:
            mu, sigma = gex_df["Total_Net_GEX"].tail(20).mean(), gex_df["Total_Net_GEX"].tail(20).std()
            if sigma > 0: current_z_gex = (total_net_gex - mu) / sigma
        st.session_state["gex_history"] = pd.concat([gex_df, pd.DataFrame([{"Date": today_date_str, "Timestamp_dt": now_ist, "Time": now_time_str, "Total_Net_GEX": total_net_gex, "Z_GEX": current_z_gex, "Flip_Strike": gamma_flip_strike, "Spot": spot_price}])], ignore_index=True)
        save_persisted_df(st.session_state["gex_history"], "gex_history")

    # 4. Multi-Strike Synthetic Parity
    strike_m50, strike_p50 = atm_strike - 50, atm_strike + 50
    synth_df = st.session_state["synth_history"]
    row_m50, row_atm, row_p50 = df_oc[df_oc["Strike"] == strike_m50], df_oc[df_oc["Strike"] == atm_strike], df_oc[df_oc["Strike"] == strike_p50]
    s_m50 = strike_m50 + row_m50["CE_LTP"].values[0] - row_m50["PE_LTP"].values[0] if not row_m50.empty else spot_price
    s_atm = atm_strike + row_atm["CE_LTP"].values[0] - row_atm["PE_LTP"].values[0] if not row_atm.empty else spot_price
    s_p50 = strike_p50 + row_p50["CE_LTP"].values[0] - row_p50["PE_LTP"].values[0] if not row_p50.empty else spot_price
    pcp_dev_mean = ((s_m50 - spot_price) + (s_atm - spot_price) + (s_p50 - spot_price)) / 3.0
    
    if synth_df.empty or synth_df.iloc[-1]["Time"] != now_time_str:
        st.session_state["synth_history"] = pd.concat([synth_df, pd.DataFrame([{"Date": today_date_str, "Time": now_time_str, "Spot": spot_price, "Strike_M50": strike_m50, "Strike_ATM": atm_strike, "Strike_P50": strike_p50, "Synth_M50": s_m50, "Synth_ATM": s_atm, "Synth_P50": s_p50, "PCP_Dev_Mean": pcp_dev_mean}])], ignore_index=True)
        save_persisted_df(st.session_state["synth_history"], "synth_history")

    # 5. Real-Time Net Delta OI ROC
    doi_df = st.session_state["delta_oi_history"]
    doi_roc_1m, dex_vel_5m = 0.0, 0.0
    if doi_df.empty or doi_df.iloc[-1]["Time"] != now_time_str:
        if not doi_df.empty:
            past_1m = doi_df[doi_df["Timestamp_dt"] <= (now_ist - datetime.timedelta(minutes=1))]
            if not past_1m.empty: doi_roc_1m = total_net_delta_oi - past_1m.iloc[-1]["Total_Net_Delta_OI"]
            past_5m = doi_df[doi_df["Timestamp_dt"] <= (now_ist - datetime.timedelta(minutes=5))]
            if not past_5m.empty: dex_vel_5m = total_net_dex_crores - past_5m.iloc[-1]["Total_Net_DEX"]
        st.session_state["delta_oi_history"] = pd.concat([doi_df, pd.DataFrame([{"Date": today_date_str, "Timestamp_dt": now_ist, "Time": now_time_str, "Total_Net_Delta_OI": total_net_delta_oi, "Delta_OI_ROC_1m": doi_roc_1m, "Total_Net_DEX": total_net_dex_crores, "DEX_Vel_5m": dex_vel_5m}])], ignore_index=True)
        save_persisted_df(st.session_state["delta_oi_history"], "delta_oi_history")

    # 6. Anchored ATM Straddle Decay Engine
    strad_df = st.session_state["straddle_history"]
    row_atm_cur = df_oc[df_oc["Strike"] == atm_strike]
    current_straddle = (row_atm_cur["CE_LTP"].values[0] if not row_atm_cur.empty else 0.0) + (row_atm_cur["PE_LTP"].values[0] if not row_atm_cur.empty else 0.0)
    elapsed_mins = max(0, min((now_ist - m_open).total_seconds() / 60.0, 375)) 
    
    if elapsed_mins >= 5.0 and st.session_state["straddle_anchor_price"] is None:
        st.session_state["straddle_anchor_price"] = current_straddle
        
    anchor = st.session_state["straddle_anchor_price"] if st.session_state["straddle_anchor_price"] else current_straddle
    expected_straddle = anchor * (1 - (0.15 * math.sqrt(elapsed_mins / 375)))
    strad_regime = "VOL COIL 🟢" if current_straddle > expected_straddle + 2.0 else ("IV CRUSH 🔴" if current_straddle < expected_straddle - 2.0 else "NORMAL DECAY")

    if strad_df.empty or strad_df.iloc[-1]["Time"] != now_time_str:
        st.session_state["straddle_history"] = pd.concat([strad_df, pd.DataFrame([{"Date": today_date_str, "Time": now_time_str, "Elapsed_Mins": elapsed_mins, "Actual_Straddle": current_straddle, "Expected_Straddle": expected_straddle, "Regime": strad_regime}])], ignore_index=True)
        save_persisted_df(st.session_state["straddle_history"], "straddle_history")

# Read latest values for UI display
pcr_df = st.session_state["pcr_history"]
gex_df = st.session_state["gex_history"]
synth_df = st.session_state["synth_history"]
doi_df = st.session_state["delta_oi_history"]
strad_df = st.session_state["straddle_history"]

current_z_gex = gex_df.iloc[-1]["Z_GEX"] if not gex_df.empty else 0.0
delta_pcr_15m = pcr_df.iloc[-1]["Delta_PCR_15m"] if not pcr_df.empty else 0.0
doi_roc_1m = doi_df.iloc[-1]["Delta_OI_ROC_1m"] if not doi_df.empty else 0.0
current_straddle = strad_df.iloc[-1]["Actual_Straddle"] if not strad_df.empty else 0.0
strad_regime = strad_df.iloc[-1]["Regime"] if not strad_df.empty else "NORMAL DECAY"

# Regime Logic
if current_z_gex < -2.0: z_signal, z_color, z_card_border = "GAMMA COLLAPSE", "sub-red", "metric-card-red"
elif -1.0 <= current_z_gex <= 1.0: z_signal, z_color, z_card_border = "NORMAL DAMPENING", "sub-green", "metric-card-green"
else: z_signal, z_color, z_card_border = "TRANSITION ZONE", "sub-amber", "metric-card-amber"

if total_net_delta_oi > 50000: dir_signal, dir_color = "STRONGLY BULLISH", "sub-green"
elif total_net_delta_oi > 10000: dir_signal, dir_color = "MILDLY BULLISH", "sub-green"
elif total_net_delta_oi < -50000: dir_signal, dir_color = "STRONGLY BEARISH", "sub-red"
elif total_net_delta_oi < -10000: dir_signal, dir_color = "MILDLY BEARISH", "sub-red"
else: dir_signal, dir_color = "NEUTRAL / RANGEBOUND", "sub-amber"

# ---------------------------------------------------------
# 11. PROFESSIONAL TABBED UI RENDERING
# ---------------------------------------------------------
st.markdown(f"### 🏛️ PRINCE PAX | INSTITUTIONAL VOLATILITY DESK")
status_class = "status-live" if is_market_live else "status-closed"
status_text = "🟢 LIVE MARKET" if is_market_live else "🟠 MARKET CLOSED (Last Session)"
st.markdown(f'<div class="status-badge {status_class}">{status_text} | Expiry: {selected_expiry} | IST: {now_time_str}</div>', unsafe_allow_html=True)
st.markdown("<br>", unsafe_allow_html=True)

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Command Center", 
    "🧱 Dealer Exposure (GEX/DEX)", 
    "🌊 Order Flow & Momentum", 
    "📈 Volatility & Term Structure",
    "📋 Data Grid & Playbook"
])

# ================= TAB 1: COMMAND CENTER =================
with tab1:
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    
    with m1:
        st.markdown(f"""
            <div class="metric-card metric-card-amber">
                <div class="info-tooltip">ⓘ<span class="tooltip-text">Synthetic Future (K + C - P). All analytics dynamically center on this True Forward Price. Max Pain indicates institutional strike magnet.</span></div>
                <div class="metric-title">NIFTY SYNTH FUT</div>
                <div class="metric-value">₹{synthetic_future:,.2f}</div>
                <div class="metric-sub sub-amber">Spot: ₹{spot_price:,.2f} | Pain: {max_pain_strike}</div>
            </div>
        """, unsafe_allow_html=True)

    with m2:
        spread_class = "sub-green" if target_iv_spread >= 0 else "sub-red"
        border_class = "metric-card-green" if target_iv_spread >= 0 else "metric-card-red"
        st.markdown(f"""
            <div class="metric-card {border_class}">
                <div class="info-tooltip">ⓘ<span class="tooltip-text"><b>IV Spread = Call IV - Put IV.</b><br>Rising values indicate institutional stealth accumulation of Calls.</span></div>
                <div class="metric-title">{selected_target_strike} IV SPREAD</div>
                <div class="metric-value">{target_iv_spread:+.2f}%</div>
                <div class="metric-sub {spread_class}">CE {target_ce_iv:.1f}% | PE {target_pe_iv:.1f}%</div>
            </div>
        """, unsafe_allow_html=True)

    with m3:
        pcr_color = "sub-green" if delta_pcr_15m >= 0.15 else ("sub-red" if delta_pcr_15m <= -0.15 else "sub-amber")
        p_border = "metric-card-green" if delta_pcr_15m >= 0.15 else ("metric-card-red" if delta_pcr_15m <= -0.15 else "metric-card-amber")
        st.markdown(f"""
            <div class="metric-card {p_border}">
                <div class="info-tooltip">ⓘ<span class="tooltip-text"><b>Rate of Change of PCR (15m window).</b><br>> +0.15 = Aggressive Put Writing (Bullish).<br>< -0.15 = Aggressive Call Writing (Bearish).</span></div>
                <div class="metric-title">ΔPCR 15M VELOCITY</div>
                <div class="metric-value">{delta_pcr_15m:+.2f}</div>
                <div class="metric-sub {pcr_color}">PCR: {current_pcr:.2f}</div>
            </div>
        """, unsafe_allow_html=True)

    with m4:
        doi_color = "sub-green" if doi_roc_1m >= 0 else "sub-red"
        st.markdown(f"""
            <div class="metric-card {'metric-card-green' if total_net_delta_oi >= 0 else 'metric-card-red'}">
                <div class="info-tooltip">ⓘ<span class="tooltip-text"><b>Net Delta Exposure.</b><br>A sharp drop signals short-covering panic by Call writers.</span></div>
                <div class="metric-title">NET DELTA OI</div>
                <div class="metric-value">{total_net_delta_oi:+,.0f}</div>
                <div class="metric-sub {doi_color}">1m ROC: {doi_roc_1m:+,.0f} | {dir_signal}</div>
            </div>
        """, unsafe_allow_html=True)

    with m5:
        st.markdown(f"""
            <div class="metric-card {'metric-card-green' if strad_regime == 'VOL COIL 🟢' else 'metric-card-amber'}">
                <div class="info-tooltip">ⓘ<span class="tooltip-text"><b>ATM Straddle Premium Decay.</b><br>If premium stays flat/rises while Spot sits still, IV is coiling for a breakout.</span></div>
                <div class="metric-title">STRADDLE DECAY</div>
                <div class="metric-value">₹{current_straddle:.1f}</div>
                <div class="metric-sub {'sub-green' if strad_regime == 'VOL COIL 🟢' else 'sub-amber'}">{strad_regime}</div>
            </div>
        """, unsafe_allow_html=True)

    with m6:
        st.markdown(f"""
            <div class="metric-card {z_card_border}">
                <div class="info-tooltip">ⓘ<span class="tooltip-text"><b>Statistical Gamma Regime.</b><br>Z-GEX < -2.0 means dealer stabilizing power has mathematically collapsed. Prime regime for multi-strike squeezes.</span></div>
                <div class="metric-title">Z-GEX SCORE</div>
                <div class="metric-value">{current_z_gex:+.2f}</div>
                <div class="metric-sub {z_color}">{z_signal}</div>
            </div>
        """, unsafe_allow_html=True)

# ================= TAB 2: DEALER EXPOSURE =================
with tab2:
    c1, c2 = st.columns(2)
    
    with c1:
        st.markdown('<div class="chart-container"><div class="chart-title">Net Gamma Exposure (GEX) By Strike <div class="info-tooltip">ⓘ<span class="tooltip-text">OpenBull Model: GEX = Gamma × OI × LotSize. Red = Call Walls (Resistance). Green = Put Walls (Support). Blue dashed = Gamma Flip.</span></div></div>', unsafe_allow_html=True)
        fig_gex = go.Figure()
        colors_gex = ["#00E676" if g >= 0 else "#FF5252" for g in df_filtered["Net_GEX"]]
        fig_gex.add_trace(go.Bar(x=df_filtered["Strike"], y=df_filtered["Net_GEX"], marker_color=colors_gex, name="Net GEX", opacity=0.8, hovertemplate="Strike: %{x}<br>Net GEX: %{y:,.0f}<extra></extra>"))
        fig_gex.add_trace(go.Scatter(x=df_filtered["Strike"], y=df_filtered["ABS_GEX"], mode="lines", name="Absolute GEX", line=dict(color="#29B6F6", width=2, shape="spline")))
        
        fig_gex.add_vline(x=spot_price, line_dash="solid", line_color="#FFD700", line_width=1, annotation_text="Spot", annotation_position="top right")
        fig_gex.add_vline(x=gamma_flip_strike, line_dash="dash", line_color="#29B6F6", line_width=1, annotation_text="Flip", annotation_position="bottom right")
        
        fig_gex.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=10, b=0), height=350, xaxis=dict(tickmode='array', tickvals=df_filtered["Strike"], ticktext=strike_labels, tickangle=-45))
        st.plotly_chart(fig_gex, use_container_width=True, key="chart_gex_profile")
        st.markdown('</div>', unsafe_allow_html=True)

    with c2:
        st.markdown('<div class="chart-container"><div class="chart-title">Net Delta Exposure (DEX) By Strike <div class="info-tooltip">ⓘ<span class="tooltip-text">Total Rupee Value of Delta per strike. Visualizes where directional bias is heavily concentrated.</span></div></div>', unsafe_allow_html=True)
        fig_dex = go.Figure()
        colors_dex = ["#00E676" if val >= 0 else "#FF5252" for val in df_filtered["Net_DEX"]]
        fig_dex.add_trace(go.Bar(x=df_filtered["Strike"], y=df_filtered["Net_DEX"], marker_color=colors_dex, name="Net DEX", opacity=0.8, hovertemplate="Strike: %{x}<br>DEX: %{y:,.1f}L<extra></extra>"))
        fig_dex.add_trace(go.Scatter(x=df_filtered["Strike"], y=df_filtered["ABS_DEX"], mode="lines", name="Absolute DEX", line=dict(color="#FFA726", width=2, shape="spline")))
        
        fig_dex.add_vline(x=spot_price, line_dash="solid", line_color="#FFD700", line_width=1)
        fig_dex.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=10, b=0), height=350, xaxis=dict(tickmode='array', tickvals=df_filtered["Strike"], ticktext=strike_labels, tickangle=-45))
        st.plotly_chart(fig_dex, use_container_width=True, key="chart_dex")
        st.markdown('</div>', unsafe_allow_html=True)

    c3, c4 = st.columns(2)
    with c3:
        st.markdown('<div class="chart-container"><div class="chart-title">CE vs PE GEX Comparison (OpenBull Model)</div>', unsafe_allow_html=True)
        fig_gex_compare = go.Figure()
        fig_gex_compare.add_trace(go.Bar(x=df_filtered["Strike"], y=df_filtered["CE_GEX"], name="CE GEX", marker_color="#00E676", opacity=0.7))
        fig_gex_compare.add_trace(go.Bar(x=df_filtered["Strike"], y=-df_filtered["PE_GEX"], name="PE GEX", marker_color="#FF5252", opacity=0.7))
        fig_gex_compare.add_hline(y=0, line_dash="solid", line_color="white", opacity=0.3)
        fig_gex_compare.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=10, b=0), height=280, barmode='overlay', xaxis=dict(tickmode='array', tickvals=df_filtered["Strike"], ticktext=strike_labels, tickangle=-45))
        st.plotly_chart(fig_gex_compare, use_container_width=True, key="chart_gex_compare")
        st.markdown('</div>', unsafe_allow_html=True)
        
    with c4:
        st.markdown('<div class="chart-container"><div class="chart-title">Vanna (VEX) & Charm (CHEX) Exposure</div>', unsafe_allow_html=True)
        fig_vex_chex = go.Figure()
        fig_vex_chex.add_trace(go.Scatter(x=df_filtered["Strike"], y=df_filtered["Net_VEX"], mode="lines+markers", name="VEX", line=dict(color="#FFA726", width=2)))
        fig_vex_chex.add_trace(go.Scatter(x=df_filtered["Strike"], y=df_filtered["Net_CHEX"], mode="lines+markers", name="CHEX", line=dict(color="#AB47BC", width=2)))
        fig_vex_chex.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=10, b=0), height=280, xaxis=dict(tickmode='array', tickvals=df_filtered["Strike"], ticktext=strike_labels, tickangle=-45))
        st.plotly_chart(fig_vex_chex, use_container_width=True, key="chart_vex_chex")
        st.markdown('</div>', unsafe_allow_html=True)

    c5, c6 = st.columns(2)
    with c5:
        st.markdown('<div class="chart-container"><div class="chart-title">Expiry Day Speed Exposure (SPEX)</div>', unsafe_allow_html=True)
        fig_spex = go.Figure()
        colors_spex = ["#00E676" if g >= 0 else "#FF5252" for g in df_filtered["Net_SPEX"]]
        fig_spex.add_trace(go.Bar(x=df_filtered["Strike"], y=df_filtered["Net_SPEX"], marker_color=colors_spex, hovertemplate="Strike: %{x}<br>SPEX: %{y:,.2f}<extra></extra>"))
        fig_spex.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=10, b=0), height=250, xaxis=dict(tickmode='array', tickvals=df_filtered["Strike"], ticktext=strike_labels, tickangle=-45))
        st.plotly_chart(fig_spex, use_container_width=True, key="chart_spex")
        st.markdown('</div>', unsafe_allow_html=True)
        
    with c6:
        st.markdown('<div class="chart-container"><div class="chart-title">Max Pain Pinning Profile</div>', unsafe_allow_html=True)
        pain_strikes = df_oc["Strike"].values
        pain_curve = []
        for k_eval in pain_strikes:
            loss = np.sum(df_oc["CE_OI"].values * np.maximum(k_eval - pain_strikes, 0)) + np.sum(df_oc["PE_OI"].values * np.maximum(pain_strikes - k_eval, 0))
            pain_curve.append(loss)
            
        fig_pain = go.Figure()
        fig_pain.add_trace(go.Scatter(x=pain_strikes, y=pain_curve, mode="lines", fill="tozeroy", name="Writer Loss", line=dict(color="#8A93A6", width=1), fillcolor="rgba(138, 147, 166, 0.2)"))
        fig_pain.add_vline(x=spot_price, line_dash="solid", line_color="#FFD700", annotation_text="Spot")
        fig_pain.add_vline(x=max_pain_strike, line_dash="dash", line_color="#29B6F6", annotation_text=f"Max Pain: {max_pain_strike}")
        fig_pain.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=10, b=0), height=250)
        st.plotly_chart(fig_pain, use_container_width=True, key="chart_max_pain")
        st.markdown('</div>', unsafe_allow_html=True)

# ================= TAB 3: ORDER FLOW & MOMENTUM =================
with tab3:
    r3_col1, r3_col2 = st.columns(2)

    with r3_col1:
        st.markdown('<div class="chart-container"><div class="chart-title">Cumulative Open Interest Trend (Cr) <div class="info-tooltip">ⓘ<span class="tooltip-text">Tracks total Call and Put OI buildup across the day. A rising PE-CE curve indicates strong Bullish momentum.</span></div></div>', unsafe_allow_html=True)
        fig_oi_trend = go.Figure()
        if not pcr_df.empty:
            pcr_df["CE_OI_Cr"] = pcr_df["Total_CE_OI"] / 10000000
            pcr_df["PE_OI_Cr"] = pcr_df["Total_PE_OI"] / 10000000
            pcr_df["Net_OI_Cr"] = pcr_df["PE_OI_Cr"] - pcr_df["CE_OI_Cr"]
            
            fig_oi_trend.add_trace(go.Scatter(x=pcr_df["Time"], y=pcr_df["PE_OI_Cr"], mode="lines", name="Put OI", line=dict(color="#FF5252", width=2)))
            fig_oi_trend.add_trace(go.Scatter(x=pcr_df["Time"], y=pcr_df["CE_OI_Cr"], mode="lines", name="Call OI", line=dict(color="#00E676", width=2)))
            fig_oi_trend.add_trace(go.Scatter(x=pcr_df["Time"], y=pcr_df["Net_OI_Cr"], mode="lines", name="PE-CE (Diff)", line=dict(color="#AB47BC", width=2)))
        
        fig_oi_trend.update_xaxes(range=["09:15:00", "15:30:00"], dtick="3600000", gridcolor="#2A2E39")
        fig_oi_trend.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=10, b=0), height=280, legend=dict(orientation="h", y=1.1))
        st.plotly_chart(fig_oi_trend, use_container_width=True, key="chart_oi_trend")
        st.markdown('</div>', unsafe_allow_html=True)

    with r3_col2:
        st.markdown('<div class="chart-container"><div class="chart-title">Intraday PCR & Vol PCR Trend <div class="info-tooltip">ⓘ<span class="tooltip-text">Volume PCR reacts faster to immediate order flow, while OI PCR shows structural commitment.</span></div></div>', unsafe_allow_html=True)
        fig_pcr_trend = go.Figure()
        if not pcr_df.empty:
            fig_pcr_trend.add_trace(go.Scatter(x=pcr_df["Time"], y=pcr_df["PCR"], mode="lines", name="OI PCR", line=dict(color="#29B6F6", width=2)))
            if "Vol_PCR" in pcr_df.columns and pcr_df["Vol_PCR"].sum() > 0:
                fig_pcr_trend.add_trace(go.Scatter(x=pcr_df["Time"], y=pcr_df["Vol_PCR"], mode="lines", name="Vol PCR", line=dict(color="#FFA726", width=2)))
        
        fig_pcr_trend.update_xaxes(range=["09:15:00", "15:30:00"], dtick="3600000", gridcolor="#2A2E39")
        fig_pcr_trend.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=10, b=0), height=280, legend=dict(orientation="h", y=1.1))
        st.plotly_chart(fig_pcr_trend, use_container_width=True, key="chart_pcr_trend")
        st.markdown('</div>', unsafe_allow_html=True)

    r4_col1, r4_col2 = st.columns(2)

    with r4_col1:
        st.markdown('<div class="chart-container"><div class="chart-title">Real-Time Delta-Weighted Net OI <div class="info-tooltip">ⓘ<span class="tooltip-text">Tracks continuous Net Delta Weighted OI. Watch for severe drops near resistance—this flags short-covering panic.</span></div></div>', unsafe_allow_html=True)
        fig_doi = go.Figure()
        if not doi_df.empty:
            fig_doi.add_trace(go.Scatter(x=doi_df["Time"], y=doi_df["Total_Net_Delta_OI"], mode="lines", fill='tozeroy', line=dict(color="#00E676", width=2)))
        fig_doi.add_hline(y=0, line_dash="dash", line_color="white", opacity=0.3)
        fig_doi.update_xaxes(range=["09:15:00", "15:30:00"], dtick="3600000", gridcolor="#2A2E39")
        fig_doi.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=10, b=0), height=250)
        st.plotly_chart(fig_doi, use_container_width=True, key="chart_doi")
        st.markdown('</div>', unsafe_allow_html=True)

    with r4_col2:
        st.markdown('<div class="chart-container"><div class="chart-title">Dealer Delta Velocity (DEX 5m ROC) <div class="info-tooltip">ⓘ<span class="tooltip-text">Measures the 5-Minute rate of change of Dealer Delta Exposure. Extreme bars indicate dealers are violently shifting hedges.</span></div></div>', unsafe_allow_html=True)
        fig_dex_vel = go.Figure()
        if not doi_df.empty:
            colors_vel = ["#00E676" if v >= 0 else "#FF5252" for v in doi_df["DEX_Vel_5m"]]
            fig_dex_vel.add_trace(go.Bar(x=doi_df["Time"], y=doi_df["DEX_Vel_5m"], marker_color=colors_vel))
        fig_dex_vel.add_hline(y=0, line_dash="dash", line_color="white", opacity=0.3)
        fig_dex_vel.update_xaxes(range=["09:15:00", "15:30:00"], dtick="3600000", gridcolor="#2A2E39")
        fig_dex_vel.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=10, b=0), height=250)
        st.plotly_chart(fig_dex_vel, use_container_width=True, key="chart_dex_vel")
        st.markdown('</div>', unsafe_allow_html=True)

    r5_col1, r5_col2 = st.columns(2)

    with r5_col1:
        st.markdown('<div class="chart-container"><div class="chart-title">Anchored ATM Straddle Decay vs Expected <div class="info-tooltip">ⓘ<span class="tooltip-text">Compares actual ATM straddle premium against a theoretical Black-Scholes Theta decay model anchored at 09:20.</span></div></div>', unsafe_allow_html=True)
        fig_strad = go.Figure()
        if not strad_df.empty:
            fig_strad.add_trace(go.Scatter(x=strad_df["Time"], y=strad_df["Actual_Straddle"], mode="lines", name="Actual", line=dict(color="#29B6F6", width=2.5)))
            fig_strad.add_trace(go.Scatter(x=strad_df["Time"], y=strad_df["Expected_Straddle"], mode="lines", name="Expected Decay", line=dict(color="#8A93A6", width=1.5, dash="dot")))
        fig_strad.update_xaxes(range=["09:15:00", "15:30:00"], dtick="3600000", gridcolor="#2A2E39")
        fig_strad.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=10, b=0), height=250, legend=dict(orientation="h", y=1.1))
        st.plotly_chart(fig_strad, use_container_width=True, key="chart_strad")
        st.markdown('</div>', unsafe_allow_html=True)

    with r5_col2:
        st.markdown('<div class="chart-container"><div class="chart-title">Gamma Flip Migration (ΔFlip) <div class="info-tooltip">ⓘ<span class="tooltip-text">Tracks the structural movement of the Dealer Gamma Flip Level vs Spot. If the blue line drifts upward while Spot consolidates, dealer support is rising.</span></div></div>', unsafe_allow_html=True)
        fig_flip = go.Figure()
        if not gex_df.empty:
            fig_flip.add_trace(go.Scatter(x=gex_df["Time"], y=gex_df["Spot"], mode="lines", name="Spot", line=dict(color="#FFD700", width=2)))
            fig_flip.add_trace(go.Scatter(x=gex_df["Time"], y=gex_df["Flip_Strike"], mode="lines", name="Flip Level", line=dict(color="#29B6F6", width=2, dash="dash")))
        fig_flip.update_xaxes(range=["09:15:00", "15:30:00"], dtick="3600000", gridcolor="#2A2E39")
        fig_flip.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=10, b=0), height=250, legend=dict(orientation="h", y=1.1))
        st.plotly_chart(fig_flip, use_container_width=True, key="chart_flip_mig")
        st.markdown('</div>', unsafe_allow_html=True)

    r7_col1, r7_col2 = st.columns(2)

    with r7_col1:
        st.markdown('<div class="chart-container"><div class="chart-title">Normalized Gamma Z-Score (ZGEX) Tracker <div class="info-tooltip">ⓘ<span class="tooltip-text">Isolates structural regime shifts. Watch for lines dipping below -2.0, confirming a total regime collapse.</span></div></div>', unsafe_allow_html=True)
        fig_zgex = go.Figure()
        if not gex_df.empty:
            fig_zgex.add_trace(go.Scatter(x=gex_df["Time"], y=gex_df["Z_GEX"], mode="lines", fill='tozeroy', line=dict(color="#AB47BC", width=2)))
        fig_zgex.add_hline(y=1.0, line_dash="solid", line_color="#00E676", opacity=0.3)
        fig_zgex.add_hline(y=-1.0, line_dash="solid", line_color="#00E676", opacity=0.3)
        fig_zgex.add_hline(y=-2.0, line_dash="dash", line_color="#FF5252", annotation_text="Collapse", annotation_font=dict(color="#FF5252"))
        fig_zgex.update_xaxes(range=["09:15:00", "15:30:00"], dtick="3600000", gridcolor="#2A2E39")
        fig_zgex.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=10, b=0), height=250)
        st.plotly_chart(fig_zgex, use_container_width=True, key="chart_zgex")
        st.markdown('</div>', unsafe_allow_html=True)

    with r7_col2:
        # WebSocket Heavyweight Basket
        st.markdown('<div class="chart-container"><div class="chart-title">Futures Basis & Heavyweight CVD (Live WebSocket)</div>', unsafe_allow_html=True)
        nifty_fut = live_ws_data.get("NIFTY_FUT_LTP", 0.0)
        basis = nifty_fut - spot_price if nifty_fut > 0 else 0.0
        basis_color = "sub-green" if basis >= 0 else "sub-red"
        cvd_val = live_ws_data.get("CVD", 0.0)
        cvd_color = "sub-green" if cvd_val >= 0 else "sub-red"
        
        c_hw1, c_hw2, c_hw3 = st.columns(3)
        with c_hw1:
            st.markdown(f"""
                <div>
                    <div style="color: #8A93A6; font-size: 0.75rem; font-weight: 600;">NIFTY FUTURES</div>
                    <div style="font-size: 1.3rem; font-weight: 700; margin-top: 5px; color: #FFFFFF;">₹{nifty_fut:,.2f}</div>
                </div>
            """, unsafe_allow_html=True)
        with c_hw2:
            st.markdown(f"""
                <div>
                    <div style="color: #8A93A6; font-size: 0.75rem; font-weight: 600;">FUTURES BASIS</div>
                    <div style="font-size: 1.3rem; font-weight: 700; margin-top: 5px;" class="{basis_color}">{basis:+.2f} Pts</div>
                </div>
            """, unsafe_allow_html=True)
        with c_hw3:
            st.markdown(f"""
                <div>
                    <div style="color: #8A93A6; font-size: 0.75rem; font-weight: 600;">HEAVYWEIGHT CVD</div>
                    <div style="font-size: 1.3rem; font-weight: 700; margin-top: 5px;" class="{cvd_color}">{cvd_val:+,.0f} Vol</div>
                </div>
            """, unsafe_allow_html=True)
            
        conn_status = "🟢 ACTIVE" if live_ws_data.get("CONNECTED") else f"🔴 {live_ws_data.get('ERROR', 'RECONNECTING...')}"
        st.markdown(f'<div style="margin-top: 10px; font-size: 0.85rem; color: #8A93A6;">Daemon Status: {conn_status}</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

# ================= TAB 4: VOLATILITY & TERM STRUCTURE =================
with tab4:
    c1, c2 = st.columns(2)
    with c1:
        st.markdown('<div class="chart-container"><div class="chart-title">OpenBull IV Smile (Volatility Skew) <div class="info-tooltip">ⓘ<span class="tooltip-text">Asymmetric smiles indicate institutional demand for specific OTM protections (skew).</span></div></div>', unsafe_allow_html=True)
        fig_smile = go.Figure()
        fig_smile.add_trace(go.Scatter(x=df_filtered["Strike"], y=df_filtered["CE_IV"], mode="lines+markers", name="Call IV", line=dict(color="#00E676", width=2)))
        fig_smile.add_trace(go.Scatter(x=df_filtered["Strike"], y=df_filtered["PE_IV"], mode="lines+markers", name="Put IV", line=dict(color="#FF5252", width=2)))
        fig_smile.add_vline(x=spot_price, line_dash="solid", line_color="#FFD700")
        fig_smile.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=10, b=0), height=300, xaxis=dict(tickmode='array', tickvals=df_filtered["Strike"], ticktext=strike_labels, tickangle=-45))
        st.plotly_chart(fig_smile, use_container_width=True, key="chart_iv_smile")
        st.markdown('</div>', unsafe_allow_html=True)

    with c2:
        st.markdown('<div class="chart-container"><div class="chart-title">Forward Vol Term Structure (4 Expiries) <div class="info-tooltip">ⓘ<span class="tooltip-text">Normal markets exhibit an upward slope (Contango). A downward slope (Backwardation) flags near-term fear.</span></div></div>', unsafe_allow_html=True)
        df_vol_struct = fetch_multi_expiry_vol_structure(spot_price)
        if not df_vol_struct.empty and len(df_vol_struct) >= 2:
            fig_fwd = go.Figure()
            fig_fwd.add_trace(go.Scatter(x=df_vol_struct["Expiry"], y=df_vol_struct["Forward_Vol"], mode="lines+markers", line=dict(color="#00E676", width=2.5), marker=dict(size=8)))
            fig_fwd.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=10, b=0), height=300)
            st.plotly_chart(fig_fwd, use_container_width=True, key="chart_fwd_vol")
        else:
            st.info("Loading 4 expiries to build term structure... (Takes ~5 seconds due to API limits)")
        st.markdown('</div>', unsafe_allow_html=True)

    c3, c4 = st.columns(2)
    with c3:
        st.markdown('<div class="chart-container"><div class="chart-title">Cumulative Mean Volatility Curve</div>', unsafe_allow_html=True)
        if not df_vol_struct.empty and len(df_vol_struct) >= 2:
            fig_vol_curve = go.Figure()
            fig_vol_curve.add_trace(go.Scatter(x=df_vol_struct["Expiry"], y=df_vol_struct["Mean_IV"], mode="lines+markers", line=dict(color="#AB47BC", width=2.5), marker=dict(size=8)))
            fig_vol_curve.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=10, b=0), height=250)
            st.plotly_chart(fig_vol_curve, use_container_width=True, key="chart_cum_vol")
        else:
            st.info("Loading 4 expiries to build vol curve...")
        st.markdown('</div>', unsafe_allow_html=True)
        
    with c4:
        st.markdown('<div class="chart-container"><div class="chart-title">IV Spread by Strike (Call IV - Put IV)</div>', unsafe_allow_html=True)
        fig_iv_spread = go.Figure()
        colors_spread = ["#00E676" if v >= 0 else "#FF5252" for v in df_filtered["IV_Spread"]]
        fig_iv_spread.add_trace(go.Bar(x=df_filtered["Strike"], y=df_filtered["IV_Spread"], marker_color=colors_spread))
        fig_iv_spread.add_hline(y=0, line_dash="dash", line_color="white", opacity=0.3)
        fig_iv_spread.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=10, b=0), height=250, xaxis=dict(tickmode='array', tickvals=df_filtered["Strike"], ticktext=strike_labels, tickangle=-45))
        st.plotly_chart(fig_iv_spread, use_container_width=True, key="chart_iv_spread")
        st.markdown('</div>', unsafe_allow_html=True)

# ================= TAB 5: DATA GRID & PLAYBOOK =================
with tab5:
    st.markdown("### 📋 Institutional Options Chain Grid (OpenBull GEX Model)")
    grid_df = df_filtered[[
        "Strike", "CE_LTP", "PE_LTP", "CE_OI", "PE_OI", 
        "CE_GEX", "PE_GEX", "Net_GEX", 
        "CE_Delta", "PE_Delta", "Net_Delta_OI", "Net_DEX", 
        "Net_VEX", "Net_CHEX", "Net_SPEX", "CE_IV", "PE_IV", "IV_Spread"
    ]].copy()
    
    st.dataframe(
        grid_df.style.format({
            "Strike": "{:.0f}", "CE_LTP": "₹{:.2f}", "PE_LTP": "₹{:.2f}", 
            "CE_OI": "{:,.0f}", "PE_OI": "{:,.0f}", 
            "CE_GEX": "{:,.0f}", "PE_GEX": "{:,.0f}", "Net_GEX": "{:+,.0f}", 
            "CE_Delta": "{:.2f}", "PE_Delta": "{:.2f}", "Net_Delta_OI": "{:+,.0f}", 
            "Net_DEX": "{:+,.1f}L", "Net_VEX": "{:+,.2f}", "Net_CHEX": "{:+,.2f}", "Net_SPEX": "{:+,.2f}", 
            "CE_IV": "{:.1f}%", "PE_IV": "{:.1f}%", "IV_Spread": "{:+.2f}%"
        }),
        use_container_width=True, 
        height=400,
        hide_index=True
    )

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("### 📖 Institutional Playbook: Relative Option Demand")
    st.markdown("""
    <div class="chart-container">
        <table class="playbook-table">
            <thead>
                <tr>
                    <th>Spot Nifty Action</th>
                    <th>Relative Demand (IV Spread)</th>
                    <th>What Is Happening Under the Hood</th>
                    <th>Option Buyer Action</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>Sideways Range</td>
                    <td><span style="color:#00E676; font-weight:bold;">Surging Upward</span></td>
                    <td>Stealth Call accumulation by funds</td>
                    <td><span style="color:#00E676; font-weight:bold;">Buy ATM Calls</span> before the spot breakout</td>
                </tr>
                <tr>
                    <td>Rallying High</td>
                    <td><span style="color:#00E676; font-weight:bold;">Rising with Spot</span></td>
                    <td>High-conviction buying sweeping asks</td>
                    <td><span style="color:#00E676; font-weight:bold;">Hold Long Calls</span> (Ride the trend)</td>
                </tr>
                <tr>
                    <td>Rallying High</td>
                    <td><span style="color:#FF5252; font-weight:bold;">Falling Sharply</span></td>
                    <td>Retail buying absorbed by MMs selling</td>
                    <td><span style="color:#FF5252; font-weight:bold;">Avoid Calls</span> (High risk of sharp reversal)</td>
                </tr>
                <tr>
                    <td>Sideways Range</td>
                    <td><span style="color:#FF5252; font-weight:bold;">Plunging Downward</span></td>
                    <td>Stealth Put accumulation / hedging</td>
                    <td><span style="color:#FF5252; font-weight:bold;">Buy ATM Puts</span> before the spot breakdown</td>
                </tr>
            </tbody>
        </table>
    </div>
    """, unsafe_allow_html=True)

# Footer
st.markdown("<br><hr style='border-color: #45A29E;'><div style='text-align: center; color: #8A93A6; font-size: 0.75rem;'>Prince PAX Volatility Desk v2.1 | OpenBull GEX Model | Powered by Vectorized Quant Engine</div>", unsafe_allow_html=True)
