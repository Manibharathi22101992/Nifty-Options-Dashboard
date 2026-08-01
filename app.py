import datetime
import math
import time
import os
import threading
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st
from streamlit_autorefresh import st_autorefresh

# Graceful fallback in case dhanhq isn't in requirements.txt yet
try:
    from dhanhq import marketfeed
    DHAN_WS_AVAILABLE = True
except ImportError:
    DHAN_WS_AVAILABLE = False

# ---------------------------------------------------------
# 1. PAGE SETUP & TRADYTICS-STYLE TERMINAL CSS
# ---------------------------------------------------------
st.set_page_config(
    page_title="Prince PAX Dashboard | Volatility Desk",
    layout="wide",
    initial_sidebar_state="collapsed", 
)

st.markdown(
    """
    <style>
    .stApp { background-color: #0A0A0A; color: #D1D4DC; font-family: 'Inter', sans-serif; }
    section[data-testid="stSidebar"] { background-color: #111115 !important; border-right: 1px solid #2A2E39; }
    
    .metric-card {
        background: #14151A;
        border: 1px solid #2A2E39;
        border-radius: 6px;
        padding: 10px 14px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.5);
        margin-bottom: 12px;
        border-top: 3px solid #3B4252;
        position: relative;
        overflow: visible !important;
    }
    .metric-card-green { border-top: 3px solid #00E676; }
    .metric-card-red { border-top: 3px solid #FF5252; }
    .metric-card-amber { border-top: 3px solid #FFD700; }
    
    .metric-title { color: #8A93A6; font-size: 0.65rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; }
    .metric-value { color: #FFFFFF; font-size: 1.25rem; font-weight: 800; margin-top: 2px; }
    .metric-sub { font-size: 0.75rem; font-weight: 600; margin-top: 2px; }
    
    .sub-green { color: #00E676; }
    .sub-red { color: #FF5252; }
    .sub-amber { color: #FFD700; }
    .sub-blue { color: #29B6F6; }

    .chart-container {
        background: #14151A;
        border: 1px solid #2A2E39;
        border-radius: 6px;
        padding: 12px;
        margin-bottom: 16px;
        position: relative;
        overflow: visible !important;
    }
    .chart-title {
        font-size: 0.85rem;
        font-weight: 700;
        color: #8A93A6;
        text-transform: uppercase;
        margin-bottom: 10px;
        border-bottom: 1px solid #2A2E39;
        padding-bottom: 5px;
    }

    /* Fixed CSS-Based Tooltip */
    .info-tooltip {
        position: relative;
        display: inline-block;
        cursor: help;
        color: #8A93A6;
        float: right;
        margin-left: 5px;
        font-size: 0.9rem;
        z-index: 999999;
    }
    .info-tooltip .tooltip-text {
        visibility: hidden;
        width: 260px;
        background-color: #1E2638;
        color: #E0E6ED;
        text-align: left;
        border-radius: 6px;
        padding: 10px 14px;
        position: absolute;
        top: 140%; 
        right: -10px;
        opacity: 0;
        transition: opacity 0.2s;
        border: 1px solid #3B4252;
        font-size: 0.75rem;
        font-weight: 500;
        box-shadow: 0px 4px 15px rgba(0,0,0,0.8);
        line-height: 1.4;
    }
    .info-tooltip .tooltip-text::after {
        content: "";
        position: absolute;
        bottom: 100%;
        right: 15px;
        border-width: 6px;
        border-style: solid;
        border-color: transparent transparent #3B4252 transparent;
    }
    .info-tooltip:hover .tooltip-text { visibility: visible; opacity: 1; }
    .info-tooltip:hover { color: #FFFFFF; }

    .status-badge {
        padding: 4px 10px;
        border-radius: 4px;
        font-weight: 700;
        font-size: 0.75rem;
        display: inline-block;
        margin-right: 10px;
    }
    .status-live { background-color: rgba(0, 230, 118, 0.15); border: 1px solid #00E676; color: #00E676; }
    .status-closed { background-color: rgba(255, 167, 38, 0.15); border: 1px solid #FFA726; color: #FFA726; }
    
    .summary-box { background: #121824; border: 1px solid #2A2E39; border-radius: 8px; padding: 16px 20px; margin-bottom: 20px; }
    .playbook-table { width: 100%; border-collapse: collapse; font-size: 0.85rem; margin-top: 10px; }
    .playbook-table th { background-color: #1e2638; color: #8b9bb4; text-align: left; padding: 8px; border: 1px solid #2A2E39; }
    .playbook-table td { padding: 8px; border: 1px solid #2A2E39; color: #D1D4DC; }
    </style>
    """,
    unsafe_allow_html=True,
)

# Clean API Credentials
CLIENT_ID = str(st.secrets.get("DHAN_CLIENT_ID", "")).strip().replace('"', "").replace("'", "")
ACCESS_TOKEN = str(st.secrets.get("DHAN_ACCESS_TOKEN", "")).strip().replace('"', "").replace("'", "")

if not CLIENT_ID or not ACCESS_TOKEN:
    st.error("⚠️ API credentials missing. Please update your Streamlit Secrets.")
    st.stop()

NIFTY_LOT_SIZE = 25

# ---------------------------------------------------------
# 2. LOCAL PARQUET PERSISTENCE & WEBSOCKET DAEMON
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
        # Retain yesterday's data UNTIL 09:15 AM today
        if last_date != today_date_str and now_time_str >= "09:15:00":
            df = pd.DataFrame(columns=cols)
            save_persisted_df(df, df_name)
    return df

@st.cache_resource
def start_dhan_websocket(client_id, access_token):
    ws_data = {
        "RELIANCE_LTP": 0.0, "RELIANCE_PREV": 0.0,
        "HDFCBANK_LTP": 0.0, "HDFCBANK_PREV": 0.0,
        "ICICIBANK_LTP": 0.0, "ICICIBANK_PREV": 0.0,
        "NIFTY_FUT_LTP": 0.0, "CVD": 0.0, "CONNECTED": False
    }

    if not DHAN_WS_AVAILABLE:
        ws_data["ERROR"] = "dhanhq not installed"
        return ws_data

    # IMPORTANT: Update this Nifty Futures ID when the monthly contract expires
    CURRENT_NIFTY_FUT_ID = "58756" 
    
    # Explicitly using integer codes to avoid AttributeError across different dhanhq versions
    # 1 = NSE Equity, 2 = NSE FNO
    instruments = [
        (1, "2885"),  # Reliance
        (1, "1333"),  # HDFC Bank
        (1, "4963"),  # ICICI Bank
        (2, CURRENT_NIFTY_FUT_ID)
    ]

    sub_code = getattr(marketfeed, 'Ticker', 15)

    def on_connect(instance): ws_data["CONNECTED"] = True
    def on_disconnect(instance): ws_data["CONNECTED"] = False

    def on_message(instance, message):
        if isinstance(message, dict):
            sec_id = str(message.get('security_id', ''))
            ltp = float(message.get('LTP', 0.0))
            ltq = float(message.get('last_trade_quantity', 0.0))
            
            if ltp > 0:
                if sec_id == "2885": update_cvd("RELIANCE", ltp, ltq)
                elif sec_id == "1333": update_cvd("HDFCBANK", ltp, ltq)
                elif sec_id == "4963": update_cvd("ICICIBANK", ltp, ltq)
                elif sec_id == CURRENT_NIFTY_FUT_ID: ws_data["NIFTY_FUT_LTP"] = ltp

    def update_cvd(symbol, ltp, ltq):
        prev_ltp = ws_data[f"{symbol}_PREV"]
        if prev_ltp > 0:
            if ltp > prev_ltp: ws_data["CVD"] += ltq
            elif ltp < prev_ltp: ws_data["CVD"] -= ltq
        ws_data[f"{symbol}_LTP"] = ltp
        ws_data[f"{symbol}_PREV"] = ltp

    def run_ws():
        try:
            feed = marketfeed.DhanFeed(
                client_id, 
                access_token, 
                instruments, 
                sub_code, 
                on_connect=on_connect, 
                on_message=on_message
            )
            feed.run_forever()
        except Exception: pass

    t = threading.Thread(target=run_ws, daemon=True)
    t.start()
    return ws_data

