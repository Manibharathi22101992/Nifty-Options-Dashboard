import datetime
import time
import os
import threading
import logging
import math
from typing import Dict, List, Tuple, Optional, Any
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from streamlit_autorefresh import st_autorefresh

# Configure logging
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------
# 1. CONFIGURATION (NIFTY 2026 CURRENT SPECS)
# ---------------------------------------------------------
class Config:
    NIFTY_LOT_SIZE = 65  # Current Nifty lot size (updated)
    RISK_FREE_RATE = 0.065
    NIFTY_DIVIDEND_YIELD = 0.012
    API_TIMEOUT = 10
    MAX_RETRIES = 3
    STRIKE_INTERVAL = 50
    STRIKE_RANGE_ATM = 550  # ±550 for chart window
    MARKET_OPEN = "09:15:00"
    MARKET_CLOSE = "15:30:00"

try:
    from dhanhq import marketfeed
    DHAN_WS_AVAILABLE = True
except ImportError:
    DHAN_WS_AVAILABLE = False
    logger.warning("dhanhq not installed. WebSocket disabled.")

# ---------------------------------------------------------
# 2. BLOOMBERG-GRADE CSS (GLASSMORPHISM + PREMIUM)
# ---------------------------------------------------------
st.set_page_config(
    page_title="Prince PAX | Institutional Volatility Terminal",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');
    
    .stApp { 
        background: radial-gradient(ellipse at top, #0F1419 0%, #050709 100%);
        color: #E0E6ED; 
        font-family: 'Inter', -apple-system, sans-serif; 
    }
    section[data-testid="stSidebar"] { 
        background: linear-gradient(180deg, #0F1419 0%, #1A1F2E 100%) !important; 
        border-right: 1px solid rgba(99, 179, 237, 0.2); 
    }
    
    .metric-card {
        background: rgba(26, 32, 44, 0.7);
        backdrop-filter: blur(12px);
        border: 1px solid rgba(99, 179, 237, 0.2);
        border-radius: 12px;
        padding: 14px 18px;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
        margin-bottom: 12px;
        border-top: 4px solid #63B3ED;
        transition: all 0.3s ease;
    }
    .metric-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 12px 40px rgba(99, 179, 237, 0.15);
        border-color: rgba(99, 179, 237, 0.4);
    }
    .metric-card-green { border-top-color: #48BB78; }
    .metric-card-red { border-top-color: #F56565; }
    .metric-card-amber { border-top-color: #ECC94B; }
    .metric-card-purple { border-top-color: #9F7AEA; }
    .metric-card-cyan { border-top-color: #0BC5EA; }
    
    .metric-title { 
        color: #A0AEC0; 
        font-size: 0.68rem; 
        font-weight: 700; 
        text-transform: uppercase; 
        letter-spacing: 1.2px; 
    }
    .metric-value { 
        color: #FFFFFF; 
        font-size: 1.5rem; 
        font-weight: 800; 
        margin-top: 4px; 
        font-variant-numeric: tabular-nums;
    }
    .metric-sub { 
        font-size: 0.72rem; 
        font-weight: 600; 
        margin-top: 4px; 
    }
    
    .sub-green { color: #48BB78; } 
    .sub-red { color: #F56565; } 
    .sub-amber { color: #ECC94B; } 
    .sub-blue { color: #63B3ED; } 
    .sub-purple { color: #9F7AEA; }
    .sub-cyan { color: #0BC5EA; }

    .chart-container {
        background: rgba(26, 32, 44, 0.5);
        backdrop-filter: blur(10px);
        border: 1px solid rgba(99, 179, 237, 0.15);
        border-radius: 12px;
        padding: 16px;
        margin-bottom: 16px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
    }
    .chart-title {
        font-size: 0.82rem; 
        font-weight: 700; 
        color: #63B3ED;
        text-transform: uppercase; 
        margin-bottom: 12px;
        border-bottom: 2px solid rgba(99, 179, 237, 0.3); 
        padding-bottom: 8px;
        display: flex; 
        justify-content: space-between; 
        align-items: center;
        letter-spacing: 0.5px;
    }

    .info-tooltip { 
        position: relative; 
        display: inline-block; 
        cursor: help; 
        color: #A0AEC0; 
        font-size: 0.9rem; 
    }
    .info-tooltip .tooltip-text {
        visibility: hidden; 
        width: 300px; 
        background: rgba(15, 20, 25, 0.97);
        backdrop-filter: blur(10px);
        color: #E0E6ED;
        text-align: left; 
        border-radius: 8px; 
        padding: 12px; 
        position: absolute;
        top: 150%; 
        right: 0; 
        opacity: 0; 
        transition: opacity 0.3s;
        border: 1px solid rgba(99, 179, 237, 0.3); 
        font-size: 0.72rem; 
        font-weight: 500;
        box-shadow: 0px 8px 24px rgba(0,0,0,0.8); 
        z-index: 9999;
        line-height: 1.5;
    }
    .info-tooltip:hover .tooltip-text { visibility: visible; opacity: 1; }
    .info-tooltip:hover { color: #63B3ED; }

    .status-badge { 
        padding: 8px 16px; 
        border-radius: 6px; 
        font-weight: 700; 
        font-size: 0.78rem; 
        display: inline-block;
        backdrop-filter: blur(10px);
    }
    .status-live { 
        background: rgba(72, 187, 120, 0.15); 
        border: 1px solid #48BB78; 
        color: #48BB78; 
    }
    .status-closed { 
        background: rgba(236, 201, 75, 0.15); 
        border: 1px solid #ECC94B; 
        color: #ECC94B; 
    }
    
    .playbook-table { 
        width: 100%; 
        border-collapse: collapse; 
        font-size: 0.82rem; 
        margin-top: 12px; 
    }
    .playbook-table th { 
        background: rgba(15, 20, 25, 0.8);
        color: #63B3ED; 
        text-align: left; 
        padding: 10px; 
        border: 1px solid rgba(99, 179, 237, 0.2); 
        font-weight: 700;
    }
    .playbook-table td { 
        padding: 10px; 
        border: 1px solid rgba(99, 179, 237, 0.15); 
        color: #E0E6ED; 
    }
    
    button[data-baseweb="tab"] { 
        background: rgba(26, 32, 44, 0.6) !important; 
        color: #A0AEC0 !important; 
        border-radius: 8px 8px 0 0 !important;
        border: 1px solid rgba(99, 179, 237, 0.2) !important;
        border-bottom: none !important;
        font-weight: 600 !important;
        padding: 10px 18px !important;
        transition: all 0.3s ease !important;
    }
    button[data-baseweb="tab"]:hover {
        background: rgba(99, 179, 237, 0.1) !important;
        color: #63B3ED !important;
    }
    button[data-baseweb="tab"][aria-selected="true"] { 
        background: rgba(99, 179, 237, 0.2) !important; 
        color: #63B3ED !important; 
        font-weight: 800 !important;
        border-bottom: 2px solid #63B3ED !important;
    }
    
    .alert-banner {
        background: linear-gradient(90deg, rgba(245, 101, 101, 0.15) 0%, rgba(236, 201, 75, 0.15) 100%);
        border-left: 4px solid #F56565;
        padding: 14px 18px;
        border-radius: 8px;
        margin-bottom: 16px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

CLIENT_ID = str(st.secrets.get("DHAN_CLIENT_ID", "")).strip().replace('"', "").replace("'", "")
ACCESS_TOKEN = str(st.secrets.get("DHAN_ACCESS_TOKEN", "")).strip().replace('"', "").replace("'", "")

if not CLIENT_ID or not ACCESS_TOKEN:
    st.error("⚠️ **CRITICAL:** API credentials missing. Update `.streamlit/secrets.toml`")
    st.stop()

# ---------------------------------------------------------
# 3. INSTITUTIONAL MATHEMATICAL ENGINE
# ---------------------------------------------------------
class MathEngine:
    @staticmethod
    def norm_pdf(x: np.ndarray) -> np.ndarray:
        return np.exp(-0.5 * x**2) / np.sqrt(2 * np.pi)
    
    @staticmethod
    def calculate_bs_greeks(S, K, T, sigma, r=Config.RISK_FREE_RATE, q=Config.NIFTY_DIVIDEND_YIELD):
        """Dividend-adjusted Black-Scholes: Gamma, Vanna, Charm, Speed, Vomma, Veta"""
        T = np.maximum(T, 1e-5)
        sigma = np.maximum(sigma, 1e-4)
        S = np.maximum(S, 1e-5)
        K = np.maximum(K, 1e-5)
        
        d1 = (np.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
        d2 = d1 - sigma * np.sqrt(T)
        pdf_d1 = MathEngine.norm_pdf(d1)
        
        gamma = np.exp(-q * T) * pdf_d1 / (S * sigma * np.sqrt(T))
        vanna = -np.exp(-q * T) * pdf_d1 * d2 / sigma
        charm = -np.exp(-q * T) * pdf_d1 * (2 * (r - q) * np.sqrt(T) - d2 * sigma * np.sqrt(T)) / (2 * T * sigma)
        speed = -gamma / S * (1 + d1 / (sigma * np.sqrt(T)))
        vomma = gamma * S * np.sqrt(T) * d1 * d2 / sigma
        veta = -np.exp(-q * T) * S * pdf_d1 * np.sqrt(T) * (
            (r - q) * d2 / (sigma * np.sqrt(T)) + (1 + d1 * d2) / (2 * T)
        )
        return gamma, vanna, charm, speed, vomma, veta
    
    @staticmethod
    def calculate_max_pain(strikes, ce_oi, pe_oi):
        K = strikes.reshape(-1, 1)
        S = strikes.reshape(1, -1)
        total_loss = np.sum(ce_oi * np.maximum(K - S, 0) + pe_oi * np.maximum(S - K, 0), axis=1)
        return int(strikes[np.argmin(total_loss)])
    
    @staticmethod
    def detect_unusual_activity(df, threshold=2.0):
        df = df.copy()
        for col in ['CE_Vol', 'PE_Vol']:
            mean, std = df[col].mean(), df[col].std()
            df[f'{col}_Anomaly'] = (df[col] > mean + threshold * std).astype(int)
        df['Unusual'] = df['CE_Vol_Anomaly'] | df['PE_Vol_Anomaly']
        return df[df['Unusual'] == 1]

# ---------------------------------------------------------
# 4. PARQUET PERSISTENCE (INTRADAY MEMORY)
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
# 5. DATA ENGINES
# ---------------------------------------------------------
@st.cache_data(ttl=300)
def fetch_expiry_list():
    url = "https://api.dhan.co/v2/optionchain/expirylist"
    headers = {"client-id": CLIENT_ID, "access-token": ACCESS_TOKEN, "Content-Type": "application/json"}
    for _ in range(Config.MAX_RETRIES):
        try:
            res = requests.post(url, headers=headers, json={"UnderlyingScrip": 13, "UnderlyingSeg": "IDX_I"}, timeout=Config.API_TIMEOUT)
            if res.status_code == 200 and res.json().get("status") == "success":
                return res.json().get("data", [])
        except Exception as e:
            logger.warning(f"Expiry fetch failed: {e}")
            time.sleep(1)
    return []

@st.cache_data(ttl=3)
def fetch_option_chain(expiry_date):
    url = "https://api.dhan.co/v2/optionchain"
    headers = {"client-id": CLIENT_ID, "access-token": ACCESS_TOKEN, "Content-Type": "application/json"}
    payload = {"UnderlyingScrip": 13, "UnderlyingSeg": "IDX_I", "Expiry": expiry_date}
    
    for _ in range(Config.MAX_RETRIES):
        try:
            res = requests.post(url, headers=headers, json=payload, timeout=Config.API_TIMEOUT)
            data = res.json()
            if res.status_code == 200 and data.get("status") == "success":
                raw = data.get("data", {})
                spot = float(raw.get("last_price", 0.0))
                oc = raw.get("oc", {})
                if not oc: return None, spot, "No contracts"
                
                T = max((datetime.datetime.strptime(expiry_date, "%Y-%m-%d").date() - datetime.date.today()).days, 1) / 365.0
                
                strikes = np.array([int(float(k)) for k in oc.keys()])
                ce_oi = np.array([float(oc[k].get("ce", {}).get("oi", 0) or 0) for k in oc.keys()])
                pe_oi = np.array([float(oc[k].get("pe", {}).get("oi", 0) or 0) for k in oc.keys()])
                ce_vol = np.array([float(oc[k].get("ce", {}).get("volume", 0) or 0) for k in oc.keys()])
                pe_vol = np.array([float(oc[k].get("pe", {}).get("volume", 0) or 0) for k in oc.keys()])
                ce_ltp = np.array([float(oc[k].get("ce", {}).get("last_price", 0) or 0) for k in oc.keys()])
                pe_ltp = np.array([float(oc[k].get("pe", {}).get("last_price", 0) or 0) for k in oc.keys()])
                ce_iv = np.array([float(oc[k].get("ce", {}).get("implied_volatility", 0) or 0)/100 for k in oc.keys()])
                pe_iv = np.array([float(oc[k].get("pe", {}).get("implied_volatility", 0) or 0)/100 for k in oc.keys()])
                ce_delta = np.array([float(oc[k].get("ce", {}).get("greeks", {}).get("delta", 0) or 0) for k in oc.keys()])
                pe_delta = np.array([float(oc[k].get("pe", {}).get("greeks", {}).get("delta", 0) or 0) for k in oc.keys()])
                ce_gamma_api = np.array([float(oc[k].get("ce", {}).get("greeks", {}).get("gamma", 0) or 0) for k in oc.keys()])
                pe_gamma_api = np.array([float(oc[k].get("pe", {}).get("greeks", {}).get("gamma", 0) or 0) for k in oc.keys()])
                
                ce_gamma_bs, ce_vanna, ce_charm, ce_speed, ce_vomma, ce_veta = MathEngine.calculate_bs_greeks(
                    spot, strikes, T, np.maximum(ce_iv, 0.15))
                pe_gamma_bs, pe_vanna, pe_charm, pe_speed, pe_vomma, pe_veta = MathEngine.calculate_bs_greeks(
                    spot, strikes, T, np.maximum(pe_iv, 0.15))
                
                ce_gamma = np.where(ce_gamma_api > 0, ce_gamma_api, ce_gamma_bs)
                pe_gamma = np.where(pe_gamma_api > 0, pe_gamma_api, pe_gamma_bs)
                
                # OpenBull GEX Model
                ce_gex = ce_gamma * ce_oi * Config.NIFTY_LOT_SIZE
                pe_gex = pe_gamma * pe_oi * Config.NIFTY_LOT_SIZE
                net_gex = ce_gex - pe_gex
                abs_gex = ce_gex + pe_gex
                
                ce_dex = ce_oi * ce_delta * spot * Config.NIFTY_LOT_SIZE / 1e5
                pe_dex = pe_oi * pe_delta * spot * Config.NIFTY_LOT_SIZE / 1e5
                net_dex = ce_dex + pe_dex
                abs_dex = np.abs(ce_dex) + np.abs(pe_dex)
                net_delta_oi = (ce_oi * ce_delta) + (pe_oi * pe_delta)
                
                df = pd.DataFrame({
                    "Strike": strikes, "CE_LTP": ce_ltp, "PE_LTP": pe_ltp,
                    "CE_OI": ce_oi, "PE_OI": pe_oi, "CE_Vol": ce_vol, "PE_Vol": pe_vol,
                    "CE_Delta": ce_delta, "PE_Delta": pe_delta, "Net_Delta_OI": net_delta_oi,
                    "Net_DEX": net_dex, "ABS_DEX": abs_dex,
                    "CE_GEX": ce_gex, "PE_GEX": pe_gex, "Net_GEX": net_gex, "ABS_GEX": abs_gex,
                    "Net_VEX": ((ce_oi * ce_vanna) - (pe_oi * pe_vanna)) * Config.NIFTY_LOT_SIZE / 1e3,
                    "Net_CHEX": ((ce_oi * ce_charm) - (pe_oi * pe_charm)) * Config.NIFTY_LOT_SIZE / 1e3,
                    "Net_SPEX": ((ce_oi * ce_speed) - (pe_oi * pe_speed)) * Config.NIFTY_LOT_SIZE / 1e3,
                    "Net_VOMMA": ((ce_oi * ce_vomma) - (pe_oi * pe_vomma)) * Config.NIFTY_LOT_SIZE / 1e3,
                    "Net_VETA": ((ce_oi * ce_veta) - (pe_oi * pe_veta)) * Config.NIFTY_LOT_SIZE / 1e3,
                    "CE_IV": ce_iv * 100.0, "PE_IV": pe_iv * 100.0, "IV_Spread": (ce_iv - pe_iv) * 100.0,
                })
                return df.sort_values("Strike").reset_index(drop=True), spot, None
            else:
                return None, 0.0, str(data.get("remarks") or data.get("message") or f"HTTP {res.status_code}")
        except Exception as e:
            logger.warning(f"Chain fetch failed: {e}")
            time.sleep(1)
    return None, 0.0, "Connection Error"

@st.cache_data(ttl=300)
def fetch_term_structure(spot):
    expiries = fetch_expiry_list()
    if not expiries:
        today = datetime.date.today()
        expiries = [(today + datetime.timedelta(days=i)).strftime("%Y-%m-%d") 
                   for i in range(1, 45) if (today + datetime.timedelta(days=i)).weekday() == 3][:4]
    else:
        expiries = expiries[:4]
    
    vol_data = []
    for idx, exp in enumerate(expiries):
        if idx > 0: time.sleep(1.2)
        df_exp, exp_spot, _ = fetch_option_chain(exp)
        if df_exp is not None and not df_exp.empty:
            atm = int(round(exp_spot / 50) * 50)
            row = df_exp[df_exp["Strike"] == atm]
            synth = atm + row["CE_LTP"].values[0] - row["PE_LTP"].values[0] if not row.empty else exp_spot
            atm_strike = int(round(synth / 50) * 50)
            atm_row = df_exp[df_exp["Strike"] == atm_strike]
            ce_iv = atm_row["CE_IV"].values[0] if not atm_row.empty else df_exp["CE_IV"].mean()
            pe_iv = atm_row["PE_IV"].values[0] if not atm_row.empty else df_exp["PE_IV"].mean()
            days = max((datetime.datetime.strptime(exp, "%Y-%m-%d").date() - datetime.date.today()).days, 1)
            vol_data.append({
                "Expiry": datetime.datetime.strptime(exp, "%Y-%m-%d").strftime("%d %b"),
                "Days": days, "Tenor": days / 365.0, "Mean_IV": (ce_iv + pe_iv) / 2.0
            })
    
    df_vol = pd.DataFrame(vol_data)
    if df_vol.empty or len(df_vol) < 2: return pd.DataFrame()
    
    fwd_vols = []
    for i in range(len(df_vol)):
        if i == 0:
            fwd_vols.append(df_vol.loc[i, "Mean_IV"])
        else:
            t1, t2 = df_vol.loc[i-1, "Tenor"], df_vol.loc[i, "Tenor"]
            v1, v2 = df_vol.loc[i-1, "Mean_IV"]/100, df_vol.loc[i, "Mean_IV"]/100
            var_diff, dt = (v2**2 * t2) - (v1**2 * t1), t2 - t1
            fwd_vols.append(math.sqrt(var_diff / dt) * 100 if (var_diff > 0 and dt > 0) else v2 * 100)
    
    df_vol["Forward_Vol"] = fwd_vols
    return df_vol

# ---------------------------------------------------------
# 6. WEBSOCKET DAEMON
# ---------------------------------------------------------
@st.cache_resource
def start_websocket(client_id, access_token):
    ws_data = {
        "RELIANCE_LTP": 0.0, "RELIANCE_PREV": 0.0,
        "HDFCBANK_LTP": 0.0, "HDFCBANK_PREV": 0.0,
        "ICICIBANK_LTP": 0.0, "ICICIBANK_PREV": 0.0,
        "NIFTY_FUT_LTP": 0.0, "CVD": 0.0, "CONNECTED": False, "ERROR": None
    }
    if not DHAN_WS_AVAILABLE:
        ws_data["ERROR"] = "dhanhq not installed"
        return ws_data
    
    NIFTY_FUT_ID = "58756"
    instruments = [(1, "2885"), (1, "1333"), (1, "4963"), (2, NIFTY_FUT_ID)]
    sub_code = getattr(marketfeed, 'Ticker', 15)
    
    def on_connect(i): ws_data["CONNECTED"] = True
    def on_disconnect(i): ws_data["CONNECTED"] = False
    
    def on_message(instance, msg):
        if isinstance(msg, dict):
            sec_id = str(msg.get('security_id', ''))
            ltp = float(msg.get('LTP', 0.0))
            ltq = float(msg.get('last_trade_quantity', 0.0))
            if ltp > 0:
                if sec_id == NIFTY_FUT_ID:
                    ws_data["NIFTY_FUT_LTP"] = ltp
                elif sec_id in ["2885", "1333", "4963"]:
                    sym = "RELIANCE" if sec_id == "2885" else "HDFCBANK" if sec_id == "1333" else "ICICIBANK"
                    prev = ws_data[f"{sym}_PREV"]
                    if prev > 0:
                        if ltp > prev: ws_data["CVD"] += ltq
                        elif ltp < prev: ws_data["CVD"] -= ltq
                    ws_data[f"{sym}_LTP"] = ltp
                    ws_data[f"{sym}_PREV"] = ltp
    
    def run():
        try:
            feed = marketfeed.DhanFeed(client_id, access_token, instruments, sub_code,
                                       on_connect=on_connect, on_message=on_message)
            feed.run_forever()
        except Exception as e:
            ws_data["ERROR"] = str(e)
            ws_data["CONNECTED"] = False
    
    threading.Thread(target=run, daemon=True).start()
    return ws_data

# ---------------------------------------------------------
# 7. MAIN APPLICATION
# ---------------------------------------------------------
def main():
    st.sidebar.title("⚙️ Command Center")
    auto_refresh = st.sidebar.checkbox("🔄 Live Auto-Refresh (5s)", value=True)
    if auto_refresh: st_autorefresh(interval=5000, key="refresh")
    
    IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    now_ist = datetime.datetime.now(IST)
    today_str = now_ist.strftime("%Y-%m-%d")
    now_time = now_ist.strftime("%H:%M:%S")
    
    is_weekday = now_ist.weekday() < 5
    m_open = now_ist.replace(hour=9, minute=15, second=0, microsecond=0)
    m_close = now_ist.replace(hour=15, minute=30, second=0, microsecond=0)
    is_live = is_weekday and (m_open <= now_ist <= m_close)
    
    expiries = fetch_expiry_list()
    if expiries:
        selected_expiry = st.sidebar.selectbox("📅 Primary Expiry", expiries)
    else:
        days_to_thu = (3 - now_ist.weekday()) % 7
        default = (now_ist + datetime.timedelta(days=days_to_thu)).strftime("%Y-%m-%d")
        selected_expiry = st.sidebar.date_input("📅 Primary Expiry", 
            datetime.datetime.strptime(default, "%Y-%m-%d")).strftime("%Y-%m-%d")
    
    show_unusual = st.sidebar.checkbox("🚨 Highlight Unusual Activity", value=True)
    
    with st.spinner("Fetching institutional data..."):
        df_oc, spot, err = fetch_option_chain(selected_expiry)
    
    if err:
        st.error(f"⚠️ **Error:** {err}")
        st.stop()
    
    # Synthetic Future
    synth = spot
    if df_oc is not None and not df_oc.empty:
        atm_approx = int(round(spot / 50) * 50)
        row = df_oc[df_oc["Strike"] == atm_approx]
        if not row.empty:
            synth = atm_approx + row["CE_LTP"].values[0] - row["PE_LTP"].values[0]
    atm_strike = int(round(synth / 50) * 50)
    
    strikes_list = df_oc["Strike"].tolist()
    default_idx = strikes_list.index(atm_strike) if atm_strike in strikes_list else len(strikes_list)//2
    target_strike = st.sidebar.selectbox("🎯 Target Strike", strikes_list, index=default_idx)
    
    ws_data = start_websocket(CLIENT_ID, ACCESS_TOKEN)
    
    # Memory columns
    REQ_PCR = ["Date", "Timestamp_dt", "Time", "PCR", "Vol_PCR", "Delta_PCR_15m", "Total_CE_OI", "Total_PE_OI"]
    REQ_GEX = ["Date", "Timestamp_dt", "Time", "Total_Net_GEX", "Z_GEX", "Flip_Strike", "Spot"]
    REQ_DOI = ["Date", "Timestamp_dt", "Time", "Total_Net_Delta_OI", "Delta_OI_ROC_1m", "Total_Net_DEX", "DEX_Vel_5m"]
    REQ_STRAD = ["Date", "Time", "Actual_Straddle", "Expected_Straddle", "Regime"]
    
    for key, cols in [("pcr_history", REQ_PCR), ("gex_history", REQ_GEX), 
                      ("delta_oi_history", REQ_DOI), ("straddle_history", REQ_STRAD)]:
        if key not in st.session_state:
            st.session_state[key] = check_and_reset(key, cols, today_str, now_time)
    if "straddle_anchor" not in st.session_state:
        st.session_state["straddle_anchor"] = None
    
    if st.sidebar.button("🗑️ Reset Cache"):
        for k in ["pcr_history", "gex_history", "delta_oi_history", "straddle_history"]:
            st.session_state[k] = pd.DataFrame()
        st.session_state["straddle_anchor"] = None
        st.cache_data.clear()
        st.rerun()
    
    # CORE ANALYTICS
    max_pain = MathEngine.calculate_max_pain(df_oc["Strike"].values, df_oc["CE_OI"].values, df_oc["PE_OI"].values)
    
    # Gamma Flip
    df_sorted = df_oc.sort_values("Strike").copy()
    df_sorted["Cum_GEX"] = df_sorted["Net_GEX"].cumsum()
    gamma_flip = int(spot)
    for i in range(1, len(df_sorted)):
        p, c = df_sorted.iloc[i-1]["Cum_GEX"], df_sorted.iloc[i]["Cum_GEX"]
        if (p < 0 and c >= 0) or (p > 0 and c <= 0):
            gamma_flip = int((df_sorted.iloc[i-1]["Strike"] + df_sorted.iloc[i]["Strike"]) / 2)
            break
    
    target_row = df_oc[df_oc["Strike"] == target_strike]
    t_ce_iv = target_row["CE_IV"].values[0] if not target_row.empty else 0.0
    t_pe_iv = target_row["PE_IV"].values[0] if not target_row.empty else 0.0
    t_iv_spread = t_ce_iv - t_pe_iv
    
    df_f = df_oc[(df_oc["Strike"] >= atm_strike - Config.STRIKE_RANGE_ATM) & 
                 (df_oc["Strike"] <= atm_strike + Config.STRIKE_RANGE_ATM)].copy()
    strike_labels = df_f["Strike"].astype(str).tolist()
    
    total_net_gex = df_oc["Net_GEX"].sum()
    total_net_delta_oi = df_oc["Net_Delta_OI"].sum()
    total_net_dex = df_oc["Net_DEX"].sum() / 100.0
    total_ce_oi, total_pe_oi = df_oc["CE_OI"].sum(), df_oc["PE_OI"].sum()
    current_pcr = total_pe_oi / total_ce_oi if total_ce_oi > 0 else 0.0
    
    call_wall_gex = df_f.loc[df_f['Net_GEX'].idxmax()]['Strike'] if not df_f.empty else atm_strike
    put_wall_gex = df_f.loc[df_f['Net_GEX'].idxmin()]['Strike'] if not df_f.empty else atm_strike
    call_wall_dex = df_f.loc[df_f['Net_DEX'].idxmax()]['Strike'] if not df_f.empty else atm_strike
    put_wall_dex = df_f.loc[df_f['Net_DEX'].idxmin()]['Strike'] if not df_f.empty else atm_strike
    
    unusual_df = MathEngine.detect_unusual_activity(df_oc) if show_unusual else pd.DataFrame()
    
    # INTRADAY RECORDING
    if is_live:
        # Reset if new day
        for key in ["pcr_history", "gex_history", "delta_oi_history", "straddle_history"]:
            h = st.session_state[key]
            if not h.empty and h.iloc[-1].get("Date") != today_str:
                st.session_state[key] = h.iloc[0:0]
                if key == "straddle_history": st.session_state["straddle_anchor"] = None
        
        # PCR
        total_ce_vol = df_oc["CE_Vol"].sum()
        total_pe_vol = df_oc["PE_Vol"].sum()
        vol_pcr = total_pe_vol / total_ce_vol if total_ce_vol > 0 else 0.0
        pcr_df = st.session_state["pcr_history"]
        delta_15m = 0.0
        if pcr_df.empty or pcr_df.iloc[-1]["Time"] != now_time:
            if not pcr_df.empty:
                past = pcr_df[pcr_df["Timestamp_dt"] <= (now_ist - datetime.timedelta(minutes=15))]
                if not past.empty: delta_15m = current_pcr - past.iloc[-1]["PCR"]
            st.session_state["pcr_history"] = pd.concat([pcr_df, pd.DataFrame([{
                "Date": today_str, "Timestamp_dt": now_ist, "Time": now_time,
                "PCR": current_pcr, "Vol_PCR": vol_pcr, "Delta_PCR_15m": delta_15m,
                "Total_CE_OI": total_ce_oi, "Total_PE_OI": total_pe_oi
            }])], ignore_index=True)
            save_persisted_df(st.session_state["pcr_history"], "pcr_history")
        
        # Z-GEX
        gex_df = st.session_state["gex_history"]
        z_gex = 0.0
        if gex_df.empty or gex_df.iloc[-1]["Time"] != now_time:
            if len(gex_df) >= 2:
                mu, sig = gex_df["Total_Net_GEX"].tail(20).mean(), gex_df["Total_Net_GEX"].tail(20).std()
                if sig > 0: z_gex = (total_net_gex - mu) / sig
            st.session_state["gex_history"] = pd.concat([gex_df, pd.DataFrame([{
                "Date": today_str, "Timestamp_dt": now_ist, "Time": now_time,
                "Total_Net_GEX": total_net_gex, "Z_GEX": z_gex, "Flip_Strike": gamma_flip, "Spot": spot
            }])], ignore_index=True)
            save_persisted_df(st.session_state["gex_history"], "gex_history")
        
        # Delta OI
        doi_df = st.session_state["delta_oi_history"]
        doi_roc, dex_vel = 0.0, 0.0
        if doi_df.empty or doi_df.iloc[-1]["Time"] != now_time:
            if not doi_df.empty:
                p1 = doi_df[doi_df["Timestamp_dt"] <= (now_ist - datetime.timedelta(minutes=1))]
                if not p1.empty: doi_roc = total_net_delta_oi - p1.iloc[-1]["Total_Net_Delta_OI"]
                p5 = doi_df[doi_df["Timestamp_dt"] <= (now_ist - datetime.timedelta(minutes=5))]
                if not p5.empty: dex_vel = total_net_dex - p5.iloc[-1]["Total_Net_DEX"]
            st.session_state["delta_oi_history"] = pd.concat([doi_df, pd.DataFrame([{
                "Date": today_str, "Timestamp_dt": now_ist, "Time": now_time,
                "Total_Net_Delta_OI": total_net_delta_oi, "Delta_OI_ROC_1m": doi_roc,
                "Total_Net_DEX": total_net_dex, "DEX_Vel_5m": dex_vel
            }])], ignore_index=True)
            save_persisted_df(st.session_state["delta_oi_history"], "delta_oi_history")
        
        # Straddle
        strad_df = st.session_state["straddle_history"]
        atm_row = df_oc[df_oc["Strike"] == atm_strike]
        cur_strad = (atm_row["CE_LTP"].values[0] if not atm_row.empty else 0) + (atm_row["PE_LTP"].values[0] if not atm_row.empty else 0)
        elapsed = max(0, min((now_ist - m_open).total_seconds() / 60, 375))
        if elapsed >= 5 and st.session_state["straddle_anchor"] is None:
            st.session_state["straddle_anchor"] = cur_strad
        anchor = st.session_state["straddle_anchor"] or cur_strad
        exp_strad = anchor * (1 - 0.15 * math.sqrt(elapsed / 375))
        regime = "VOL COIL 🟢" if cur_strad > exp_strad + 2 else ("IV CRUSH 🔴" if cur_strad < exp_strad - 2 else "NORMAL")
        if strad_df.empty or strad_df.iloc[-1]["Time"] != now_time:
            st.session_state["straddle_history"] = pd.concat([strad_df, pd.DataFrame([{
                "Date": today_str, "Time": now_time, "Actual_Straddle": cur_strad,
                "Expected_Straddle": exp_strad, "Regime": regime
            }])], ignore_index=True)
            save_persisted_df(st.session_state["straddle_history"], "straddle_history")
    
    # Read latest for UI
    pcr_df = st.session_state["pcr_history"]
    gex_df = st.session_state["gex_history"]
    doi_df = st.session_state["delta_oi_history"]
    strad_df = st.session_state["straddle_history"]
    
    z_gex = gex_df.iloc[-1]["Z_GEX"] if not gex_df.empty else 0.0
    delta_pcr = pcr_df.iloc[-1]["Delta_PCR_15m"] if not pcr_df.empty else 0.0
    doi_roc = doi_df.iloc[-1]["Delta_OI_ROC_1m"] if not doi_df.empty else 0.0
    cur_strad = strad_df.iloc[-1]["Actual_Straddle"] if not strad_df.empty else 0.0
    strad_regime = strad_df.iloc[-1]["Regime"] if not strad_df.empty else "NORMAL"
    
    # Regime signals
    if z_gex < -2.0: z_sig, z_col, z_bord = "GAMMA COLLAPSE", "sub-red", "metric-card-red"
    elif -1 <= z_gex <= 1: z_sig, z_col, z_bord = "NORMAL DAMPENING", "sub-green", "metric-card-green"
    else: z_sig, z_col, z_bord = "TRANSITION ZONE", "sub-amber", "metric-card-amber"
    
    if total_net_delta_oi > 50000: d_sig, d_col = "STRONGLY BULLISH", "sub-green"
    elif total_net_delta_oi > 10000: d_sig, d_col = "MILDLY BULLISH", "sub-green"
    elif total_net_delta_oi < -50000: d_sig, d_col = "STRONGLY BEARISH", "sub-red"
    elif total_net_delta_oi < -10000: d_sig, d_col = "MILDLY BEARISH", "sub-red"
    else: d_sig, d_col = "NEUTRAL", "sub-amber"
    
    # HEADER
    st.markdown("### 🏛️ PRINCE PAX | INSTITUTIONAL VOLATILITY TERMINAL")
    status_cls = "status-live" if is_live else "status-closed"
    status_txt = "🟢 LIVE MARKET" if is_live else "🟠 MARKET CLOSED"
    st.markdown(f'<div class="status-badge {status_cls}">{status_txt} | Expiry: {selected_expiry} | IST: {now_time} | Lot: {Config.NIFTY_LOT_SIZE}</div>', unsafe_allow_html=True)
    
    if show_unusual and not unusual_df.empty:
        st.markdown(f'<div class="alert-banner">🚨 <strong>UNUSUAL ACTIVITY:</strong> {len(unusual_df)} strikes with abnormal volume</div>', unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # 6-TAB LAYOUT
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📊 Command Center",
        "🧱 Dealer Exposure (GEX/DEX/VEX/CHEX)",
        "🌊 Order Flow & Momentum",
        "📈 Volatility & Term Structure",
        "🚨 Activity Monitor",
        "📋 Data Grid"
    ])
    
    # ============ TAB 1: COMMAND CENTER ============
    with tab1:
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        with c1:
            st.markdown(f"""<div class="metric-card metric-card-amber">
                <div class="info-tooltip">ⓘ<span class="tooltip-text">Synthetic Future (K+C-P). Max Pain = expiry magnet.</span></div>
                <div class="metric-title">NIFTY SYNTH FUT</div>
                <div class="metric-value">₹{synth:,.2f}</div>
                <div class="metric-sub sub-amber">Spot: ₹{spot:,.2f} | Pain: {max_pain}</div>
            </div>""", unsafe_allow_html=True)
        with c2:
            sp_cls = "sub-green" if t_iv_spread >= 0 else "sub-red"
            sp_bord = "metric-card-green" if t_iv_spread >= 0 else "metric-card-red"
            st.markdown(f"""<div class="metric-card {sp_bord}">
                <div class="info-tooltip">ⓘ<span class="tooltip-text">IV Spread = Call IV - Put IV. Rising = stealth call accumulation.</span></div>
                <div class="metric-title">{target_strike} IV SPREAD</div>
                <div class="metric-value">{t_iv_spread:+.2f}%</div>
                <div class="metric-sub {sp_cls}">CE {t_ce_iv:.1f}% | PE {t_pe_iv:.1f}%</div>
            </div>""", unsafe_allow_html=True)
        with c3:
            pcr_cls = "sub-green" if delta_pcr >= 0.15 else ("sub-red" if delta_pcr <= -0.15 else "sub-amber")
            pcr_bord = "metric-card-green" if delta_pcr >= 0.15 else ("metric-card-red" if delta_pcr <= -0.15 else "metric-card-amber")
            st.markdown(f"""<div class="metric-card {pcr_bord}">
                <div class="info-tooltip">ⓘ<span class="tooltip-text">ΔPCR 15m. >+0.15 = aggressive put writing (bullish).</span></div>
                <div class="metric-title">ΔPCR 15M VELOCITY</div>
                <div class="metric-value">{delta_pcr:+.2f}</div>
                <div class="metric-sub {pcr_cls}">PCR: {current_pcr:.2f}</div>
            </div>""", unsafe_allow_html=True)
        with c4:
            doi_cls = "sub-green" if doi_roc >= 0 else "sub-red"
            st.markdown(f"""<div class="metric-card {'metric-card-green' if total_net_delta_oi >= 0 else 'metric-card-red'}">
                <div class="info-tooltip">ⓘ<span class="tooltip-text">Net Delta OI. Sharp drops = short-covering panic.</span></div>
                <div class="metric-title">NET DELTA OI</div>
                <div class="metric-value">{total_net_delta_oi:+,.0f}</div>
                <div class="metric-sub {doi_cls}">1m ROC: {doi_roc:+,.0f} | {d_sig}</div>
            </div>""", unsafe_allow_html=True)
        with c5:
            st.markdown(f"""<div class="metric-card {'metric-card-green' if strad_regime == 'VOL COIL 🟢' else 'metric-card-amber'}">
                <div class="info-tooltip">ⓘ<span class="tooltip-text">ATM straddle vs expected decay. VOL COIL = breakout imminent.</span></div>
                <div class="metric-title">STRADDLE DECAY</div>
                <div class="metric-value">₹{cur_strad:.1f}</div>
                <div class="metric-sub {'sub-green' if strad_regime == 'VOL COIL 🟢' else 'sub-amber'}">{strad_regime}</div>
            </div>""", unsafe_allow_html=True)
        with c6:
            st.markdown(f"""<div class="metric-card {z_bord}">
                <div class="info-tooltip">ⓘ<span class="tooltip-text">Z-GEX < -2.0 = gamma collapse. Squeeze regime.</span></div>
                <div class="metric-title">Z-GEX SCORE</div>
                <div class="metric-value">{z_gex:+.2f}</div>
                <div class="metric-sub {z_col}">{z_sig}</div>
            </div>""", unsafe_allow_html=True)
        
        # Key Levels Row
        st.markdown("<br>", unsafe_allow_html=True)
        l1, l2, l3, l4 = st.columns(4)
        with l1:
            st.markdown(f"""<div class="metric-card metric-card-purple">
                <div class="metric-title">MAX PAIN</div>
                <div class="metric-value">₹{max_pain:,.0f}</div>
                <div class="metric-sub sub-purple">Expiry Magnet</div>
            </div>""", unsafe_allow_html=True)
        with l2:
            st.markdown(f"""<div class="metric-card metric-card-cyan">
                <div class="metric-title">GAMMA FLIP</div>
                <div class="metric-value">₹{gamma_flip:,.0f}</div>
                <div class="metric-sub sub-cyan">Zero-Crossing</div>
            </div>""", unsafe_allow_html=True)
        with l3:
            st.markdown(f"""<div class="metric-card metric-card-green">
                <div class="metric-title">CALL WALL (RESIST)</div>
                <div class="metric-value">₹{call_wall_gex:,.0f}</div>
                <div class="metric-sub sub-green">GEX Peak</div>
            </div>""", unsafe_allow_html=True)
        with l4:
            st.markdown(f"""<div class="metric-card metric-card-red">
                <div class="metric-title">PUT WALL (SUPPORT)</div>
                <div class="metric-value">₹{put_wall_gex:,.0f}</div>
                <div class="metric-sub sub-red">GEX Trough</div>
            </div>""", unsafe_allow_html=True)
    
    # ============ TAB 2: DEALER EXPOSURE ============
    with tab2:
        # Row 1: GEX + DEX
        r1c1, r1c2 = st.columns(2)
        with r1c1:
            st.markdown('<div class="chart-container"><div class="chart-title">Net Gamma Exposure (GEX) <div class="info-tooltip">ⓘ<span class="tooltip-text">OpenBull: GEX = Γ × OI × Lot. Green = Put walls (support). Red = Call walls (resistance). Blue = Absolute GEX envelope.</span></div></div>', unsafe_allow_html=True)
            fig_gex = go.Figure()
            colors = ["#48BB78" if g >= 0 else "#F56565" for g in df_f["Net_GEX"]]
            fig_gex.add_trace(go.Bar(x=df_f["Strike"], y=df_f["Net_GEX"], marker_color=colors, name="Net GEX", opacity=0.8, hovertemplate="Strike: %{x}<br>Net GEX: %{y:,.0f}<extra></extra>"))
            fig_gex.add_trace(go.Scatter(x=df_f["Strike"], y=df_f["ABS_GEX"], mode="lines", name="|GEX|", line=dict(color="#63B3ED", width=2, shape="spline")))
            fig_gex.add_vline(x=spot, line_dash="solid", line_color="#ECC94B", line_width=2, annotation_text=f"Spot {spot:.0f}", annotation_position="top right")
            fig_gex.add_vline(x=gamma_flip, line_dash="dash", line_color="#9F7AEA", line_width=1.5, annotation_text=f"Flip {gamma_flip}", annotation_position="bottom right")
            fig_gex.add_vline(x=call_wall_gex, line_dash="dot", line_color="#48BB78", line_width=1, annotation_text=f"Call Wall {call_wall_gex}", annotation_position="top left")
            fig_gex.add_vline(x=put_wall_gex, line_dash="dot", line_color="#F56565", line_width=1, annotation_text=f"Put Wall {put_wall_gex}", annotation_position="top left")
            fig_gex.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0,r=0,t=10,b=0), height=400, legend=dict(orientation="h", y=1.12), xaxis=dict(tickmode='array', tickvals=df_f["Strike"], ticktext=strike_labels, tickangle=-45))
            st.plotly_chart(fig_gex, use_container_width=True, key="gex")
            st.markdown('</div>', unsafe_allow_html=True)
        
        with r1c2:
            st.markdown('<div class="chart-container"><div class="chart-title">Net Delta Exposure (DEX) <div class="info-tooltip">ⓘ<span class="tooltip-text">Rupee value of Delta per strike. Shows where directional bias concentrates.</span></div></div>', unsafe_allow_html=True)
            fig_dex = go.Figure()
            colors = ["#48BB78" if v >= 0 else "#F56565" for v in df_f["Net_DEX"]]
            fig_dex.add_trace(go.Bar(x=df_f["Strike"], y=df_f["Net_DEX"], marker_color=colors, name="Net DEX", opacity=0.8, hovertemplate="Strike: %{x}<br>DEX: %{y:,.1f}L<extra></extra>"))
            fig_dex.add_trace(go.Scatter(x=df_f["Strike"], y=df_f["ABS_DEX"], mode="lines", name="|DEX|", line=dict(color="#FFA726", width=2, shape="spline")))
            fig_dex.add_vline(x=spot, line_dash="solid", line_color="#ECC94B", line_width=2, annotation_text=f"Spot {spot:.0f}")
            fig_dex.add_vline(x=call_wall_dex, line_dash="dot", line_color="#48BB78", line_width=1)
            fig_dex.add_vline(x=put_wall_dex, line_dash="dot", line_color="#F56565", line_width=1)
            fig_dex.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0,r=0,t=10,b=0), height=400, legend=dict(orientation="h", y=1.12), xaxis=dict(tickmode='array', tickvals=df_f["Strike"], ticktext=strike_labels, tickangle=-45))
            st.plotly_chart(fig_dex, use_container_width=True, key="dex")
            st.markdown('</div>', unsafe_allow_html=True)
        
        # Row 2: CE vs PE GEX + SPEX
        r2c1, r2c2 = st.columns(2)
        with r2c1:
            st.markdown('<div class="chart-container"><div class="chart-title">CE vs PE GEX Comparison <div class="info-tooltip">ⓘ<span class="tooltip-text">Overlay of Call GEX (long) vs Put GEX (short). Visualizes the net gamma position per strike.</span></div></div>', unsafe_allow_html=True)
            fig_cg = go.Figure()
            fig_cg.add_trace(go.Bar(x=df_f["Strike"], y=df_f["CE_GEX"], name="CE GEX", marker_color="#48BB78", opacity=0.7))
            fig_cg.add_trace(go.Bar(x=df_f["Strike"], y=-df_f["PE_GEX"], name="PE GEX", marker_color="#F56565", opacity=0.7))
            fig_cg.add_trace(go.Scatter(x=df_f["Strike"], y=df_f["Net_GEX"], mode="lines", name="Net GEX", line=dict(color="#63B3ED", width=2.5)))
            fig_cg.add_hline(y=0, line_dash="solid", line_color="white", opacity=0.3)
            fig_cg.add_vline(x=spot, line_dash="solid", line_color="#ECC94B")
            fig_cg.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0,r=0,t=10,b=0), height=320, barmode='overlay', legend=dict(orientation="h", y=1.12), xaxis=dict(tickmode='array', tickvals=df_f["Strike"], ticktext=strike_labels, tickangle=-45))
            st.plotly_chart(fig_cg, use_container_width=True, key="ce_pe_gex")
            st.markdown('</div>', unsafe_allow_html=True)
        
        with r2c2:
            st.markdown('<div class="chart-container"><div class="chart-title">Speed Exposure (SPEX) <div class="info-tooltip">ⓘ<span class="tooltip-text">dΓ/dS — rate of change of gamma. Peaks show strikes that trigger max acceleration in 0DTE squeezes.</span></div></div>', unsafe_allow_html=True)
            fig_spex = go.Figure()
            colors = ["#48BB78" if g >= 0 else "#F56565" for g in df_f["Net_SPEX"]]
            fig_spex.add_trace(go.Bar(x=df_f["Strike"], y=df_f["Net_SPEX"], marker_color=colors, hovertemplate="Strike: %{x}<br>SPEX: %{y:,.2f}<extra></extra>"))
            fig_spex.add_hline(y=0, line_dash="dash", line_color="white", opacity=0.3)
            fig_spex.add_vline(x=spot, line_dash="solid", line_color="#ECC94B")
            fig_spex.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0,r=0,t=10,b=0), height=320, showlegend=False, xaxis=dict(tickmode='array', tickvals=df_f["Strike"], ticktext=strike_labels, tickangle=-45))
            st.plotly_chart(fig_spex, use_container_width=True, key="spex")
            st.markdown('</div>', unsafe_allow_html=True)
        
        # Row 3: VANNA + CHARM
        r3c1, r3c2 = st.columns(2)
        with r3c1:
            st.markdown('<div class="chart-container"><div class="chart-title">Vanna Exposure (VEX) <div class="info-tooltip">ⓘ<span class="tooltip-text">dΔ/dσ — delta sensitivity to IV changes. Peaks act as price magnets during vol shifts.</span></div></div>', unsafe_allow_html=True)
            fig_vex = go.Figure()
            fig_vex.add_trace(go.Scatter(x=df_f["Strike"], y=df_f["Net_VEX"], mode="lines+markers", name="Net VEX", line=dict(color="#FFA726", width=2.5), marker=dict(size=6)))
            fig_vex.add_hline(y=0, line_dash="dash", line_color="white", opacity=0.3)
            fig_vex.add_vline(x=spot, line_dash="solid", line_color="#ECC94B", annotation_text="Spot")
            fig_vex.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0,r=0,t=10,b=0), height=300, xaxis=dict(tickmode='array', tickvals=df_f["Strike"], ticktext=strike_labels, tickangle=-45))
            st.plotly_chart(fig_vex, use_container_width=True, key="vex")
            st.markdown('</div>', unsafe_allow_html=True)
        
        with r3c2:
            st.markdown('<div class="chart-container"><div class="chart-title">Charm Exposure (CHEX) <div class="info-tooltip">ⓘ<span class="tooltip-text">dΔ/dt — delta decay over time. Shows where dealers must re-hedge as expiry approaches.</span></div></div>', unsafe_allow_html=True)
            fig_chex = go.Figure()
            fig_chex.add_trace(go.Scatter(x=df_f["Strike"], y=df_f["Net_CHEX"], mode="lines+markers", name="Net CHEX", line=dict(color="#9F7AEA", width=2.5), marker=dict(size=6)))
            fig_chex.add_hline(y=0, line_dash="dash", line_color="white", opacity=0.3)
            fig_chex.add_vline(x=spot, line_dash="solid", line_color="#ECC94B", annotation_text="Spot")
            fig_chex.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0,r=0,t=10,b=0), height=300, xaxis=dict(tickmode='array', tickvals=df_f["Strike"], ticktext=strike_labels, tickangle=-45))
            st.plotly_chart(fig_chex, use_container_width=True, key="chex")
            st.markdown('</div>', unsafe_allow_html=True)
        
        # Row 4: VOMMA + MAX PAIN
        r4c1, r4c2 = st.columns(2)
        with r4c1:
            st.markdown('<div class="chart-container"><div class="chart-title">Vomma Exposure (VOLGA) <div class="info-tooltip">ⓘ<span class="tooltip-text">dVega/dσ — vega sensitivity to vol. Shows where dealers are most exposed to vol-of-vol moves.</span></div></div>', unsafe_allow_html=True)
            fig_vomma = go.Figure()
            colors = ["#48BB78" if v >= 0 else "#F56565" for v in df_f["Net_VOMMA"]]
            fig_vomma.add_trace(go.Bar(x=df_f["Strike"], y=df_f["Net_VOMMA"], marker_color=colors))
            fig_vomma.add_hline(y=0, line_dash="dash", line_color="white", opacity=0.3)
            fig_vomma.add_vline(x=spot, line_dash="solid", line_color="#ECC94B")
            fig_vomma.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0,r=0,t=10,b=0), height=300, showlegend=False, xaxis=dict(tickmode='array', tickvals=df_f["Strike"], ticktext=strike_labels, tickangle=-45))
            st.plotly_chart(fig_vomma, use_container_width=True, key="vomma")
            st.markdown('</div>', unsafe_allow_html=True)
        
        with r4c2:
            st.markdown('<div class="chart-container"><div class="chart-title">Max Pain Pinning Profile <div class="info-tooltip">ⓘ<span class="tooltip-text">Strike where option buyers suffer max loss. Institutional expiry magnet.</span></div></div>', unsafe_allow_html=True)
            pain_strikes = df_oc["Strike"].values
            pain_curve = [np.sum(df_oc["CE_OI"].values * np.maximum(k - pain_strikes, 0)) + np.sum(df_oc["PE_OI"].values * np.maximum(pain_strikes - k, 0)) for k in pain_strikes]
            fig_pain = go.Figure()
            fig_pain.add_trace(go.Scatter(x=pain_strikes, y=pain_curve, mode="lines", fill="tozeroy", line=dict(color="#A0AEC0", width=1.5), fillcolor="rgba(160, 174, 192, 0.15)"))
            fig_pain.add_vline(x=spot, line_dash="solid", line_color="#ECC94B", annotation_text=f"Spot {spot:.0f}")
            fig_pain.add_vline(x=max_pain, line_dash="dash", line_color="#9F7AEA", line_width=2, annotation_text=f"Max Pain {max_pain}")
            fig_pain.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0,r=0,t=10,b=0), height=300, showlegend=False)
            st.plotly_chart(fig_pain, use_container_width=True, key="pain")
            st.markdown('</div>', unsafe_allow_html=True)
    
    # ============ TAB 3: ORDER FLOW ============
    with tab3:
        # Row 1: OI Trend + PCR Trend
        r1c1, r1c2 = st.columns(2)
        with r1c1:
            st.markdown('<div class="chart-container"><div class="chart-title">Cumulative OI Trend (Cr) <div class="info-tooltip">ⓘ<span class="tooltip-text">Rising PE-CE curve = bullish momentum (puts written faster).</span></div></div>', unsafe_allow_html=True)
            fig_oi = go.Figure()
            if not pcr_df.empty:
                pcr_df = pcr_df.copy()
                pcr_df["CE_Cr"] = pcr_df["Total_CE_OI"] / 1e7
                pcr_df["PE_Cr"] = pcr_df["Total_PE_OI"] / 1e7
                pcr_df["Net_Cr"] = pcr_df["PE_Cr"] - pcr_df["CE_Cr"]
                fig_oi.add_trace(go.Scatter(x=pcr_df["Time"], y=pcr_df["PE_Cr"], mode="lines", name="Put OI", line=dict(color="#F56565", width=2)))
                fig_oi.add_trace(go.Scatter(x=pcr_df["Time"], y=pcr_df["CE_Cr"], mode="lines", name="Call OI", line=dict(color="#48BB78", width=2)))
                fig_oi.add_trace(go.Scatter(x=pcr_df["Time"], y=pcr_df["Net_Cr"], mode="lines", name="PE-CE Diff", line=dict(color="#9F7AEA", width=2)))
            fig_oi.update_xaxes(range=["09:15:00", "15:30:00"], dtick="3600000", gridcolor="#2D3748")
            fig_oi.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0,r=0,t=10,b=0), height=280, legend=dict(orientation="h", y=1.12))
            st.plotly_chart(fig_oi, use_container_width=True, key="oi_trend")
            st.markdown('</div>', unsafe_allow_html=True)
        
        with r1c2:
            st.markdown('<div class="chart-container"><div class="chart-title">PCR & Vol PCR Trend <div class="info-tooltip">ⓘ<span class="tooltip-text">Vol PCR reacts faster to order flow; OI PCR shows structural commitment.</span></div></div>', unsafe_allow_html=True)
            fig_pcr = go.Figure()
            if not pcr_df.empty:
                fig_pcr.add_trace(go.Scatter(x=pcr_df["Time"], y=pcr_df["PCR"], mode="lines", name="OI PCR", line=dict(color="#63B3ED", width=2)))
                if "Vol_PCR" in pcr_df.columns and pcr_df["Vol_PCR"].sum() > 0:
                    fig_pcr.add_trace(go.Scatter(x=pcr_df["Time"], y=pcr_df["Vol_PCR"], mode="lines", name="Vol PCR", line=dict(color="#FFA726", width=2)))
            fig_pcr.add_hline(y=1.0, line_dash="dash", line_color="white", opacity=0.3)
            fig_pcr.update_xaxes(range=["09:15:00", "15:30:00"], dtick="3600000", gridcolor="#2D3748")
            fig_pcr.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0,r=0,t=10,b=0), height=280, legend=dict(orientation="h", y=1.12))
            st.plotly_chart(fig_pcr, use_container_width=True, key="pcr_trend")
            st.markdown('</div>', unsafe_allow_html=True)
        
        # Row 2: Delta OI + DEX Velocity
        r2c1, r2c2 = st.columns(2)
        with r2c1:
            st.markdown('<div class="chart-container"><div class="chart-title">Delta-Weighted Net OI <div class="info-tooltip">ⓘ<span class="tooltip-text">Severe drops near resistance = short-covering panic (squeeze).</span></div></div>', unsafe_allow_html=True)
            fig_doi = go.Figure()
            if not doi_df.empty:
                fig_doi.add_trace(go.Scatter(x=doi_df["Time"], y=doi_df["Total_Net_Delta_OI"], mode="lines", fill='tozeroy', line=dict(color="#48BB78", width=2)))
            fig_doi.add_hline(y=0, line_dash="dash", line_color="white", opacity=0.3)
            fig_doi.update_xaxes(range=["09:15:00", "15:30:00"], dtick="3600000", gridcolor="#2D3748")
            fig_doi.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0,r=0,t=10,b=0), height=250)
            st.plotly_chart(fig_doi, use_container_width=True, key="doi")
            st.markdown('</div>', unsafe_allow_html=True)
        
        with r2c2:
            st.markdown('<div class="chart-container"><div class="chart-title">Dealer Delta Velocity (DEX 5m ROC) <div class="info-tooltip">ⓘ<span class="tooltip-text">Extreme bars = dealers violently shifting hedges. Explosive momentum signal.</span></div></div>', unsafe_allow_html=True)
            fig_dv = go.Figure()
            if not doi_df.empty:
                colors = ["#48BB78" if v >= 0 else "#F56565" for v in doi_df["DEX_Vel_5m"]]
                fig_dv.add_trace(go.Bar(x=doi_df["Time"], y=doi_df["DEX_Vel_5m"], marker_color=colors))
            fig_dv.add_hline(y=0, line_dash="dash", line_color="white", opacity=0.3)
            fig_dv.update_xaxes(range=["09:15:00", "15:30:00"], dtick="3600000", gridcolor="#2D3748")
            fig_dv.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0,r=0,t=10,b=0), height=250)
            st.plotly_chart(fig_dv, use_container_width=True, key="dex_vel")
            st.markdown('</div>', unsafe_allow_html=True)
        
        # Row 3: Straddle Decay + Gamma Flip Migration
        r3c1, r3c2 = st.columns(2)
        with r3c1:
            st.markdown('<div class="chart-container"><div class="chart-title">ATM Straddle Decay vs Expected <div class="info-tooltip">ⓘ<span class="tooltip-text">Anchored at 09:20. Actual > Expected = VOL COIL (breakout imminent).</span></div></div>', unsafe_allow_html=True)
            fig_strad = go.Figure()
            if not strad_df.empty:
                fig_strad.add_trace(go.Scatter(x=strad_df["Time"], y=strad_df["Actual_Straddle"], mode="lines", name="Actual", line=dict(color="#63B3ED", width=2.5)))
                fig_strad.add_trace(go.Scatter(x=strad_df["Time"], y=strad_df["Expected_Straddle"], mode="lines", name="Expected", line=dict(color="#A0AEC0", width=1.5, dash="dot")))
            fig_strad.update_xaxes(range=["09:15:00", "15:30:00"], dtick="3600000", gridcolor="#2D3748")
            fig_strad.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0,r=0,t=10,b=0), height=250, legend=dict(orientation="h", y=1.12))
            st.plotly_chart(fig_strad, use_container_width=True, key="strad")
            st.markdown('</div>', unsafe_allow_html=True)
        
        with r3c2:
            st.markdown('<div class="chart-container"><div class="chart-title">Gamma Flip Migration <div class="info-tooltip">ⓘ<span class="tooltip-text">Flip drifting up while spot consolidates = dealer support rising (bullish).</span></div></div>', unsafe_allow_html=True)
            fig_flip = go.Figure()
            if not gex_df.empty:
                fig_flip.add_trace(go.Scatter(x=gex_df["Time"], y=gex_df["Spot"], mode="lines", name="Spot", line=dict(color="#ECC94B", width=2)))
                fig_flip.add_trace(go.Scatter(x=gex_df["Time"], y=gex_df["Flip_Strike"], mode="lines", name="Flip", line=dict(color="#63B3ED", width=2, dash="dash")))
            fig_flip.update_xaxes(range=["09:15:00", "15:30:00"], dtick="3600000", gridcolor="#2D3748")
            fig_flip.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0,r=0,t=10,b=0), height=250, legend=dict(orientation="h", y=1.12))
            st.plotly_chart(fig_flip, use_container_width=True, key="flip")
            st.markdown('</div>', unsafe_allow_html=True)
        
        # Row 4: Z-GEX + WebSocket
        r4c1, r4c2 = st.columns(2)
        with r4c1:
            st.markdown('<div class="chart-container"><div class="chart-title">Z-GEX Regime Tracker <div class="info-tooltip">ⓘ<span class="tooltip-text">Below -2.0 = total regime collapse. Dealers forced to buy rips, sell dips.</span></div></div>', unsafe_allow_html=True)
            fig_zgex = go.Figure()
            if not gex_df.empty:
                fig_zgex.add_trace(go.Scatter(x=gex_df["Time"], y=gex_df["Z_GEX"], mode="lines", fill='tozeroy', line=dict(color="#9F7AEA", width=2)))
            fig_zgex.add_hline(y=1.0, line_dash="solid", line_color="#48BB78", opacity=0.3)
            fig_zgex.add_hline(y=-1.0, line_dash="solid", line_color="#48BB78", opacity=0.3)
            fig_zgex.add_hline(y=-2.0, line_dash="dash", line_color="#F56565", annotation_text="Collapse", annotation_font=dict(color="#F56565"))
            fig_zgex.update_xaxes(range=["09:15:00", "15:30:00"], dtick="3600000", gridcolor="#2D3748")
            fig_zgex.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0,r=0,t=10,b=0), height=250)
            st.plotly_chart(fig_zgex, use_container_width=True, key="zgex")
            st.markdown('</div>', unsafe_allow_html=True)
        
        with r4c2:
            st.markdown('<div class="chart-container"><div class="chart-title">Futures Basis & Heavyweight CVD (Live WS)</div>', unsafe_allow_html=True)
            nifty_fut = ws_data.get("NIFTY_FUT_LTP", 0.0)
            basis = nifty_fut - spot if nifty_fut > 0 else 0.0
            basis_col = "sub-green" if basis >= 0 else "sub-red"
            cvd = ws_data.get("CVD", 0.0)
            cvd_col = "sub-green" if cvd >= 0 else "sub-red"
            wc1, wc2, wc3 = st.columns(3)
            with wc1:
                st.markdown(f'<div style="color:#A0AEC0;font-size:0.7rem;font-weight:700;">NIFTY FUT</div><div style="font-size:1.3rem;font-weight:800;color:#fff;">₹{nifty_fut:,.2f}</div>', unsafe_allow_html=True)
            with wc2:
                st.markdown(f'<div style="color:#A0AEC0;font-size:0.7rem;font-weight:700;">BASIS</div><div style="font-size:1.3rem;font-weight:800;" class="{basis_col}">{basis:+.2f}</div>', unsafe_allow_html=True)
            with wc3:
                st.markdown(f'<div style="color:#A0AEC0;font-size:0.7rem;font-weight:700;">HEAVYWEIGHT CVD</div><div style="font-size:1.3rem;font-weight:800;" class="{cvd_col}">{cvd:+,.0f}</div>', unsafe_allow_html=True)
            conn = "🟢 ACTIVE" if ws_data.get("CONNECTED") else f"🔴 {ws_data.get('ERROR', 'OFFLINE')}"
            st.markdown(f'<div style="margin-top:10px;font-size:0.8rem;color:#A0AEC0;">Daemon: {conn}</div>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)
    
    # ============ TAB 4: VOLATILITY & TERM STRUCTURE ============
    with tab4:
        # Row 1: IV Smile + IV Spread
        r1c1, r1c2 = st.columns(2)
        with r1c1:
            st.markdown('<div class="chart-container"><div class="chart-title">IV Smile (Volatility Skew) <div class="info-tooltip">ⓘ<span class="tooltip-text">Asymmetric smile = institutional demand for OTM protection (skew).</span></div></div>', unsafe_allow_html=True)
            fig_smile = go.Figure()
            fig_smile.add_trace(go.Scatter(x=df_f["Strike"], y=df_f["CE_IV"], mode="lines+markers", name="Call IV", line=dict(color="#48BB78", width=2), marker=dict(size=5)))
            fig_smile.add_trace(go.Scatter(x=df_f["Strike"], y=df_f["PE_IV"], mode="lines+markers", name="Put IV", line=dict(color="#F56565", width=2), marker=dict(size=5)))
            fig_smile.add_vline(x=spot, line_dash="solid", line_color="#ECC94B", line_width=2, annotation_text=f"Spot {spot:.0f}")
            fig_smile.add_vline(x=atm_strike, line_dash="dot", line_color="#63B3ED", annotation_text=f"ATM {atm_strike}")
            fig_smile.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0,r=0,t=10,b=0), height=350, legend=dict(orientation="h", y=1.12), xaxis=dict(tickmode='array', tickvals=df_f["Strike"], ticktext=strike_labels, tickangle=-45))
            st.plotly_chart(fig_smile, use_container_width=True, key="smile")
            st.markdown('</div>', unsafe_allow_html=True)
        
        with r1c2:
            st.markdown('<div class="chart-container"><div class="chart-title">IV Spread by Strike (Call - Put) <div class="info-tooltip">ⓘ<span class="tooltip-text">Green = call skew (bullish demand). Red = put skew (bearish demand).</span></div></div>', unsafe_allow_html=True)
            fig_spread = go.Figure()
            colors = ["#48BB78" if v >= 0 else "#F56565" for v in df_f["IV_Spread"]]
            fig_spread.add_trace(go.Bar(x=df_f["Strike"], y=df_f["IV_Spread"], marker_color=colors, hovertemplate="Strike: %{x}<br>IV Spread: %{y:+.2f}%<extra></extra>"))
            fig_spread.add_hline(y=0, line_dash="dash", line_color="white", opacity=0.3)
            fig_spread.add_vline(x=spot, line_dash="solid", line_color="#ECC94B")
            fig_spread.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0,r=0,t=10,b=0), height=350, xaxis=dict(tickmode='array', tickvals=df_f["Strike"], ticktext=strike_labels, tickangle=-45))
            st.plotly_chart(fig_spread, use_container_width=True, key="spread")
            st.markdown('</div>', unsafe_allow_html=True)
        
        # Row 2: Term Structure
        with st.spinner("Building 4-expiry term structure..."):
            df_vol = fetch_term_structure(spot)
        
        r2c1, r2c2 = st.columns(2)
        with r2c1:
            st.markdown('<div class="chart-container"><div class="chart-title">Forward Vol Term Structure (4 Expiries) <div class="info-tooltip">ⓘ<span class="tooltip-text">Upward slope = Contango (normal). Downward = Backwardation (near-term fear).</span></div></div>', unsafe_allow_html=True)
            if not df_vol.empty and len(df_vol) >= 2:
                fig_fwd = go.Figure()
                fig_fwd.add_trace(go.Scatter(x=df_vol["Expiry"], y=df_vol["Forward_Vol"], mode="lines+markers", line=dict(color="#48BB78", width=3), marker=dict(size=10, color="#48BB78", line=dict(color="#fff", width=2))))
                fig_fwd.add_hline(y=df_vol["Forward_Vol"].mean(), line_dash="dash", line_color="#A0AEC0", annotation_text="Mean")
                fig_fwd.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0,r=0,t=10,b=0), height=320, yaxis_title="Forward Vol %")
                st.plotly_chart(fig_fwd, use_container_width=True, key="fwd")
            else:
                st.info("Loading 4 expiries... (~5s)")
            st.markdown('</div>', unsafe_allow_html=True)
        
        with r2c2:
            st.markdown('<div class="chart-container"><div class="chart-title">ATM Mean IV Curve (4 Expiries)</div>', unsafe_allow_html=True)
            if not df_vol.empty and len(df_vol) >= 2:
                fig_ivc = go.Figure()
                fig_ivc.add_trace(go.Scatter(x=df_vol["Expiry"], y=df_vol["Mean_IV"], mode="lines+markers", line=dict(color="#9F7AEA", width=3), marker=dict(size=10, color="#9F7AEA", line=dict(color="#fff", width=2))))
                fig_ivc.add_hline(y=df_vol["Mean_IV"].mean(), line_dash="dash", line_color="#A0AEC0", annotation_text="Mean")
                fig_ivc.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0,r=0,t=10,b=0), height=320, yaxis_title="Mean IV %")
                st.plotly_chart(fig_ivc, use_container_width=True, key="ivc")
            else:
                st.info("Loading 4 expiries...")
            st.markdown('</div>', unsafe_allow_html=True)
        
        # Term structure table
        if not df_vol.empty and len(df_vol) >= 2:
            st.markdown('<div class="chart-container"><div class="chart-title">Term Structure Summary</div>', unsafe_allow_html=True)
            st.dataframe(
                df_vol[["Expiry", "Days", "Mean_IV", "Forward_Vol"]].style.format({
                    "Days": "{:.0f}", "Mean_IV": "{:.2f}%", "Forward_Vol": "{:.2f}%"
                }),
                use_container_width=True, hide_index=True
            )
            st.markdown('</div>', unsafe_allow_html=True)
    
    # ============ TAB 5: ACTIVITY MONITOR ============
    with tab5:
        if show_unusual and not unusual_df.empty:
            st.markdown(f'<div class="alert-banner">🚨 <strong>{len(unusual_df)} STRIKES</strong> showing abnormal volume patterns (>{2}σ)</div>', unsafe_allow_html=True)
            st.dataframe(
                unusual_df[["Strike", "CE_Vol", "PE_Vol", "CE_OI", "PE_OI", "CE_IV", "PE_IV", "Net_GEX"]].style.format({
                    "Strike": "{:.0f}", "CE_Vol": "{:,.0f}", "PE_Vol": "{:,.0f}",
                    "CE_OI": "{:,.0f}", "PE_OI": "{:,.0f}", "CE_IV": "{:.1f}%", "PE_IV": "{:.1f}%", "Net_GEX": "{:+,.0f}"
                }),
                use_container_width=True, height=400, hide_index=True
            )
        else:
            st.success("✅ No unusual activity. Volume patterns within normal statistical range.")
        
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("### 📖 Institutional Playbook")
        st.markdown("""
        <div class="chart-container">
            <table class="playbook-table">
                <thead><tr>
                    <th>Spot Action</th><th>IV Spread</th><th>Under the Hood</th><th>Action</th>
                </tr></thead>
                <tbody>
                    <tr><td>Sideways</td><td style="color:#48BB78;font-weight:700;">Surging ↑</td><td>Stealth call accumulation</td><td style="color:#48BB78;font-weight:700;">Buy ATM Calls</td></tr>
                    <tr><td>Rallying</td><td style="color:#48BB78;font-weight:700;">Rising with Spot</td><td>High-conviction buying</td><td style="color:#48BB78;font-weight:700;">Hold Long Calls</td></tr>
                    <tr><td>Rallying</td><td style="color:#F56565;font-weight:700;">Falling Sharply</td><td>Retail absorbed by MMs</td><td style="color:#F56565;font-weight:700;">Avoid Calls</td></tr>
                    <tr><td>Sideways</td><td style="color:#F56565;font-weight:700;">Plunging ↓</td><td>Stealth put accumulation</td><td style="color:#F56565;font-weight:700;">Buy ATM Puts</td></tr>
                </tbody>
            </table>
        </div>
        """, unsafe_allow_html=True)
    
    # ============ TAB 6: DATA GRID ============
    with tab6:
        st.markdown("### 📋 Institutional Options Chain (OpenBull GEX)")
        grid = df_f[[
            "Strike", "CE_LTP", "PE_LTP", "CE_OI", "PE_OI",
            "CE_GEX", "PE_GEX", "Net_GEX",
            "CE_Delta", "PE_Delta", "Net_Delta_OI", "Net_DEX",
            "Net_VEX", "Net_CHEX", "Net_SPEX", "Net_VOMMA",
            "CE_IV", "PE_IV", "IV_Spread"
        ]].copy()
        
        st.dataframe(
            grid.style.format({
                "Strike": "{:.0f}", "CE_LTP": "₹{:.2f}", "PE_LTP": "₹{:.2f}",
                "CE_OI": "{:,.0f}", "PE_OI": "{:,.0f}",
                "CE_GEX": "{:,.0f}", "PE_GEX": "{:,.0f}", "Net_GEX": "{:+,.0f}",
                "CE_Delta": "{:.2f}", "PE_Delta": "{:.2f}", "Net_Delta_OI": "{:+,.0f}",
                "Net_DEX": "{:+,.1f}L", "Net_VEX": "{:+,.2f}", "Net_CHEX": "{:+,.2f}",
                "Net_SPEX": "{:+,.2f}", "Net_VOMMA": "{:+,.2f}",
                "CE_IV": "{:.1f}%", "PE_IV": "{:.1f}%", "IV_Spread": "{:+.2f}%"
            }),
            use_container_width=True, height=500, hide_index=True
        )
    
    # Footer
    st.markdown("<br><hr style='border-color: rgba(99, 179, 237, 0.2);'>", unsafe_allow_html=True)
    st.markdown(
        "<div style='text-align:center;color:#A0AEC0;font-size:0.72rem;'>"
        "Prince PAX Institutional Volatility Terminal v3.1 | OpenBull GEX | "
        "NIFTY Lot: 65 | Dividend-Adjusted Greeks | Vectorized Engine"
        "</div>", unsafe_allow_html=True
    )

if __name__ == "__main__":
    main()