live_ws_data = start_dhan_websocket(CLIENT_ID, ACCESS_TOKEN)


# ---------------------------------------------------------
# 3. BLACK-SCHOLES GREEK ENGINE (WITH SPEED/SPEX)
# ---------------------------------------------------------
def calculate_bs_greeks(S, K, T, sigma, r=0.07):
    if T <= 1e-5 or sigma <= 1e-4 or S <= 0 or K <= 0:
        return 0.0, 0.0, 0.0, 0.0
    try:
        d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        pdf_d1 = (1.0 / math.sqrt(2 * math.pi)) * math.exp(-0.5 * d1 * d1)
        gamma = pdf_d1 / (S * sigma * math.sqrt(T))
        vanna = -pdf_d1 * d2 / sigma
        charm = -pdf_d1 * (2 * r * math.sqrt(T) - d2 * sigma) / (2 * T * sigma)
        speed = -gamma / S * (1 + d1 / (sigma * math.sqrt(T)))
        return gamma, vanna, charm, speed
    except Exception:
        return 0.0, 0.0, 0.0, 0.0

# ---------------------------------------------------------
# 4. DIRECT REST API DATA ENGINE
# ---------------------------------------------------------
@st.cache_data(ttl=3)
def fetch_gex_option_chain(expiry_date):
    url = "https://api.dhan.co/v2/optionchain"
    headers = {"client-id": CLIENT_ID, "access-token": ACCESS_TOKEN, "Content-Type": "application/json"}
    payload = {"UnderlyingScrip": 13, "UnderlyingSeg": "IDX_I", "Expiry": expiry_date}

    try:
        res = requests.post(url, headers=headers, json=payload, timeout=10)
        data = res.json()
        if res.status_code == 200 and data.get("status") == "success":
            raw_data = data.get("data", {})
            spot_price = float(raw_data.get("last_price", 0.0))
            oc_raw = raw_data.get("oc", {})
            if not oc_raw: return None, spot_price, f"No contracts returned."

            T_years = max((datetime.datetime.strptime(expiry_date, "%Y-%m-%d").date() - datetime.date.today()).days, 1) / 365.0
            records = []
            for strike_str, details in oc_raw.items():
                strike = int(float(strike_str))
                ce, pe = details.get("ce", {}), details.get("pe", {})
                
                ce_oi, pe_oi = float(ce.get("oi", 0)), float(pe.get("oi", 0))
                ce_ltp, pe_ltp = float(ce.get("last_price", 0)), float(pe.get("last_price", 0))
                ce_iv, pe_iv = float(ce.get("implied_volatility", 0))/100.0, float(pe.get("implied_volatility", 0))/100.0
                ce_delta, pe_delta = float(ce.get("greeks", {}).get("delta", 0)), float(pe.get("greeks", {}).get("delta", 0))
                ce_gamma, pe_gamma = float(ce.get("greeks", {}).get("gamma", 0)), float(pe.get("greeks", {}).get("gamma", 0))

                if ce_gamma <= 0 and ce_iv > 0: ce_gamma, ce_vanna, ce_charm, ce_speed = calculate_bs_greeks(spot_price, strike, T_years, ce_iv)
                else: _, ce_vanna, ce_charm, ce_speed = calculate_bs_greeks(spot_price, strike, T_years, max(ce_iv, 0.15))

                if pe_gamma <= 0 and pe_iv > 0: pe_gamma, pe_vanna, pe_charm, pe_speed = calculate_bs_greeks(spot_price, strike, T_years, pe_iv)
                else: _, pe_vanna, pe_charm, pe_speed = calculate_bs_greeks(spot_price, strike, T_years, max(pe_iv, 0.15))

                call_gex = (ce_oi * ce_gamma * (spot_price**2) * 0.01 * NIFTY_LOT_SIZE / 1e5)
                put_gex = (-pe_oi * pe_gamma * (spot_price**2) * 0.01 * NIFTY_LOT_SIZE / 1e5)
                net_gex = call_gex + put_gex

                ce_delta_oi = ce_oi * ce_delta
                pe_delta_oi = pe_oi * pe_delta
                net_delta_oi = ce_delta_oi + pe_delta_oi
                net_dex = net_delta_oi * spot_price * NIFTY_LOT_SIZE / 1e5

                records.append({
                    "Strike": strike, "CE_LTP": ce_ltp, "PE_LTP": pe_ltp, "CE_OI": ce_oi, "PE_OI": pe_oi,
                    "CE_Delta": ce_delta, "PE_Delta": pe_delta, "Net_Delta_OI": net_delta_oi, "Net_DEX": net_dex,
                    "Call_GEX": call_gex, "Put_GEX": put_gex, "Net_GEX": net_gex, 
                    "Net_VEX": ((ce_oi * ce_vanna) - (pe_oi * pe_vanna)) * NIFTY_LOT_SIZE / 1e3, 
                    "Net_CHEX": ((ce_oi * ce_charm) - (pe_oi * pe_charm)) * NIFTY_LOT_SIZE / 1e3,
                    "Net_SPEX": ((ce_oi * ce_speed) - (pe_oi * pe_speed)) * NIFTY_LOT_SIZE / 1e3,
                    "CE_IV": ce_iv * 100.0, "PE_IV": pe_iv * 100.0, "IV_Spread": (ce_iv * 100.0) - (pe_iv * 100.0),
                })
            return pd.DataFrame(records).sort_values("Strike").reset_index(drop=True), spot_price, None
        else: return None, 0.0, str(data.get("remarks") or data.get("message") or f"HTTP {res.status_code}")
    except Exception as e: return None, 0.0, f"Connection Error: {str(e)}"

# ---------------------------------------------------------
# 5. MULTI-EXPIRY TERM STRUCTURE ENGINE (4 EXPIRIES)
# ---------------------------------------------------------
@st.cache_data(ttl=300)
def fetch_expiry_list_direct():
    url = "https://api.dhan.co/v2/optionchain/expirylist"
    headers = {"client-id": CLIENT_ID, "access-token": ACCESS_TOKEN, "Content-Type": "application/json"}
    try:
        res = requests.post(url, headers=headers, json={"UnderlyingScrip": 13, "UnderlyingSeg": "IDX_I"}, timeout=5)
        if res.status_code == 200 and res.json().get("status") == "success": return res.json().get("data", [])
    except: pass
    return []

@st.cache_data(ttl=120)
def fetch_multi_expiry_vol_structure(spot_price):
    expiries = fetch_expiry_list_direct()
    if not expiries:
        today = datetime.date.today()
        expiries = [(today + datetime.timedelta(days=i)).strftime("%Y-%m-%d") for i in range(1, 45) if (today + datetime.timedelta(days=i)).weekday() == 3][:4]
    else: expiries = expiries[:4]

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
# 6. CONTROLS, MEMORY INIT & LIVE SESSION LOGIC
# ---------------------------------------------------------
st.sidebar.header("⚙️ Command Center Controls")

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
if valid_expiries: selected_expiry = st.sidebar.selectbox("Primary Expiry", valid_expiries)
else:
    days_until_thursday = (3 - now_ist.weekday()) % 7
    default_expiry = (now_ist + datetime.timedelta(days=days_until_thursday)).strftime("%Y-%m-%d")
    selected_expiry = st.sidebar.date_input("Primary Expiry", datetime.datetime.strptime(default_expiry, "%Y-%m-%d")).strftime("%Y-%m-%d")

df_oc, spot_price, error_remark = fetch_gex_option_chain(selected_expiry)

# Global Synthetic Future Calculation
synthetic_future = spot_price
if df_oc is not None and not df_oc.empty:
    spot_atm = int(round(spot_price / 50) * 50)
    spot_row = df_oc[df_oc["Strike"] == spot_atm]
    if not spot_row.empty: synthetic_future = spot_atm + spot_row["CE_LTP"].values[0] - spot_row["PE_LTP"].values[0]
        
atm_strike = int(round(synthetic_future / 50) * 50)

selected_target_strike = None
if df_oc is not None and not df_oc.empty:
    all_strikes = df_oc["Strike"].tolist()
    default_index = all_strikes.index(atm_strike) if atm_strike in all_strikes else 0
    selected_target_strike = st.sidebar.selectbox("🎯 Target Strike", all_strikes, index=default_index)

# Data Memory Definitions (Parquet Backed)
REQUIRED_HIST_COLS = ["Date", "Time", "Strike", "CE_IV", "PE_IV", "IV_Spread", "Spot"]
REQUIRED_PCR_COLS = ["Date", "Timestamp_dt", "Time", "PCR", "Delta_PCR_5m", "Delta_PCR_15m"]
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
# 7. ENGINE PROCESSING LOGIC
# ---------------------------------------------------------
if error_remark:
    st.error(f"⚠️ **Dhan Server Error:** {error_remark}")
elif df_oc is not None and not df_oc.empty:
    
    strike_m50, strike_p50 = atm_strike - 50, atm_strike + 50
    
    # Cumulative Gamma Flip
    df_sorted = df_oc.sort_values("Strike").copy()
    df_sorted["Cum_Net_GEX"] = df_sorted["Net_GEX"].cumsum()
    gamma_flip_strike = int(spot_price)
    for i in range(1, len(df_sorted)):
        prev_val, curr_val = df_sorted.iloc[i - 1]["Cum_Net_GEX"], df_sorted.iloc[i]["Cum_Net_GEX"]
        if (prev_val < 0 and curr_val >= 0) or (prev_val > 0 and curr_val <= 0):
            gamma_flip_strike = int((df_sorted.iloc[i - 1]["Strike"] + df_sorted.iloc[i]["Strike"]) / 2.0)
            break

    # OPENBULL ALGO: MAX PAIN CALCULATION
    max_pain_strike = atm_strike
    df_pain = pd.DataFrame()
    pain_records = []
    # Calculate Max Pain strictly within reasonable range to save computation
    for k_eval in df_oc["Strike"]:
        if atm_strike - 1500 <= k_eval <= atm_strike + 1500:
            loss = (df_oc["CE_OI"] * (k_eval - df_oc["Strike"]).clip(lower=0)).sum() + (df_oc["PE_OI"] * (df_oc["Strike"] - k_eval).clip(lower=0)).sum()
            pain_records.append({"Strike": k_eval, "Writer_Loss": loss})
    if pain_records:
        df_pain = pd.DataFrame(pain_records)
        max_pain_strike = df_pain.loc[df_pain["Writer_Loss"].idxmin()]["Strike"]

    target_row = df_oc[df_oc["Strike"] == selected_target_strike]
    target_ce_iv = target_row["CE_IV"].values[0] if not target_row.empty else 0.0
    target_pe_iv = target_row["PE_IV"].values[0] if not target_row.empty else 0.0
    target_iv_spread = target_ce_iv - target_pe_iv

    df_filtered = df_oc[(df_oc["Strike"] >= atm_strike - 550) & (df_oc["Strike"] <= atm_strike + 550)].copy()
    strike_labels = df_filtered["Strike"].astype(str).tolist()

    total_net_gex = df_oc["Net_GEX"].sum()
    total_net_delta_oi = df_oc["Net_Delta_OI"].sum()
    total_net_dex_crores = df_oc["Net_DEX"].sum() / 100.0

    # ---------------------------------------------------------
    # SMART MEMORY RESET: Keep yesterday's data UNTIL exactly 09:15 AM
    # ---------------------------------------------------------
    if is_market_live:
        for hist_key in ["iv_spread_history", "pcr_history", "gex_history", "synth_history", "delta_oi_history", "straddle_history"]:
            h_df = st.session_state[hist_key]
            if not h_df.empty and h_df.iloc[-1].get("Date") != today_date_str:
                st.session_state[hist_key] = h_df.iloc[0:0] # Reset strictly at open
                if hist_key == "straddle_history": st.session_state["straddle_anchor_price"] = None

    # STRICT INTRADAY TICK RECORDING TO PARQUET (Only during live session)
    if is_market_live:
        
        # 1. IV Spread Memory
        hist_df = st.session_state["iv_spread_history"]
        if hist_df.empty or hist_df.iloc[-1]["Time"] != now_time_str:
            new_ticks = [{"Date": today_date_str, "Time": now_time_str, "Strike": int(r["Strike"]), "CE_IV": float(r["CE_IV"]), "PE_IV": float(r["PE_IV"]), "IV_Spread": float(r["IV_Spread"]), "Spot": spot_price} for _, r in df_filtered.iterrows()]
            st.session_state["iv_spread_history"] = pd.concat([hist_df, pd.DataFrame(new_ticks)], ignore_index=True)
            save_persisted_df(st.session_state["iv_spread_history"], "iv_spread_history")

        # 2. PCR Velocity Memory
        total_call_oi, total_put_oi = df_oc["CE_OI"].sum(), df_oc["PE_OI"].sum()
        current_pcr = total_put_oi / total_call_oi if total_call_oi > 0 else 0.0
        pcr_df = st.session_state["pcr_history"]
        delta_pcr_15m = 0.0
        if pcr_df.empty or pcr_df.iloc[-1]["Time"] != now_time_str:
            if not pcr_df.empty:
                past_15m = pcr_df[pcr_df["Timestamp_dt"] <= (now_ist - datetime.timedelta(minutes=15))]
                if not past_15m.empty: delta_pcr_15m = current_pcr - past_15m.iloc[-1]["PCR"]
            st.session_state["pcr_history"] = pd.concat([pcr_df, pd.DataFrame([{"Date": today_date_str, "Timestamp_dt": now_ist, "Time": now_time_str, "PCR": current_pcr, "Delta_PCR_5m": 0.0, "Delta_PCR_15m": delta_pcr_15m}])], ignore_index=True)
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

        # 4. Multi-Strike Synthetic Parity & PCP Discrepancy Index
        synth_df = st.session_state["synth_history"]
        row_m50, row_atm, row_p50 = df_oc[df_oc["Strike"] == strike_m50], df_oc[df_oc["Strike"] == atm_strike], df_oc[df_oc["Strike"] == strike_p50]
        s_m50 = strike_m50 + row_m50["CE_LTP"].values[0] - row_m50["PE_LTP"].values[0] if not row_m50.empty else spot_price
        s_atm = atm_strike + row_atm["CE_LTP"].values[0] - row_atm["PE_LTP"].values[0] if not row_atm.empty else spot_price
        s_p50 = strike_p50 + row_p50["CE_LTP"].values[0] - row_p50["PE_LTP"].values[0] if not row_p50.empty else spot_price
        pcp_dev_mean = ((s_m50 - spot_price) + (s_atm - spot_price) + (s_p50 - spot_price)) / 3.0
        
        if synth_df.empty or synth_df.iloc[-1]["Time"] != now_time_str:
            st.session_state["synth_history"] = pd.concat([synth_df, pd.DataFrame([{"Date": today_date_str, "Time": now_time_str, "Spot": spot_price, "Strike_M50": strike_m50, "Strike_ATM": atm_strike, "Strike_P50": strike_p50, "Synth_M50": s_m50, "Synth_ATM": s_atm, "Synth_P50": s_p50, "PCP_Dev_Mean": pcp_dev_mean}])], ignore_index=True)
            save_persisted_df(st.session_state["synth_history"], "synth_history")

        # 5. Real-Time Net Delta OI ROC & Dealer Delta Velocity
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

    total_call_oi, total_put_oi = df_oc["CE_OI"].sum(), df_oc["PE_OI"].sum()
    current_pcr = total_put_oi / total_call_oi if total_call_oi > 0 else 0.0
    delta_pcr_15m = pcr_df.iloc[-1]["Delta_PCR_15m"] if not pcr_df.empty else 0.0
    current_z_gex = gex_df.iloc[-1]["Z_GEX"] if not gex_df.empty else 0.0
    doi_roc_1m = doi_df.iloc[-1]["Delta_OI_ROC_1m"] if not doi_df.empty else 0.0
    
    current_straddle = strad_df.iloc[-1]["Actual_Straddle"] if not strad_df.empty else 0.0
    strad_regime = strad_df.iloc[-1]["Regime"] if not strad_df.empty else "NORMAL DECAY"

    row_m50, row_atm, row_p50 = df_oc[df_oc["Strike"] == strike_m50], df_oc[df_oc["Strike"] == atm_strike], df_oc[df_oc["Strike"] == strike_p50]
    synth_m50 = strike_m50 + row_m50["CE_LTP"].values[0] - row_m50["PE_LTP"].values[0] if not row_m50.empty else spot_price
    synth_atm = atm_strike + row_atm["CE_LTP"].values[0] - row_atm["PE_LTP"].values[0] if not row_atm.empty else spot_price
    synth_p50 = strike_p50 + row_p50["CE_LTP"].values[0] - row_p50["PE_LTP"].values[0] if not row_p50.empty else spot_price

    # Regime Interpretation Logics
    if current_z_gex < -2.0: z_signal, z_color, z_card_border = "GAMMA COLLAPSE", "sub-red", "metric-card-red"
    elif -1.0 <= current_z_gex <= 1.0: z_signal, z_color, z_card_border = "NORMAL DAMPENING", "sub-green", "metric-card-green"
    else: z_signal, z_color, z_card_border = "TRANSITION ZONE", "sub-amber", "metric-card-amber"

    if total_net_delta_oi > 50000: dir_signal, dir_color = "STRONGLY BULLISH", "sub-green"
    elif total_net_delta_oi > 10000: dir_signal, dir_color = "MILDLY BULLISH", "sub-green"
    elif total_net_delta_oi < -50000: dir_signal, dir_color = "STRONGLY BEARISH", "sub-red"
    elif total_net_delta_oi < -10000: dir_signal, dir_color = "MILDLY BEARISH", "sub-red"
    else: dir_signal, dir_color = "NEUTRAL / RANGEBOUND", "sub-amber"

    if (synth_m50 > spot_price + 1.0) and (synth_atm > spot_price + 1.0) and (synth_p50 > spot_price + 1.0):
        synth_flag_text, synth_flag_color = "🟢 BULL ACCUMULATION FLAG: Synthetics > Spot", "#00E676"
    elif (synth_m50 < spot_price - 1.0) and (synth_atm < spot_price - 1.0) and (synth_p50 < spot_price - 1.0):
        synth_flag_text, synth_flag_color = "🔴 BEAR DISTRIBUTION FLAG: Synthetics < Spot", "#FF5252"
    else: synth_flag_text, synth_flag_color = "⚪ NEUTRAL: Synthetic Parity Tracking Spot Closely", "#8A93A6"


    # ---------------------------------------------------------
    # 8. DASHBOARD UI (PRINCE PAX COMMAND CENTER)
    # ---------------------------------------------------------
    st.markdown(f"### PRINCE PAX DASHBOARD")
    status_class = "status-live" if is_market_live else "status-closed"
    status_text = "🟢 LIVE MARKET" if is_market_live else "🟠 MARKET CLOSED (Showing Last Session)"
    st.markdown(f'<div class="status-badge {status_class}">{status_text} | Expiry: {selected_expiry} | IST: {now_time_str}</div>', unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    # ================= ROW 1: TOP SUMMARY BANNER =================
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    
    with m1:
        st.markdown(f"""
            <div class="metric-card metric-card-amber">
                <div class="info-tooltip">ⓘ<span class="tooltip-text">Calculated Synthetic Future (K + C - P) for the selected expiry. All analytics dynamically center on this True Forward Price. Max Pain indicates institutional strike magnet.</span></div>
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
                <div class="info-tooltip">ⓘ<span class="tooltip-text"><b>IV Spread = Call IV - Put IV.</b><br>Rising values indicate institutional stealth accumulation of Calls. Falling values indicate accumulation of Puts.</span></div>
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
                <div class="info-tooltip">ⓘ<span class="tooltip-text"><b>Net Delta Exposure (Contracts).</b><br>A sharp drop (<-5000) signals short covering panic by Call writers.</span></div>
                <div class="metric-title">NET DELTA OI</div>
                <div class="metric-value">{total_net_delta_oi:+,.0f}</div>
                <div class="metric-sub {doi_color}">1m ROC: {doi_roc_1m:+,.0f}</div>
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
                <div class="info-tooltip">ⓘ<span class="tooltip-text"><b>Statistical Gamma Regime.</b><br>When Z-GEX drops below -2.0, dealer stabilizing power has mathematically collapsed. Prime regime for buying options and capturing multi-strike squeezes.</span></div>
                <div class="metric-title">Z-GEX SCORE</div>
                <div class="metric-value">{current_z_gex:+.2f}</div>
                <div class="metric-sub {z_color}">{z_signal}</div>
            </div>
        """, unsafe_allow_html=True)

    # ================= ROW 2: LIVE INTRADAY VELOCITY CHARTS =================
    r2_col1, r2_col2 = st.columns(2)

    with r2_col1:
        st.markdown(f'<div class="chart-container"><div class="info-tooltip">ⓘ<span class="tooltip-text">Tracks the exact tick-by-tick difference between Call IV and Put IV. Look for upward divergences (stealth call buying) before spot price breaks out.</span></div><div class="chart-title">Intraday IV Spread Movement ({selected_target_strike})</div>', unsafe_allow_html=True)
        fig_ts = go.Figure()
        strike_history = st.session_state["iv_spread_history"]
        strike_history = strike_history[strike_history["Strike"] == selected_target_strike]
        if not strike_history.empty:
            fig_ts.add_trace(go.Scatter(x=strike_history["Time"], y=strike_history["IV_Spread"], mode="lines+markers", line=dict(color="#29B6F6", width=2), marker=dict(size=3)))
        fig_ts.add_hline(y=0, line_dash="dash", line_color="white", opacity=0.3)
        fig_ts.update_xaxes(range=["09:15:00", "15:30:00"], dtick="3600000", gridcolor="#2A2E39")
        fig_ts.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=10, b=0), height=250)
        st.plotly_chart(fig_ts, use_container_width=True, key="chart_ts")
        st.markdown('</div>', unsafe_allow_html=True)

    with r2_col2:
        st.markdown('<div class="chart-container"><div class="info-tooltip">ⓘ<span class="tooltip-text">Measures the speed of option writing. Bars breaking above the green dashed line (+0.15) signal aggressive Put writing/Support. Bars breaking below the red dashed line (-0.15) signal aggressive Call writing/Resistance.</span></div><div class="chart-title">15-Min PCR Velocity (ΔPCR)</div>', unsafe_allow_html=True)
        fig_pcr = go.Figure()
        if not pcr_df.empty:
            colors = ["#00E676" if v >= 0.15 else ("#FF5252" if v <= -0.15 else "#8A93A6") for v in pcr_df["Delta_PCR_15m"]]
            fig_pcr.add_trace(go.Bar(x=pcr_df["Time"], y=pcr_df["Delta_PCR_15m"], marker_color=colors))
        fig_pcr.add_hline(y=0.15, line_dash="dash", line_color="#00E676")
        fig_pcr.add_hline(y=-0.15, line_dash="dash", line_color="#FF5252")
        fig_pcr.update_xaxes(range=["09:15:00", "15:30:00"], dtick="3600000", gridcolor="#2A2E39")
        fig_pcr.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=10, b=0), height=250)
        st.plotly_chart(fig_pcr, use_container_width=True, key="chart_pcr")
        st.markdown('</div>', unsafe_allow_html=True)

    # ================= ROW 3: NEW TOOLS (DELTA OI & DEX VELOCITY) =================
    r3_col1, r3_col2 = st.columns(2)

    with r3_col1:
        st.markdown(f'<div class="chart-container"><div class="info-tooltip">ⓘ<span class="tooltip-text">Tracks continuous Net Delta Weighted OI. Watch for severe drops near resistance—this flags short-covering panic (a squeeze).</span></div><div class="chart-title">Real-Time Delta-Weighted Net OI</div>', unsafe_allow_html=True)
        fig_doi = go.Figure()
        if not doi_df.empty:
            fig_doi.add_trace(go.Scatter(x=doi_df["Time"], y=doi_df["Total_Net_Delta_OI"], mode="lines", fill='tozeroy', line=dict(color="#00E676", width=2)))
        fig_doi.add_hline(y=0, line_dash="dash", line_color="white", opacity=0.3)
        fig_doi.update_xaxes(range=["09:15:00", "15:30:00"], dtick="3600000", gridcolor="#2A2E39")
        fig_doi.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=10, b=0), height=250)
        st.plotly_chart(fig_doi, use_container_width=True, key="chart_doi")
        st.markdown('</div>', unsafe_allow_html=True)

    with r3_col2:
        st.markdown('<div class="chart-container"><div class="info-tooltip">ⓘ<span class="tooltip-text">Measures the 5-Minute Rate of Change of Dealer Delta Exposure (DEX). Extreme bars indicate dealers are violently shifting hedges, signaling explosive spot momentum.</span></div><div class="chart-title">Dealer Delta Velocity (DEX 5m ROC)</div>', unsafe_allow_html=True)
        fig_dex_vel = go.Figure()
        if not doi_df.empty:
            colors_vel = ["#00E676" if v >= 0 else "#FF5252" for v in doi_df["DEX_Vel_5m"]]
            fig_dex_vel.add_trace(go.Bar(x=doi_df["Time"], y=doi_df["DEX_Vel_5m"], marker_color=colors_vel))
        fig_dex_vel.add_hline(y=0, line_dash="dash", line_color="white", opacity=0.3)
        fig_dex_vel.update_xaxes(range=["09:15:00", "15:30:00"], dtick="3600000", gridcolor="#2A2E39")
        fig_dex_vel.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=10, b=0), height=250)
        st.plotly_chart(fig_dex_vel, use_container_width=True, key="chart_dex_vel")
        st.markdown('</div>', unsafe_allow_html=True)

    # ================= ROW 4: STRADDLE DECAY & GAMMA FLIP MIGRATION =================
    r4_col1, r4_col2 = st.columns(2)

    with r4_col1:
        st.markdown('<div class="chart-container"><div class="info-tooltip">ⓘ<span class="tooltip-text">Compares actual ATM straddle premium against a theoretical Black-Scholes Theta decay model anchored at 09:20. If actual stays high, a "Vol Coil" (breakout) is pricing in.</span></div><div class="chart-title">Anchored ATM Straddle Decay vs Expected</div>', unsafe_allow_html=True)
        fig_strad = go.Figure()
        if not strad_df.empty:
            fig_strad.add_trace(go.Scatter(x=strad_df["Time"], y=strad_df["Actual_Straddle"], mode="lines", name="Actual", line=dict(color="#29B6F6", width=2.5)))
            fig_strad.add_trace(go.Scatter(x=strad_df["Time"], y=strad_df["Expected_Straddle"], mode="lines", name="Expected Decay", line=dict(color="#8A93A6", width=1.5, dash="dot")))
        fig_strad.update_xaxes(range=["09:15:00", "15:30:00"], dtick="3600000", gridcolor="#2A2E39")
        fig_strad.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=10, b=0), height=250, legend=dict(orientation="h", y=1.1))
        st.plotly_chart(fig_strad, use_container_width=True, key="chart_strad")
        st.markdown('</div>', unsafe_allow_html=True)

    with r4_col2:
        st.markdown('<div class="chart-container"><div class="info-tooltip">ⓘ<span class="tooltip-text">Tracks the structural movement of the Dealer Gamma Flip Level vs Spot. If the blue line drifts upward while Spot consolidates, dealer support is rising (Bullish).</span></div><div class="chart-title">Gamma Flip Migration (ΔFlip)</div>', unsafe_allow_html=True)
        fig_flip = go.Figure()
        if not gex_df.empty:
            fig_flip.add_trace(go.Scatter(x=gex_df["Time"], y=gex_df["Spot"], mode="lines", name="Spot", line=dict(color="#FFD700", width=2)))
            fig_flip.add_trace(go.Scatter(x=gex_df["Time"], y=gex_df["Flip_Strike"], mode="lines", name="Flip Level", line=dict(color="#29B6F6", width=2, dash="dash")))
        fig_flip.update_xaxes(range=["09:15:00", "15:30:00"], dtick="3600000", gridcolor="#2A2E39")
        fig_flip.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=10, b=0), height=250, legend=dict(orientation="h", y=1.1))
        st.plotly_chart(fig_flip, use_container_width=True, key="chart_flip_mig")
        st.markdown('</div>', unsafe_allow_html=True)

    # ================= ROW 5: PCP DEVIATION & SYNTHETIC ENGINE =================
    r5_col1, r5_col2 = st.columns(2)

    with r5_col1:
        st.markdown('<div class="chart-container"><div class="info-tooltip">ⓘ<span class="tooltip-text">Measures the mathematical discrepancy between Theoretical Put-Call Parity and real options pricing. Readings above +3.0 imply massive, aggressive institutional Call buying ahead of a spot move.</span></div><div class="chart-title">Put-Call Parity Discrepancy Index (PCP_Dev)</div>', unsafe_allow_html=True)
        fig_pcp = go.Figure()
        if not synth_df.empty:
            colors_pcp = ["#00E676" if v > 0 else "#FF5252" for v in synth_df["PCP_Dev_Mean"]]
            fig_pcp.add_trace(go.Bar(x=synth_df["Time"], y=synth_df["PCP_Dev_Mean"], marker_color=colors_pcp))
        fig_pcp.add_hline(y=3.0, line_dash="dash", line_color="#00E676", annotation_text="+3.0 Call Squeeze")
        fig_pcp.add_hline(y=-3.0, line_dash="dash", line_color="#FF5252", annotation_text="-3.0 Put Squeeze")
        fig_pcp.update_xaxes(range=["09:15:00", "15:30:00"], dtick="3600000", gridcolor="#2A2E39")
        fig_pcp.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=10, b=0), height=265)
        st.plotly_chart(fig_pcp, use_container_width=True, key="chart_pcp")
        st.markdown('</div>', unsafe_allow_html=True)

    with r5_col2:
        st.markdown('<div class="chart-container"><div class="info-tooltip">ⓘ<span class="tooltip-text"><b>Multi-Strike Synthetic Parity Engine.</b><br>Tracks the implied spot price derived from options premiums (K + C - P). If Synthetics break out while Spot consolidates, it signals institutional stealth accumulation.</span></div><div class="chart-title">Multi-Strike Synthetic Parity Engine</div>', unsafe_allow_html=True)
        st.markdown(f"**Signal:** <span style='color: {synth_flag_color};'>{synth_flag_text}</span>", unsafe_allow_html=True)
        fig_synth = go.Figure()
        if not synth_df.empty:
            fig_synth.add_trace(go.Scatter(x=synth_df["Time"], y=synth_df["Spot"], mode="lines", name="Spot", line=dict(color="#FFD700", width=2)))
            fig_synth.add_trace(go.Scatter(x=synth_df["Time"], y=synth_df["Synth_M50"], mode="lines", name="ITM Synth", line=dict(color="#00E676", width=1.5, dash="dot")))
            fig_synth.add_trace(go.Scatter(x=synth_df["Time"], y=synth_df["Synth_ATM"], mode="lines", name="ATM Synth", line=dict(color="#29B6F6", width=1.5, dash="dot")))
            fig_synth.add_trace(go.Scatter(x=synth_df["Time"], y=synth_df["Synth_P50"], mode="lines", name="OTM Synth", line=dict(color="#FF5252", width=1.5, dash="dot")))
        fig_synth.update_xaxes(range=["09:15:00", "15:30:00"], dtick="3600000", gridcolor="#2A2E39")
        fig_synth.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=10, b=0), height=230, legend=dict(orientation="h", y=1.1))
        st.plotly_chart(fig_synth, use_container_width=True, key="chart_synth_par")
        st.markdown('</div>', unsafe_allow_html=True)

    # ================= ROW 6: EXPOSURE PROFILES (DEX & GEX ADJACENT) =================
    r6_col1, r6_col2 = st.columns(2)

    with r6_col1:
        st.markdown('<div class="chart-container"><div class="info-tooltip">ⓘ<span class="tooltip-text">Total Rupee Value of Delta per strike. Visualizes where directional bias is heavily concentrated and where dealer hedging flows are trapped. Includes the current Spot line.</span></div><div class="chart-title">Net Delta Exposure (DEX) By Strike</div>', unsafe_allow_html=True)
        fig_dex = go.Figure()
        colors_dex = ["#00E676" if val >= 0 else "#FF5252" for val in df_filtered["Net_DEX"]]
        fig_dex.add_trace(go.Bar(x=df_filtered["Strike"], y=df_filtered["Net_DEX"], marker_color=colors_dex))
        fig_dex.add_vline(x=spot_price, line_dash="solid", line_color="#FFD700")
        fig_dex.add_annotation(x=spot_price, y=0.95, yref="paper", text="Spot", showarrow=False, font=dict(color="#FFD700", size=10), xanchor="left")
        fig_dex.update_xaxes(range=[atm_strike - 550, atm_strike + 550], tickmode='array', tickvals=df_filtered["Strike"], ticktext=strike_labels, tickangle=-45, gridcolor="#2A2E39")
        fig_dex.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=10, b=0), height=250)
        st.plotly_chart(fig_dex, use_container_width=True, key="chart_dex")
        st.markdown('</div>', unsafe_allow_html=True)

    with r6_col2:
        st.markdown('<div class="chart-container"><div class="info-tooltip">ⓘ<span class="tooltip-text">Identifies Resistance (Call Walls - Red) and Support (Put Walls - Green). Yellow line marks the Spot Price, Blue dashed line marks the Gamma Flip Level (Zero-crossing).</span></div><div class="chart-title">Net GEX Profile</div>', unsafe_allow_html=True)
        fig_gex = go.Figure()
        colors_gex = ["#00E676" if g >= 0 else "#FF5252" for g in df_filtered["Net_GEX"]]
        fig_gex.add_trace(go.Bar(x=df_filtered["Strike"], y=df_filtered["Net_GEX"], marker_color=colors_gex))
        fig_gex.add_vline(x=spot_price, line_dash="solid", line_color="#FFD700")
        fig_gex.add_annotation(x=spot_price, y=0.95, yref="paper", text="Spot", showarrow=False, font=dict(color="#FFD700", size=10), xanchor="left")
        fig_gex.add_vline(x=gamma_flip_strike, line_dash="dash", line_color="#29B6F6")
        fig_gex.add_annotation(x=gamma_flip_strike, y=0.85, yref="paper", text="Flip", showarrow=False, font=dict(color="#29B6F6", size=10), xanchor="left")
        fig_gex.update_xaxes(range=[atm_strike - 550, atm_strike + 550], tickmode='array', tickvals=df_filtered["Strike"], ticktext=strike_labels, tickangle=-45, gridcolor="#2A2E39")
        fig_gex.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=10, b=0), height=250, showlegend=False)
        st.plotly_chart(fig_gex, use_container_width=True, key="chart_gex_profile")
        st.markdown('</div>', unsafe_allow_html=True)

    # ================= ROW 7: Z-GEX & SPEX (SPEED) =================
    r7_col1, r7_col2 = st.columns(2)

    with r7_col1:
        st.markdown('<div class="chart-container"><div class="info-tooltip">ⓘ<span class="tooltip-text">Isolates structural regime shifts by comparing current GEX to its rolling mean. Watch for lines dipping below -2.0, which confirms a total regime collapse where dealers are forced to violently buy rips and sell dips.</span></div><div class="chart-title">Normalized Gamma Z-Score (ZGEX) Tracker</div>', unsafe_allow_html=True)
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
        st.markdown('<div class="chart-container"><div class="info-tooltip">ⓘ<span class="tooltip-text">Speed (Rate of Change of Gamma w.r.t Spot). Shows exact strike clusters that will trigger maximum acceleration during 0DTE expiry squeezes.</span></div><div class="chart-title">Expiry Day Speed Exposure (SPEX)</div>', unsafe_allow_html=True)
        fig_spex = go.Figure()
        colors_spex = ["#00E676" if g >= 0 else "#FF5252" for g in df_filtered["Net_SPEX"]]
        fig_spex.add_trace(go.Bar(x=df_filtered["Strike"], y=df_filtered["Net_SPEX"], marker_color=colors_spex))
        fig_spex.update_xaxes(range=[atm_strike - 550, atm_strike + 550], tickmode='array', tickvals=df_filtered["Strike"], ticktext=strike_labels, tickangle=-45, gridcolor="#2A2E39")
        fig_spex.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=10, b=0), height=250, showlegend=False)
        st.plotly_chart(fig_spex, use_container_width=True, key="chart_spex")
        st.markdown('</div>', unsafe_allow_html=True)

    # ================= ROW 8: VANNA & CHARM =================
    r8_col1, r8_col2 = st.columns(2)

    with r8_col1:
        st.markdown('<div class="chart-container"><div class="info-tooltip">ⓘ<span class="tooltip-text">Sensitivity of Dealer Delta to changes in Implied Volatility. Strikes with massive Vanna peaks act as strong price magnets during high-volatility shifts or news events.</span></div><div class="chart-title">Vanna Exposure (VEX)</div>', unsafe_allow_html=True)
        fig_vex = go.Figure()
        fig_vex.add_trace(go.Scatter(x=df_filtered["Strike"], y=df_filtered["Net_VEX"], mode="lines+markers", line=dict(color="#FFA726", width=2)))
        fig_vex.update_xaxes(range=[atm_strike - 550, atm_strike + 550], tickmode='array', tickvals=df_filtered["Strike"], ticktext=strike_labels, tickangle=-45, gridcolor="#2A2E39")
        fig_vex.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=10, b=0), height=240)
        st.plotly_chart(fig_vex, use_container_width=True, key="chart_vex")
        st.markdown('</div>', unsafe_allow_html=True)

    with r8_col2:
        st.markdown('<div class="chart-container"><div class="info-tooltip">ⓘ<span class="tooltip-text">Dealer Delta adjustments driven entirely by the passage of time (Theta bleed). CHEX dictates where dealers must buy/sell to remain hedged as the clock approaches 3:30 PM.</span></div><div class="chart-title">Charm Exposure (CHEX)</div>', unsafe_allow_html=True)
        fig_chex = go.Figure()
        fig_chex.add_trace(go.Scatter(x=df_filtered["Strike"], y=df_filtered["Net_CHEX"], mode="lines+markers", line=dict(color="#AB47BC", width=2)))
        fig_chex.update_xaxes(range=[atm_strike - 550, atm_strike + 550], tickmode='array', tickvals=df_filtered["Strike"], ticktext=strike_labels, tickangle=-45, gridcolor="#2A2E39")
        fig_chex.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=10, b=0), height=240)
        st.plotly_chart(fig_chex, use_container_width=True, key="chart_chex")
        st.markdown('</div>', unsafe_allow_html=True)

    # ================= ROW 9: VOLATILITY TERM STRUCTURE =================
    r9_col1, r9_col2 = st.columns(2)
    df_vol_struct = fetch_multi_expiry_vol_structure(spot_price)

    with r9_col1:
        st.markdown('<div class="chart-container"><div class="info-tooltip">ⓘ<span class="tooltip-text">Plots implied forward variance. Normal markets exhibit an upward slope (Contango). A downward slope (Backwardation) flags near-term fear and extreme panic pricing in front-month options.</span></div><div class="chart-title">Forward Vol Term Structure (4 Expiries)</div>', unsafe_allow_html=True)
        if not df_vol_struct.empty and len(df_vol_struct) >= 2:
            fig_fwd = go.Figure()
            fig_fwd.add_trace(go.Scatter(x=df_vol_struct["Expiry"], y=df_vol_struct["Forward_Vol"], mode="lines+markers", line=dict(color="#00E676", width=2.5), marker=dict(size=8)))
            fig_fwd.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=10, b=0), height=220)
            st.plotly_chart(fig_fwd, use_container_width=True, key="chart_fwd_vol")
        else:
            st.info("Loading 4 expiries to build term structure... (Takes ~5 seconds due to API limits)")
        st.markdown('</div>', unsafe_allow_html=True)

    with r9_col2:
        st.markdown('<div class="chart-container"><div class="info-tooltip">ⓘ<span class="tooltip-text">Displays the raw ATM Average Implied Volatility plotted across the upcoming 4 valid expiry dates.</span></div><div class="chart-title">Cumulative Mean Volatility Curve</div>', unsafe_allow_html=True)
        if not df_vol_struct.empty and len(df_vol_struct) >= 2:
            fig_vol_curve = go.Figure()
            fig_vol_curve.add_trace(go.Scatter(x=df_vol_struct["Expiry"], y=df_vol_struct["Mean_IV"], mode="lines+markers", line=dict(color="#AB47BC", width=2.5), marker=dict(size=8)))
            fig_vol_curve.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=10, b=0), height=220)
            st.plotly_chart(fig_vol_curve, use_container_width=True, key="chart_cum_vol")
        else:
            st.info("Loading 4 expiries to build vol curve... (Takes ~5 seconds due to API limits)")
        st.markdown('</div>', unsafe_allow_html=True)

    # ================= ROW 10: OPENBULL OPTIONS ANALYTICS (IV SMILE & MAX PAIN) =================
    r10_col1, r10_col2 = st.columns(2)
    
    with r10_col1:
        st.markdown('<div class="chart-container"><div class="info-tooltip">ⓘ<span class="tooltip-text"><b>IV Smile (Volatility Skew):</b> Shows Call vs Put Implied Volatility across strikes. An asymmetric smile indicates institutional demand for specific OTM protections (skew).</span></div><div class="chart-title">IV Smile (Volatility Skew Profile)</div>', unsafe_allow_html=True)
        fig_smile = go.Figure()
        fig_smile.add_trace(go.Scatter(x=df_filtered["Strike"], y=df_filtered["CE_IV"], mode="lines+markers", name="Call IV", line=dict(color="#00E676", width=2)))
        fig_smile.add_trace(go.Scatter(x=df_filtered["Strike"], y=df_filtered["PE_IV"], mode="lines+markers", name="Put IV", line=dict(color="#FF5252", width=2)))
        fig_smile.add_vline(x=spot_price, line_dash="solid", line_color="#FFD700")
        fig_smile.add_annotation(x=spot_price, y=0.95, yref="paper", text="Spot", showarrow=False, font=dict(color="#FFD700", size=10), xanchor="left")
        fig_smile.update_xaxes(range=[atm_strike - 550, atm_strike + 550], tickmode='array', tickvals=df_filtered["Strike"], ticktext=strike_labels, tickangle=-45, gridcolor="#2A2E39")
        fig_smile.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=10, b=0), height=250, legend=dict(orientation="h", y=1.1))
        st.plotly_chart(fig_smile, use_container_width=True, key="chart_iv_smile")
        st.markdown('</div>', unsafe_allow_html=True)

    with r10_col2:
        st.markdown('<div class="chart-container"><div class="info-tooltip">ⓘ<span class="tooltip-text"><b>Max Pain Point:</b> The strike price where option buyers suffer the most intrinsic loss. Serves as a massive institutional magnetic pin on expiry day.</span></div><div class="chart-title">Max Pain Pinning Profile</div>', unsafe_allow_html=True)
        fig_pain = go.Figure()
        if not df_pain.empty:
            fig_pain.add_trace(go.Bar(x=df_pain["Strike"], y=df_pain["Writer_Loss"], marker_color="#8A93A6", name="Option Writer Loss"))
            fig_pain.add_vline(x=spot_price, line_dash="solid", line_color="#FFD700")
            fig_pain.add_annotation(x=spot_price, y=0.95, yref="paper", text="Spot", showarrow=False, font=dict(color="#FFD700", size=10), xanchor="left")
            fig_pain.add_vline(x=max_pain_strike, line_dash="dash", line_color="#29B6F6")
            fig_pain.add_annotation(x=max_pain_strike, y=0.85, yref="paper", text=f"Max Pain: {max_pain_strike}", showarrow=False, font=dict(color="#29B6F6", size=10), xanchor="left")
        fig_pain.update_xaxes(range=[atm_strike - 550, atm_strike + 550], tickmode='array', tickvals=df_filtered["Strike"], ticktext=strike_labels, tickangle=-45, gridcolor="#2A2E39")
        fig_pain.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=10, b=0), height=250)
        st.plotly_chart(fig_pain, use_container_width=True, key="chart_max_pain")
        st.markdown('</div>', unsafe_allow_html=True)

    # ================= ROW 11: WEBSOCKET HEAVYWEIGHT BASKET =================
    st.markdown('<div class="chart-container"><div class="info-tooltip">ⓘ<span class="tooltip-text">Tracks the Basis (Futures - Spot) and the Cumulative Volume Delta of top index heavyweights via WebSocket. Validates the structural strength of breakouts.</span></div><div class="chart-title">Futures Basis & Heavyweight CVD Filter (Live WebSocket)</div>', unsafe_allow_html=True)
    
    nifty_fut = live_ws_data.get("NIFTY_FUT_LTP", 0.0)
    basis = nifty_fut - spot_price if nifty_fut > 0 else 0.0
    basis_color = "sub-green" if basis >= 0 else "sub-red"
    cvd_val = live_ws_data.get("CVD", 0.0)
    cvd_color = "sub-green" if cvd_val >= 0 else "sub-red"
    
    c_hw1, c_hw2, c_hw3, c_hw4 = st.columns(4)
    
    with c_hw1:
        st.metric("Live Nifty Futures", f"₹{nifty_fut:,.2f}" if nifty_fut > 0 else "Awaiting Tick...")
    with c_hw2:
        st.markdown(f"""
            <div>
                <div style="color: #8A93A6; font-size: 0.85rem; font-weight: 600;">FUTURES BASIS</div>
                <div style="font-size: 1.5rem; font-weight: 700; margin-top: 5px;" class="{basis_color}">{basis:+.2f} Pts</div>
            </div>
        """, unsafe_allow_html=True)
    with c_hw3:
        st.markdown(f"""
            <div>
                <div style="color: #8A93A6; font-size: 0.85rem; font-weight: 600;">HEAVYWEIGHT NET CVD</div>
                <div style="font-size: 1.5rem; font-weight: 700; margin-top: 5px;" class="{cvd_color}">{cvd_val:+,.0f} Vol</div>
            </div>
        """, unsafe_allow_html=True)
    with c_hw4:
        conn_status = "🟢 ACTIVE" if live_ws_data.get("CONNECTED") else f"🔴 {live_ws_data.get('ERROR', 'RECONNECTING...')}"
        st.markdown(f"""
            <div>
                <div style="color: #8A93A6; font-size: 0.85rem; font-weight: 600;">DAEMON STATUS</div>
                <div style="font-size: 1.1rem; font-weight: 700; margin-top: 5px;">{conn_status}</div>
            </div>
        """, unsafe_allow_html=True)
        
    st.markdown('</div>', unsafe_allow_html=True)

    # ================= ROW 12: INSTITUTIONAL PLAYBOOK EXPANDER =================
    with st.expander("📖 Institutional Playbook: How to Trade Nifty Using Relative Option Demand", expanded=False):
        st.markdown("""
            Monitoring the **ATM IV Spread (IV_Call - IV_Put)** provides major advantages for intraday buyers:
            
            **1. Spotting Pre-Breakout Accumulation**
            *   **Context:** Spot Nifty is stuck in a narrow range.
            *   **Signal:** The ATM IV Spread trends upward steadily over a 15–30 min period.
            *   **Interpretation:** Institutions are quietly accumulating Calls ahead of a move. Buy ATM Calls before Delta and Vega expansion hit.

            **2. Identifying "Fakeout" Breakouts**
            *   **Context:** Nifty breaks above an intraday resistance level.
            *   **Signal:** Call IV drops rapidly as spot pushes higher (IV Spread turns sharply negative).
            *   **Interpretation:** Market makers are dumping Call inventory into retail buyers. The move lacks backing. Avoid Calls; prepare for mean-reversion.

            **3. Trend Continuation Confirmation**
            *   **Context:** Nifty is trending upward.
            *   **Signal:** Call IV continues to rise alongside Spot Nifty (defying normal inverse volatility behavior).
            *   **Interpretation:** High-conviction buying sweeps the asks. Hold long calls for larger multi-strike targets.
        """)
        st.markdown("""
            <div class="summary-box" style="margin-top: 15px;">
                <div class="summary-title" style="color: #FFA726;">Interpreting Intraday Signals (Summary Matrix)</div>
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

    # ================= ROW 13: DATA GRID =================
    st.markdown('<div class="chart-container"><div class="chart-title">Institutional Options Chain Grid</div>', unsafe_allow_html=True)
    grid_df = df_filtered[["Strike", "CE_LTP", "PE_LTP", "CE_OI", "PE_OI", "CE_Delta", "PE_Delta", "Net_Delta_OI", "Net_DEX", "Net_GEX", "Net_VEX", "Net_CHEX", "Net_SPEX", "CE_IV", "PE_IV", "IV_Spread"]].copy()
    st.dataframe(
        grid_df.style.format({
            "Strike": "{:.0f}", "CE_LTP": "₹{:.2f}", "PE_LTP": "₹{:.2f}", "CE_OI": "{:,.0f}", "PE_OI": "{:,.0f}", 
            "CE_Delta": "{:.2f}", "PE_Delta": "{:.2f}", "Net_Delta_OI": "{:+,.0f}", "Net_DEX": "{:+,.1f}L", 
            "Net_GEX": "{:+,.1f}L", "Net_VEX": "{:+,.2f}", "Net_CHEX": "{:+,.2f}", "Net_SPEX": "{:+,.2f}", 
            "CE_IV": "{:.1f}%", "PE_IV": "{:.1f}%", "IV_Spread": "{:+.2f}%"
        }),
        use_container_width=True, height=350
    )
    st.markdown('</div>', unsafe_allow_html=True)
