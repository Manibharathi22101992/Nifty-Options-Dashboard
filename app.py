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
    
    /* Streamlit Tabs Styling */
    div[data-testid="stTabs"] button {
        color: #8A93A6; font-weight: 600; font-size: 0.9rem;
    }
    div[data-testid="stTabs"] button[aria-selected="true"] {
        color: #29B6F6; border-bottom-color: #29B6F6;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------
# 2. CONFIGURATION & HELPERS
# ---------------------------------------------------------
CLIENT_ID = str(st.secrets.get("DHAN_CLIENT_ID", "")).strip().replace('"', "").replace("'", "")
ACCESS_TOKEN = str(st.secrets.get("DHAN_ACCESS_TOKEN", "")).strip().replace('"', "").replace("'", "")

if not CLIENT_ID or not ACCESS_TOKEN:
    st.error("⚠️ API credentials missing. Please update your Streamlit Secrets.")
    st.stop()

NIFTY_LOT_SIZE = 25

def apply_dark_layout(fig, height=250):
    """Centralized Plotly layout engine for consistent UI spacing and colors."""
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=5, r=5, t=10, b=5),
        height=height,
        legend=dict(orientation="h", y=1.1, x=0, font=dict(size=10))
    )
    fig.update_xaxes(gridcolor="#2A2E39", zerolinecolor="#2A2E39", tickfont=dict(size=10))
    fig.update_yaxes(gridcolor="#2A2E39", zerolinecolor="#2A2E39", tickfont=dict(size=10))
    return fig

def create_h_bar(title, put_val, call_val):
    """Creates horizontal comparative bars matching OpenBull aesthetics"""
    fig = go.Figure()
    fig.add_trace(go.Bar(x=[put_val], y=[''], name='Put', orientation='h', marker_color="#29B6F6", text=f"{put_val:,.0f}", textposition='inside', insidetextanchor='end'))
    fig.add_trace(go.Bar(x=[call_val], y=[''], name='Call', orientation='h', marker_color="#FF5252", text=f"{call_val:,.0f}", textposition='inside', insidetextanchor='start'))
    fig.update_layout(
        title=dict(text=title, font=dict(size=11, color="#8A93A6"), x=0.5, xanchor='center'),
        barmode='group',
        margin=dict(l=0, r=0, t=25, b=0),
        height=75,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        xaxis=dict(visible=False), yaxis=dict(visible=False),
        bargap=0.2
    )
    return fig

# ---------------------------------------------------------
# 3. LOCAL PARQUET PERSISTENCE & WEBSOCKET DAEMON
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
        "RELIANCE_LTP": 0.0, "RELIANCE_PREV": 0.0, "HDFCBANK_LTP": 0.0, "HDFCBANK_PREV": 0.0,
        "ICICIBANK_LTP": 0.0, "ICICIBANK_PREV": 0.0, "NIFTY_FUT_LTP": 0.0, "CVD": 0.0, "CONNECTED": False
    }

    if not DHAN_WS_AVAILABLE:
        ws_data["ERROR"] = "dhanhq not installed"
        return ws_data

    CURRENT_NIFTY_FUT_ID = "58756" # Update monthly
    instruments = [(1, "2885"), (1, "1333"), (1, "4963"), (2, CURRENT_NIFTY_FUT_ID)]
    sub_code = getattr(marketfeed, 'Ticker', 15)

    def on_connect(instance): ws_data["CONNECTED"] = True
    def on_disconnect(instance): ws_data["CONNECTED"] = False

    def on_message(instance, message):
        if isinstance(message, dict):
            sec_id, ltp = str(message.get('security_id', '')), float(message.get('LTP', 0.0))
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
            feed = marketfeed.DhanFeed(client_id, access_token, instruments, sub_code, on_connect=on_connect, on_message=on_message)
            feed.run_forever()
        except Exception: pass

    threading.Thread(target=run_ws, daemon=True).start()
    return ws_data

live_ws_data = start_dhan_websocket(CLIENT_ID, ACCESS_TOKEN)

# ---------------------------------------------------------
# 4. BLACK-SCHOLES GREEK ENGINE
# ---------------------------------------------------------
def calculate_bs_greeks(S, K, T, sigma, r=0.07):
    if T <= 1e-5 or sigma <= 1e-4 or S <= 0 or K <= 0: return 0.0, 0.0, 0.0, 0.0
    try:
        d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        pdf_d1 = (1.0 / math.sqrt(2 * math.pi)) * math.exp(-0.5 * d1 * d1)
        gamma = pdf_d1 / (S * sigma * math.sqrt(T))
        vanna = -pdf_d1 * d2 / sigma
        charm = -pdf_d1 * (2 * r * math.sqrt(T) - d2 * sigma) / (2 * T * sigma)
        speed = -gamma / S * (1 + d1 / (sigma * math.sqrt(T)))
        return gamma, vanna, charm, speed
    except Exception: return 0.0, 0.0, 0.0, 0.0

# ---------------------------------------------------------
# 5. DATA API ENGINE
# ---------------------------------------------------------
@st.cache_data(ttl=3)
def fetch_gex_option_chain(expiry_date):
    url = "https://api.dhan.co/v2/optionchain"
    headers = {"client-id": CLIENT_ID, "access-token": ACCESS_TOKEN, "Content-Type": "application/json"}
    try:
        res = requests.post(url, headers=headers, json={"UnderlyingScrip": 13, "UnderlyingSeg": "IDX_I", "Expiry": expiry_date}, timeout=10)
        data = res.json()
        if res.status_code == 200 and data.get("status") == "success":
            spot_price = float(data.get("data", {}).get("last_price", 0.0))
            oc_raw = data.get("data", {}).get("oc", {})
            if not oc_raw: return None, spot_price, f"No contracts returned."

            T_years = max((datetime.datetime.strptime(expiry_date, "%Y-%m-%d").date() - datetime.date.today()).days, 1) / 365.0
            records = []
            for strike_str, details in oc_raw.items():
                strike = int(float(strike_str))
                ce, pe = details.get("ce", {}), details.get("pe", {})
                
                ce_oi, pe_oi = float(ce.get("oi", 0)), float(pe.get("oi", 0))
                ce_oichg = float(ce.get("oi_change", ce.get("change_in_oi", 0)))
                pe_oichg = float(pe.get("oi_change", pe.get("change_in_oi", 0)))
                ce_vol, pe_vol = float(ce.get("volume") or 0.0), float(pe.get("volume") or 0.0)
                ce_ltp, pe_ltp = float(ce.get("last_price", 0)), float(pe.get("last_price", 0))
                ce_iv, pe_iv = float(ce.get("implied_volatility", 0))/100.0, float(pe.get("implied_volatility", 0))/100.0
                ce_delta, pe_delta = float(ce.get("greeks", {}).get("delta", 0)), float(pe.get("greeks", {}).get("delta", 0))
                ce_gamma, pe_gamma = float(ce.get("greeks", {}).get("gamma", 0)), float(pe.get("greeks", {}).get("gamma", 0))

                ce_gamma, ce_vanna, ce_charm, ce_speed = calculate_bs_greeks(spot_price, strike, T_years, ce_iv if ce_gamma <= 0 and ce_iv > 0 else max(ce_iv, 0.15))
                pe_gamma, pe_vanna, pe_charm, pe_speed = calculate_bs_greeks(spot_price, strike, T_years, pe_iv if pe_gamma <= 0 and pe_iv > 0 else max(pe_iv, 0.15))

                call_gex = (ce_oi * ce_gamma * (spot_price**2) * 0.01 * NIFTY_LOT_SIZE / 1e5)
                put_gex = (-pe_oi * pe_gamma * (spot_price**2) * 0.01 * NIFTY_LOT_SIZE / 1e5)
                ce_dex = ce_oi * ce_delta * spot_price * NIFTY_LOT_SIZE / 1e5
                pe_dex = pe_oi * pe_delta * spot_price * NIFTY_LOT_SIZE / 1e5
                
                ce_vex = ce_oi * ce_vanna * NIFTY_LOT_SIZE / 1e3
                pe_vex = pe_oi * pe_vanna * NIFTY_LOT_SIZE / 1e3
                ce_chex = ce_oi * ce_charm * NIFTY_LOT_SIZE / 1e3
                pe_chex = pe_oi * pe_charm * NIFTY_LOT_SIZE / 1e3

                records.append({
                    "Strike": strike, "CE_LTP": ce_ltp, "PE_LTP": pe_ltp, 
                    "CE_OI": ce_oi, "PE_OI": pe_oi, "CE_OI_Chg": ce_oichg, "PE_OI_Chg": pe_oichg,
                    "CE_Vol": ce_vol, "PE_Vol": pe_vol,
                    "CE_Delta": ce_delta, "PE_Delta": pe_delta, "Net_Delta_OI": (ce_oi * ce_delta) + (pe_oi * pe_delta),
                    "Net_DEX": ce_dex + pe_dex, "ABS_DEX": ce_dex + abs(pe_dex),
                    "Call_GEX": call_gex, "Put_GEX": put_gex, "Net_GEX": call_gex + put_gex, "ABS_GEX": call_gex + abs(put_gex),
                    "CE_VEX": ce_vex, "PE_VEX": pe_vex, "Net_VEX": ce_vex - pe_vex, 
                    "CE_CHEX": ce_chex, "PE_CHEX": pe_chex, "Net_CHEX": ce_chex - pe_chex,
                    "Net_SPEX": ((ce_oi * ce_speed) - (pe_oi * pe_speed)) * NIFTY_LOT_SIZE / 1e3,
                    "CE_IV": ce_iv * 100.0, "PE_IV": pe_iv * 100.0, "IV_Spread": (ce_iv * 100.0) - (pe_iv * 100.0),
                })
            return pd.DataFrame(records).sort_values("Strike").reset_index(drop=True), spot_price, None
        else: return None, 0.0, str(data.get("remarks") or data.get("message") or f"HTTP {res.status_code}")
    except Exception as e: return None, 0.0, f"Connection Error: {str(e)}"

@st.cache_data(ttl=120)
def fetch_multi_expiry_vol_structure(spot_price):
    try:
        res = requests.post("https://api.dhan.co/v2/optionchain/expirylist", headers={"client-id": CLIENT_ID, "access-token": ACCESS_TOKEN, "Content-Type": "application/json"}, json={"UnderlyingScrip": 13, "UnderlyingSeg": "IDX_I"}, timeout=5)
        expiries = res.json().get("data", [])[:4] if res.status_code == 200 else []
    except: expiries = []

    vol_data, surface_data = [], []
    for idx, exp in enumerate(expiries):
        if idx > 0: time.sleep(1.2)
        df_exp, exp_spot, _ = fetch_gex_option_chain(exp)
        if df_exp is not None and not df_exp.empty:
            temp_spot_atm = int(round(exp_spot / 50) * 50)
            temp_row = df_exp[df_exp["Strike"] == temp_spot_atm]
            exp_synth = temp_spot_atm + temp_row["CE_LTP"].values[0] - temp_row["PE_LTP"].values[0] if not temp_row.empty else exp_spot
            exp_atm = int(round(exp_synth / 50) * 50)
            
            atm_row = df_exp[df_exp["Strike"] == exp_atm]
            mean_iv = ( (atm_row["CE_IV"].values[0] if not atm_row.empty else df_exp["CE_IV"].mean()) + (atm_row["PE_IV"].values[0] if not atm_row.empty else df_exp["PE_IV"].mean()) ) / 2.0
            days = max((datetime.datetime.strptime(exp, "%Y-%m-%d").date() - datetime.date.today()).days, 1)

            vol_data.append({"Expiry": datetime.datetime.strptime(exp, "%Y-%m-%d").strftime("%d %b"), "Days": days, "Tenor_Years": days / 365.0, "Mean_IV": mean_iv})
            for _, r in df_exp.iterrows():
                if exp_atm - 600 <= r["Strike"] <= exp_atm + 600:
                    surface_data.append({"Expiry": exp, "Days": days, "Strike": r["Strike"], "IV": (r["CE_IV"] + r["PE_IV"]) / 2.0})

    df_vol, df_surf = pd.DataFrame(vol_data), pd.DataFrame(surface_data)
    if not df_vol.empty and len(df_vol) > 1:
        fwd_vols = [df_vol.loc[0, "Mean_IV"]]
        for i in range(1, len(df_vol)):
            t1, t2, v1, v2 = df_vol.loc[i-1, "Tenor_Years"], df_vol.loc[i, "Tenor_Years"], df_vol.loc[i-1, "Mean_IV"]/100.0, df_vol.loc[i, "Mean_IV"]/100.0
            var_diff, dt = (v2**2 * t2) - (v1**2 * t1), t2 - t1
            fwd_vols.append(math.sqrt(var_diff / dt) * 100.0 if (var_diff > 0 and dt > 0) else v2 * 100.0)
        df_vol["Forward_Vol"] = fwd_vols
    return df_vol, df_surf

# ---------------------------------------------------------
# 6. SESSION & LIVE ENGINE INITIALIZATION
# ---------------------------------------------------------
st.sidebar.header("⚙️ Command Center")
auto_refresh = st.sidebar.checkbox("Live Auto-Refresh (5s)", value=True)
if auto_refresh: st_autorefresh(interval=5000, key="datarefresh")

now_ist = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
today_date_str, now_time_str = now_ist.strftime("%Y-%m-%d"), now_ist.strftime("%H:%M:%S")
m_open, m_close = now_ist.replace(hour=9, minute=15, second=0, microsecond=0), now_ist.replace(hour=15, minute=30, second=0, microsecond=0)
is_market_live = now_ist.weekday() < 5 and (m_open <= now_ist <= m_close)

try: valid_expiries = requests.post("https://api.dhan.co/v2/optionchain/expirylist", headers={"client-id": CLIENT_ID, "access-token": ACCESS_TOKEN, "Content-Type": "application/json"}, json={"UnderlyingScrip": 13, "UnderlyingSeg": "IDX_I"}, timeout=5).json().get("data", [])
except: valid_expiries = []
selected_expiry = st.sidebar.selectbox("Primary Expiry", valid_expiries) if valid_expiries else st.sidebar.date_input("Primary Expiry").strftime("%Y-%m-%d")

df_oc, spot_price, error_remark = fetch_gex_option_chain(selected_expiry)

synthetic_future = spot_price
if df_oc is not None and not df_oc.empty:
    spot_atm = int(round(spot_price / 50) * 50)
    row_atm = df_oc[df_oc["Strike"] == spot_atm]
    if not row_atm.empty: synthetic_future = spot_atm + row_atm["CE_LTP"].values[0] - row_atm["PE_LTP"].values[0]

atm_strike = int(round(synthetic_future / 50) * 50)
strike_m50, strike_p50 = atm_strike - 50, atm_strike + 50

selected_target_strike = st.sidebar.selectbox("🎯 Target Strike", df_oc["Strike"].tolist() if df_oc is not None else [], index=df_oc["Strike"].tolist().index(atm_strike) if df_oc is not None and atm_strike in df_oc["Strike"].tolist() else 0)

# Init Memory
for key, cols in [
    ("iv_spread_history", ["Date", "Time", "Strike", "CE_IV", "PE_IV", "IV_Spread", "Spot"]),
    ("pcr_history", ["Date", "Timestamp_dt", "Time", "PCR", "Vol_PCR", "Delta_PCR_5m", "Delta_PCR_15m", "Total_CE_OI", "Total_PE_OI"]),
    ("gex_history", ["Date", "Timestamp_dt", "Time", "Total_Net_GEX", "Z_GEX", "Flip_Strike", "Spot"]),
    ("synth_history", ["Date", "Time", "Spot", "Strike_M50", "Strike_ATM", "Strike_P50", "Synth_M50", "Synth_ATM", "Synth_P50", "PCP_Dev_Mean"]),
    ("delta_oi_history", ["Date", "Timestamp_dt", "Time", "Total_Net_Delta_OI", "Delta_OI_ROC_1m", "Total_Net_DEX", "DEX_Vel_5m"]),
    ("straddle_history", ["Date", "Time", "Elapsed_Mins", "Actual_Straddle", "Expected_Straddle", "Regime"])
]:
    if key not in st.session_state: st.session_state[key] = check_and_reset(key, cols, today_date_str, now_time_str)

if "straddle_anchor_price" not in st.session_state: st.session_state["straddle_anchor_price"] = None

if st.sidebar.button("🗑️ Reset Session Cache"):
    for key in ["iv_spread_history", "pcr_history", "gex_history", "synth_history", "delta_oi_history", "straddle_history"]:
        st.session_state[key] = pd.DataFrame(columns=st.session_state[key].columns)
    st.session_state["straddle_anchor_price"] = None
    st.cache_data.clear()
    st.rerun()

# ---------------------------------------------------------
# 7. DATA ENGINE PROCESSING
# ---------------------------------------------------------
if error_remark: st.error(f"⚠️ Dhan API Error: {error_remark}")
elif df_oc is not None and not df_oc.empty:
    df_sorted = df_oc.sort_values("Strike").copy()
    df_sorted["Cum_Net_GEX"] = df_sorted["Net_GEX"].cumsum()
    gamma_flip_strike = int(spot_price)
    for i in range(1, len(df_sorted)):
        if (df_sorted.iloc[i-1]["Cum_Net_GEX"] < 0 and df_sorted.iloc[i]["Cum_Net_GEX"] >= 0) or (df_sorted.iloc[i-1]["Cum_Net_GEX"] > 0 and df_sorted.iloc[i]["Cum_Net_GEX"] <= 0):
            gamma_flip_strike = int((df_sorted.iloc[i-1]["Strike"] + df_sorted.iloc[i]["Strike"]) / 2.0)
            break

    # Max Pain Engine
    df_pain, max_pain_strike = pd.DataFrame(), atm_strike
    pain_records = [{"Strike": k, "Writer_Loss": (df_oc["CE_OI"] * (k - df_oc["Strike"]).clip(lower=0)).sum() + (df_oc["PE_OI"] * (df_oc["Strike"] - k).clip(lower=0)).sum()} for k in df_oc["Strike"] if atm_strike - 1500 <= k <= atm_strike + 1500]
    if pain_records:
        df_pain = pd.DataFrame(pain_records)
        max_pain_strike = df_pain.loc[df_pain["Writer_Loss"].idxmin()]["Strike"]

    target_row = df_oc[df_oc["Strike"] == selected_target_strike]
    target_iv_spread = (target_row["CE_IV"].values[0] if not target_row.empty else 0.0) - (target_row["PE_IV"].values[0] if not target_row.empty else 0.0)

    df_filtered = df_oc[(df_oc["Strike"] >= atm_strike - 550) & (df_oc["Strike"] <= atm_strike + 550)].copy()
    strike_labels = df_filtered["Strike"].astype(str).tolist()
    
    # Safe Wall Calculations
    call_wall_gex = df_filtered.loc[df_filtered['Net_GEX'].idxmax()]['Strike'] if not df_filtered.empty else atm_strike
    put_wall_gex = df_filtered.loc[df_filtered['Net_GEX'].idxmin()]['Strike'] if not df_filtered.empty else atm_strike
    call_wall_dex = df_filtered.loc[df_filtered['Net_DEX'].idxmax()]['Strike'] if not df_filtered.empty else atm_strike
    put_wall_dex = df_filtered.loc[df_filtered['Net_DEX'].idxmin()]['Strike'] if not df_filtered.empty else atm_strike

    # Process Memory updates ONLY during Live Market
    if is_market_live:
        for key in ["iv_spread_history", "pcr_history", "gex_history", "synth_history", "delta_oi_history", "straddle_history"]:
            if not st.session_state[key].empty and st.session_state[key].iloc[-1]["Date"] != today_date_str:
                st.session_state[key] = st.session_state[key].iloc[0:0]
                if key == "straddle_history": st.session_state["straddle_anchor_price"] = None

        if st.session_state["iv_spread_history"].empty or st.session_state["iv_spread_history"].iloc[-1]["Time"] != now_time_str:
            new_ticks = [{"Date": today_date_str, "Time": now_time_str, "Strike": r["Strike"], "CE_IV": r["CE_IV"], "PE_IV": r["PE_IV"], "IV_Spread": r["IV_Spread"], "Spot": spot_price} for _, r in df_filtered.iterrows()]
            st.session_state["iv_spread_history"] = pd.concat([st.session_state["iv_spread_history"], pd.DataFrame(new_ticks)], ignore_index=True)
            save_persisted_df(st.session_state["iv_spread_history"], "iv_spread_history")

        total_ce_oi, total_pe_oi = df_oc["CE_OI"].sum(), df_oc["PE_OI"].sum()
        current_pcr = total_pe_oi / total_ce_oi if total_ce_oi > 0 else 0.0
        vol_pcr = df_oc["PE_Vol"].sum() / df_oc["CE_Vol"].sum() if df_oc["CE_Vol"].sum() > 0 else 0.0
        
        pcr_df = st.session_state["pcr_history"]
        if pcr_df.empty or pcr_df.iloc[-1]["Time"] != now_time_str:
            dp_15m = current_pcr - pcr_df[pcr_df["Timestamp_dt"] <= now_ist - datetime.timedelta(minutes=15)].iloc[-1]["PCR"] if not pcr_df[pcr_df["Timestamp_dt"] <= now_ist - datetime.timedelta(minutes=15)].empty else 0.0
            st.session_state["pcr_history"] = pd.concat([pcr_df, pd.DataFrame([{"Date": today_date_str, "Timestamp_dt": now_ist, "Time": now_time_str, "PCR": current_pcr, "Vol_PCR": vol_pcr, "Delta_PCR_5m": 0.0, "Delta_PCR_15m": dp_15m, "Total_CE_OI": total_ce_oi, "Total_PE_OI": total_pe_oi}])], ignore_index=True)
            save_persisted_df(st.session_state["pcr_history"], "pcr_history")

        gex_df = st.session_state["gex_history"]
        if gex_df.empty or gex_df.iloc[-1]["Time"] != now_time_str:
            z_gex = (df_oc["Net_GEX"].sum() - gex_df["Total_Net_GEX"].tail(20).mean()) / gex_df["Total_Net_GEX"].tail(20).std() if len(gex_df) >= 2 and gex_df["Total_Net_GEX"].tail(20).std() > 0 else 0.0
            st.session_state["gex_history"] = pd.concat([gex_df, pd.DataFrame([{"Date": today_date_str, "Timestamp_dt": now_ist, "Time": now_time_str, "Total_Net_GEX": df_oc["Net_GEX"].sum(), "Z_GEX": z_gex, "Flip_Strike": gamma_flip_strike, "Spot": spot_price}])], ignore_index=True)
            save_persisted_df(st.session_state["gex_history"], "gex_history")

        synth_df = st.session_state["synth_history"]
        if synth_df.empty or synth_df.iloc[-1]["Time"] != now_time_str:
            r_m50, r_atm, r_p50 = df_oc[df_oc["Strike"] == strike_m50], df_oc[df_oc["Strike"] == atm_strike], df_oc[df_oc["Strike"] == strike_p50]
            s_m50 = strike_m50 + r_m50["CE_LTP"].values[0] - r_m50["PE_LTP"].values[0] if not r_m50.empty else spot_price
            s_atm = atm_strike + r_atm["CE_LTP"].values[0] - r_atm["PE_LTP"].values[0] if not r_atm.empty else spot_price
            s_p50 = strike_p50 + r_p50["CE_LTP"].values[0] - r_p50["PE_LTP"].values[0] if not r_p50.empty else spot_price
            st.session_state["synth_history"] = pd.concat([synth_df, pd.DataFrame([{"Date": today_date_str, "Time": now_time_str, "Spot": spot_price, "Strike_M50": strike_m50, "Strike_ATM": atm_strike, "Strike_P50": strike_p50, "Synth_M50": s_m50, "Synth_ATM": s_atm, "Synth_P50": s_p50, "PCP_Dev_Mean": ((s_m50 - spot_price) + (s_atm - spot_price) + (s_p50 - spot_price)) / 3.0}])], ignore_index=True)
            save_persisted_df(st.session_state["synth_history"], "synth_history")

        doi_df = st.session_state["delta_oi_history"]
        if doi_df.empty or doi_df.iloc[-1]["Time"] != now_time_str:
            d_roc_1m = df_oc["Net_Delta_OI"].sum() - doi_df[doi_df["Timestamp_dt"] <= now_ist - datetime.timedelta(minutes=1)].iloc[-1]["Total_Net_Delta_OI"] if not doi_df[doi_df["Timestamp_dt"] <= now_ist - datetime.timedelta(minutes=1)].empty else 0.0
            dex_vel = (df_oc["Net_DEX"].sum() / 100.0) - doi_df[doi_df["Timestamp_dt"] <= now_ist - datetime.timedelta(minutes=5)].iloc[-1]["Total_Net_DEX"] if not doi_df[doi_df["Timestamp_dt"] <= now_ist - datetime.timedelta(minutes=5)].empty else 0.0
            st.session_state["delta_oi_history"] = pd.concat([doi_df, pd.DataFrame([{"Date": today_date_str, "Timestamp_dt": now_ist, "Time": now_time_str, "Total_Net_Delta_OI": df_oc["Net_Delta_OI"].sum(), "Delta_OI_ROC_1m": d_roc_1m, "Total_Net_DEX": df_oc["Net_DEX"].sum() / 100.0, "DEX_Vel_5m": dex_vel}])], ignore_index=True)
            save_persisted_df(st.session_state["delta_oi_history"], "delta_oi_history")

        strad_df = st.session_state["straddle_history"]
        if strad_df.empty or strad_df.iloc[-1]["Time"] != now_time_str:
            r_atm_cur = df_oc[df_oc["Strike"] == atm_strike]
            c_strad = (r_atm_cur["CE_LTP"].values[0] if not r_atm_cur.empty else 0.0) + (r_atm_cur["PE_LTP"].values[0] if not r_atm_cur.empty else 0.0)
            e_mins = max(0, min((now_ist - m_open).total_seconds() / 60.0, 375)) 
            if e_mins >= 5.0 and st.session_state["straddle_anchor_price"] is None: st.session_state["straddle_anchor_price"] = c_strad
            e_strad = (st.session_state["straddle_anchor_price"] or c_strad) * (1 - (0.15 * math.sqrt(e_mins / 375)))
            regime = "VOL COIL 🟢" if c_strad > e_strad + 2.0 else ("IV CRUSH 🔴" if c_strad < e_strad - 2.0 else "NORMAL DECAY")
            st.session_state["straddle_history"] = pd.concat([strad_df, pd.DataFrame([{"Date": today_date_str, "Time": now_time_str, "Elapsed_Mins": e_mins, "Actual_Straddle": c_strad, "Expected_Straddle": e_strad, "Regime": regime}])], ignore_index=True)
            save_persisted_df(st.session_state["straddle_history"], "straddle_history")

    # UI Interpretation State Values
    pcr_df, gex_df, synth_df, doi_df, strad_df = st.session_state["pcr_history"], st.session_state["gex_history"], st.session_state["synth_history"], st.session_state["delta_oi_history"], st.session_state["straddle_history"]
    
    cz_gex = gex_df.iloc[-1]["Z_GEX"] if not gex_df.empty else 0.0
    if cz_gex < -2.0: z_signal, z_color = "GAMMA COLLAPSE", "#FF5252"
    elif -1.0 <= cz_gex <= 1.0: z_signal, z_color = "NORMAL DAMPENING", "#00E676"
    else: z_signal, z_color = "TRANSITION ZONE", "#FFD700"

    t_net_doi = df_oc["Net_Delta_OI"].sum()
    if t_net_doi > 50000: dir_signal, dir_color = "STRONGLY BULLISH", "#00E676"
    elif t_net_doi > 10000: dir_signal, dir_color = "MILDLY BULLISH", "#00E676"
    elif t_net_doi < -50000: dir_signal, dir_color = "STRONGLY BEARISH", "#FF5252"
    elif t_net_doi < -10000: dir_signal, dir_color = "MILDLY BEARISH", "#FF5252"
    else: dir_signal, dir_color = "NEUTRAL / RANGEBOUND", "#FFD700"

    r_m50, r_atm, r_p50 = df_oc[df_oc["Strike"] == strike_m50], df_oc[df_oc["Strike"] == atm_strike], df_oc[df_oc["Strike"] == strike_p50]
    s_m50 = strike_m50 + r_m50["CE_LTP"].values[0] - r_m50["PE_LTP"].values[0] if not r_m50.empty else spot_price
    s_atm = atm_strike + r_atm["CE_LTP"].values[0] - r_atm["PE_LTP"].values[0] if not r_atm.empty else spot_price
    s_p50 = strike_p50 + r_p50["CE_LTP"].values[0] - r_p50["PE_LTP"].values[0] if not r_p50.empty else spot_price

    if (s_m50 > spot_price + 1.0) and (s_atm > spot_price + 1.0) and (s_p50 > spot_price + 1.0): synth_flag_text, synth_flag_color = "🟢 BULL ACCUMULATION FLAG: Synthetics > Spot", "#00E676"
    elif (s_m50 < spot_price - 1.0) and (s_atm < spot_price - 1.0) and (s_p50 < spot_price - 1.0): synth_flag_text, synth_flag_color = "🔴 BEAR DISTRIBUTION FLAG: Synthetics < Spot", "#FF5252"
    else: synth_flag_text, synth_flag_color = "⚪ NEUTRAL: Synthetic Parity Tracking Spot Closely", "#8A93A6"


    # ---------------------------------------------------------
    # 8. DASHBOARD UI RENDERING
    # ---------------------------------------------------------
    st.markdown(f"### PRINCE PAX DASHBOARD")
    st.markdown(f'<div class="status-badge {"status-live" if is_market_live else "status-closed"}">{"🟢 LIVE MARKET" if is_market_live else "🟠 MARKET CLOSED"} | Expiry: {selected_expiry} | IST: {now_time_str}</div>', unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    # --- EXECUTIVE INTERPRETATION PANEL ---
    st.markdown(f"""
    <div style="background-color: #14151A; border: 1px solid #2A2E39; border-radius: 6px; padding: 12px 16px; margin-bottom: 20px; box-shadow: 0 4px 12px rgba(0,0,0,0.5);">
        <div style="color: #8A93A6; font-size: 0.75rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 10px; border-bottom: 1px solid #2A2E39; padding-bottom: 5px;">🧠 Executive Regime Interpretation</div>
        <div style="display: flex; flex-wrap: wrap; gap: 15px;">
            <div style="flex: 1; min-width: 200px; border-right: 1px solid #2A2E39; padding-right: 10px;">
                <span style="color: #D1D4DC; font-size: 0.8rem; font-weight: 600;">SYNTHETIC PARITY:</span><br>
                <span style="color: {synth_flag_color}; font-weight: 800; font-size: 0.95rem;">{synth_flag_text}</span>
            </div>
            <div style="flex: 1; min-width: 150px; border-right: 1px solid #2A2E39; padding-right: 10px;">
                <span style="color: #D1D4DC; font-size: 0.8rem; font-weight: 600;">DELTA FLOW:</span><br>
                <span style="color: {dir_color}; font-weight: 800; font-size: 0.95rem;">{dir_signal}</span>
            </div>
            <div style="flex: 1; min-width: 150px;">
                <span style="color: #D1D4DC; font-size: 0.8rem; font-weight: 600;">GAMMA REGIME:</span><br>
                <span style="color: {z_color}; font-weight: 800; font-size: 0.95rem;">{z_signal}</span>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # --- TOP SUMMARY METRIC CARDS ---
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.markdown(f'<div class="metric-card metric-card-amber"><div class="metric-title">NIFTY SYNTH FUT</div><div class="metric-value">₹{synthetic_future:,.2f}</div><div class="metric-sub sub-amber">Spot: ₹{spot_price:,.2f} | Pain: {max_pain_strike}</div></div>', unsafe_allow_html=True)
    m2.markdown(f'<div class="metric-card {"metric-card-green" if target_iv_spread >= 0 else "metric-card-red"}"><div class="metric-title">{selected_target_strike} IV SPREAD</div><div class="metric-value">{target_iv_spread:+.2f}%</div><div class="metric-sub {"sub-green" if target_iv_spread >= 0 else "sub-red"}">CE {(target_row["CE_IV"].values[0]*100) if not target_row.empty else 0:.1f}% | PE {(target_row["PE_IV"].values[0]*100) if not target_row.empty else 0:.1f}%</div></div>', unsafe_allow_html=True)
    dp_15m = pcr_df.iloc[-1]["Delta_PCR_15m"] if not pcr_df.empty else 0.0
    m3.markdown(f'<div class="metric-card {"metric-card-green" if dp_15m >= 0.15 else ("metric-card-red" if dp_15m <= -0.15 else "metric-card-amber")}"><div class="metric-title">ΔPCR 15M VELOCITY</div><div class="metric-value">{dp_15m:+.2f}</div><div class="metric-sub {"sub-green" if dp_15m >= 0.15 else ("sub-red" if dp_15m <= -0.15 else "sub-amber")}">PCR: {pcr_df.iloc[-1]["PCR"] if not pcr_df.empty else 0:.2f}</div></div>', unsafe_allow_html=True)
    m4.markdown(f'<div class="metric-card {"metric-card-green" if df_oc["Net_Delta_OI"].sum() >= 0 else "metric-card-red"}"><div class="metric-title">NET DELTA OI</div><div class="metric-value">{df_oc["Net_Delta_OI"].sum():+,.0f}</div><div class="metric-sub {"sub-green" if (doi_df.iloc[-1]["Delta_OI_ROC_1m"] if not doi_df.empty else 0) >= 0 else "sub-red"}">1m ROC: {doi_df.iloc[-1]["Delta_OI_ROC_1m"] if not doi_df.empty else 0:+,.0f}</div></div>', unsafe_allow_html=True)
    m5.markdown(f'<div class="metric-card {"metric-card-green" if (strad_df.iloc[-1]["Regime"] if not strad_df.empty else "") == "VOL COIL 🟢" else "metric-card-amber"}"><div class="metric-title">STRADDLE DECAY</div><div class="metric-value">₹{strad_df.iloc[-1]["Actual_Straddle"] if not strad_df.empty else 0:.1f}</div><div class="metric-sub {"sub-green" if (strad_df.iloc[-1]["Regime"] if not strad_df.empty else "") == "VOL COIL 🟢" else "sub-amber"}">{strad_df.iloc[-1]["Regime"] if not strad_df.empty else "NORMAL"}</div></div>', unsafe_allow_html=True)
    z_col = "metric-card-red" if cz_gex < -2.0 else ("metric-card-green" if -1.0 <= cz_gex <= 1.0 else "metric-card-amber")
    m6.markdown(f'<div class="metric-card {z_col}"><div class="metric-title">Z-GEX SCORE</div><div class="metric-value">{cz_gex:+.2f}</div><div class="metric-sub {"sub-red" if cz_gex < -2.0 else ("sub-green" if -1.0 <= cz_gex <= 1.0 else "sub-amber")}">{"GAMMA COLLAPSE" if cz_gex < -2.0 else ("NORMAL DAMPENING" if -1.0 <= cz_gex <= 1.0 else "TRANSITION ZONE")}</div></div>', unsafe_allow_html=True)

    # --- HORIZONTAL AGGREGATE METRICS (IMAGE REPLICA) ---
    st.markdown('<div class="chart-title" style="margin-top:10px;">Aggregate Options Flow (Total Call vs Put)</div>', unsafe_allow_html=True)
    h1, h2, h3, h4, h5, h6 = st.columns(6)
    h1.plotly_chart(create_h_bar("Total OI", df_filtered["PE_OI"].sum(), df_filtered["CE_OI"].sum()), use_container_width=True)
    h2.plotly_chart(create_h_bar("OI Change", df_filtered["PE_OI_Chg"].sum(), df_filtered["CE_OI_Chg"].sum()), use_container_width=True)
    h3.plotly_chart(create_h_bar("Volume", df_filtered["PE_Vol"].sum(), df_filtered["CE_Vol"].sum()), use_container_width=True)
    h4.plotly_chart(create_h_bar("Theta Exp (CHEX)", df_filtered["PE_CHEX"].sum(), df_filtered["CE_CHEX"].sum()), use_container_width=True)
    h5.plotly_chart(create_h_bar("Vega Exp (VEX)", df_filtered["PE_VEX"].sum(), df_filtered["CE_VEX"].sum()), use_container_width=True)
    h6.plotly_chart(create_h_bar("Gamma Exp (GEX)", abs(df_filtered["Put_GEX"].sum()), df_filtered["Call_GEX"].sum()), use_container_width=True)


    # 8C. TABBED INTERFACE
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "🚀 Intraday Flow Center", 
        "🛡️ Greek Exposure Profiles", 
        "🔬 Advanced Analytics", 
        "📈 OpenBull Options Skew", 
        "📊 Options Chain Grid"
    ])

    with tab1: # INTRA DAY FLOW
        r1c1, r1c2 = st.columns(2)
        with r1c1:
            st.markdown(f'<div class="chart-container"><div class="chart-title">Intraday IV Spread Movement ({selected_target_strike})</div>', unsafe_allow_html=True)
            fig_ts = go.Figure()
            strike_history = st.session_state["iv_spread_history"][st.session_state["iv_spread_history"]["Strike"] == selected_target_strike] if not st.session_state["iv_spread_history"].empty else pd.DataFrame()
            if not strike_history.empty: fig_ts.add_trace(go.Scatter(x=strike_history["Time"], y=strike_history["IV_Spread"], mode="lines+markers", line=dict(color="#29B6F6", width=2), marker=dict(size=3)))
            fig_ts.add_hline(y=0, line_dash="dash", line_color="white", opacity=0.3)
            st.plotly_chart(apply_dark_layout(fig_ts), use_container_width=True, key="c_ts")
            st.markdown('</div>', unsafe_allow_html=True)
        with r1c2:
            st.markdown('<div class="chart-container"><div class="chart-title">15-Min PCR Velocity (ΔPCR)</div>', unsafe_allow_html=True)
            fig_pcr = go.Figure()
            if not pcr_df.empty: fig_pcr.add_trace(go.Bar(x=pcr_df["Time"], y=pcr_df["Delta_PCR_15m"], marker_color=["#00E676" if v >= 0.15 else ("#FF5252" if v <= -0.15 else "#8A93A6") for v in pcr_df["Delta_PCR_15m"]]))
            fig_pcr.add_hline(y=0.15, line_dash="dash", line_color="#00E676")
            fig_pcr.add_hline(y=-0.15, line_dash="dash", line_color="#FF5252")
            st.plotly_chart(apply_dark_layout(fig_pcr), use_container_width=True, key="c_pcr")
            st.markdown('</div>', unsafe_allow_html=True)

        r2c1, r2c2 = st.columns(2)
        with r2c1:
            st.markdown('<div class="chart-container"><div class="chart-title">OpenBull Cumulative OI Trend (Cr)</div>', unsafe_allow_html=True)
            fig_oi_trend = go.Figure()
            if not pcr_df.empty:
                fig_oi_trend.add_trace(go.Scatter(x=pcr_df["Time"], y=pcr_df["Total_PE_OI"]/1e7, mode="lines", name="Put OI", line=dict(color="#29B6F6", width=2)))
                fig_oi_trend.add_trace(go.Scatter(x=pcr_df["Time"], y=pcr_df["Total_CE_OI"]/1e7, mode="lines", name="Call OI", line=dict(color="#FF5252", width=2)))
                fig_oi_trend.add_trace(go.Scatter(x=pcr_df["Time"], y=(pcr_df["Total_PE_OI"]-pcr_df["Total_CE_OI"])/1e7, mode="lines", name="PE-CE Diff", line=dict(color="#AB47BC", width=2)))
            st.plotly_chart(apply_dark_layout(fig_oi_trend), use_container_width=True, key="c_oit")
            st.markdown('</div>', unsafe_allow_html=True)
        with r2c2:
            st.markdown('<div class="chart-container"><div class="chart-title">Intraday PCR & Vol PCR Trend</div>', unsafe_allow_html=True)
            fig_pcr_t = go.Figure()
            if not pcr_df.empty:
                fig_pcr_t.add_trace(go.Scatter(x=pcr_df["Time"], y=pcr_df["PCR"], mode="lines", name="OI PCR", line=dict(color="#29B6F6", width=2)))
                if "Vol_PCR" in pcr_df.columns: fig_pcr_t.add_trace(go.Scatter(x=pcr_df["Time"], y=pcr_df["Vol_PCR"], mode="lines", name="Vol PCR", line=dict(color="#FFA726", width=2)))
            st.plotly_chart(apply_dark_layout(fig_pcr_t), use_container_width=True, key="c_pcrt")
            st.markdown('</div>', unsafe_allow_html=True)

        r3c1, r3c2 = st.columns(2)
        with r3c1:
            st.markdown('<div class="chart-container"><div class="chart-title">Real-Time Delta-Weighted Net OI</div>', unsafe_allow_html=True)
            fig_doi = go.Figure()
            if not doi_df.empty: fig_doi.add_trace(go.Scatter(x=doi_df["Time"], y=doi_df["Total_Net_Delta_OI"], mode="lines", fill='tozeroy', line=dict(color="#00E676", width=2)))
            fig_doi.add_hline(y=0, line_dash="dash", line_color="white", opacity=0.3)
            st.plotly_chart(apply_dark_layout(fig_doi), use_container_width=True, key="c_doi")
            st.markdown('</div>', unsafe_allow_html=True)
        with r3c2:
            st.markdown('<div class="chart-container"><div class="chart-title">Dealer Delta Velocity (DEX 5m ROC)</div>', unsafe_allow_html=True)
            fig_dvel = go.Figure()
            if not doi_df.empty: fig_dvel.add_trace(go.Bar(x=doi_df["Time"], y=doi_df["DEX_Vel_5m"], marker_color=["#00E676" if v >= 0 else "#FF5252" for v in doi_df["DEX_Vel_5m"]]))
            fig_dvel.add_hline(y=0, line_dash="dash", line_color="white", opacity=0.3)
            st.plotly_chart(apply_dark_layout(fig_dvel), use_container_width=True, key="c_dvel")
            st.markdown('</div>', unsafe_allow_html=True)

    with tab2: # GREEK EXPOSURES
        oi_col1, oi_col2 = st.columns(2)
        with oi_col1:
            st.markdown('<div class="chart-container"><div class="chart-title">OI Tracker (CE/PE Profile)</div>', unsafe_allow_html=True)
            fig_oi_prof = go.Figure()
            fig_oi_prof.add_trace(go.Bar(x=df_filtered["Strike"], y=df_filtered["PE_OI"], name="Put OI", marker_color="#29B6F6"))
            fig_oi_prof.add_trace(go.Bar(x=df_filtered["Strike"], y=df_filtered["CE_OI"], name="Call OI", marker_color="#FF5252"))
            fig_oi_prof.add_vline(x=spot_price, line_dash="solid", line_color="#FFD700")
            fig_oi_prof.update_xaxes(tickmode='array', tickvals=df_filtered["Strike"], ticktext=strike_labels)
            fig_oi_prof.update_layout(barmode='group')
            st.plotly_chart(apply_dark_layout(fig_oi_prof), use_container_width=True, key="c_oiprof")
            st.markdown('</div>', unsafe_allow_html=True)
        with oi_col2:
            st.markdown('<div class="chart-container"><div class="chart-title">OI Change Tracker (CE/PE Profile)</div>', unsafe_allow_html=True)
            fig_oichg_prof = go.Figure()
            fig_oichg_prof.add_trace(go.Bar(x=df_filtered["Strike"], y=df_filtered["PE_OI_Chg"], name="Put OI Chg", marker_color="#29B6F6"))
            fig_oichg_prof.add_trace(go.Bar(x=df_filtered["Strike"], y=df_filtered["CE_OI_Chg"], name="Call OI Chg", marker_color="#FF5252"))
            fig_oichg_prof.add_vline(x=spot_price, line_dash="solid", line_color="#FFD700")
            fig_oichg_prof.update_xaxes(tickmode='array', tickvals=df_filtered["Strike"], ticktext=strike_labels)
            fig_oichg_prof.update_layout(barmode='group')
            st.plotly_chart(apply_dark_layout(fig_oichg_prof), use_container_width=True, key="c_oichgprof")
            st.markdown('</div>', unsafe_allow_html=True)

        e1, e2 = st.columns(2)
        with e1:
            st.markdown('<div class="chart-container"><div class="chart-title">Net Delta Exposure (DEX) By Strike</div>', unsafe_allow_html=True)
            fig_dex = go.Figure()
            fig_dex.add_trace(go.Bar(x=df_filtered["Strike"], y=df_filtered["Net_DEX"], marker_color=["#00E676" if val >= 0 else "#FF5252" for val in df_filtered["Net_DEX"]], name="Net DEX", opacity=0.75))
            fig_dex.add_trace(go.Scatter(x=df_filtered["Strike"], y=df_filtered["ABS_DEX"], mode="lines", name="Absolute DEX", line=dict(color="#FFA726", width=2, shape="spline", smoothing=1.3)))
            y_max_dex = max(df_filtered["ABS_DEX"].max() if not df_filtered.empty else 1, df_filtered["Net_DEX"].max() if not df_filtered.empty else 1) * 1.1
            fig_dex.add_vline(x=spot_price, line_dash="solid", line_color="#FFD700"); fig_dex.add_annotation(x=spot_price, y=y_max_dex*0.95, text=f"Spot: {spot_price:.1f}", showarrow=False, font=dict(color="#FFD700", size=9))
            fig_dex.add_vline(x=call_wall_dex, line_dash="dash", line_color="#00E676"); fig_dex.add_annotation(x=call_wall_dex, y=y_max_dex*0.85, text=f"Call Wall: {call_wall_dex}", showarrow=False, font=dict(color="#00E676", size=9))
            fig_dex.add_vline(x=put_wall_dex, line_dash="dash", line_color="#FF5252"); fig_dex.add_annotation(x=put_wall_dex, y=y_max_dex*0.75, text=f"Put Wall: {put_wall_dex}", showarrow=False, font=dict(color="#FF5252", size=9))
            fig_dex.update_xaxes(tickmode='array', tickvals=df_filtered["Strike"], ticktext=strike_labels, tickangle=-45)
            st.plotly_chart(apply_dark_layout(fig_dex, 350), use_container_width=True, key="c_dex")
            st.markdown('</div>', unsafe_allow_html=True)
        with e2:
            st.markdown('<div class="chart-container"><div class="chart-title">Net Gamma Exposure (GEX) By Strike</div>', unsafe_allow_html=True)
            fig_gex = go.Figure()
            fig_gex.add_trace(go.Bar(x=df_filtered["Strike"], y=df_filtered["Net_GEX"], marker_color=["#00E676" if g >= 0 else "#FF5252" for g in df_filtered["Net_GEX"]], name="Net GEX", opacity=0.75))
            fig_gex.add_trace(go.Scatter(x=df_filtered["Strike"], y=df_filtered["ABS_GEX"], mode="lines", name="Absolute GEX", line=dict(color="#29B6F6", width=2, shape="spline", smoothing=1.3)))
            y_max_gex = max(df_filtered["ABS_GEX"].max() if not df_filtered.empty else 1, df_filtered["Net_GEX"].max() if not df_filtered.empty else 1) * 1.1
            fig_gex.add_vline(x=spot_price, line_dash="solid", line_color="#FFD700"); fig_gex.add_annotation(x=spot_price, y=y_max_gex*0.95, text=f"Spot: {spot_price:.1f}", showarrow=False, font=dict(color="#FFD700", size=9))
            fig_gex.add_vline(x=gamma_flip_strike, line_dash="dash", line_color="#29B6F6"); fig_gex.add_annotation(x=gamma_flip_strike, y=y_max_gex*0.85, text=f"Flip: {gamma_flip_strike}", showarrow=False, font=dict(color="#29B6F6", size=9))
            fig_gex.add_vline(x=call_wall_gex, line_dash="dash", line_color="#00E676"); fig_gex.add_annotation(x=call_wall_gex, y=y_max_gex*0.75, text=f"Call Wall: {call_wall_gex}", showarrow=False, font=dict(color="#00E676", size=9))
            fig_gex.add_vline(x=put_wall_gex, line_dash="dash", line_color="#FF5252"); fig_gex.add_annotation(x=put_wall_gex, y=y_max_gex*0.65, text=f"Put Wall: {put_wall_gex}", showarrow=False, font=dict(color="#FF5252", size=9))
            fig_gex.update_xaxes(tickmode='array', tickvals=df_filtered["Strike"], ticktext=strike_labels, tickangle=-45)
            st.plotly_chart(apply_dark_layout(fig_gex, 350), use_container_width=True, key="c_gex")
            st.markdown('</div>', unsafe_allow_html=True)

        e3, e4 = st.columns(2)
        with e3:
            st.markdown('<div class="chart-container"><div class="chart-title">Z-GEX & Expiry SPEX (Speed)</div>', unsafe_allow_html=True)
            fig_zgex = go.Figure()
            if not gex_df.empty: fig_zgex.add_trace(go.Scatter(x=gex_df["Time"], y=gex_df["Z_GEX"], mode="lines", fill='tozeroy', line=dict(color="#AB47BC", width=2)))
            fig_zgex.add_hline(y=1.0, line_dash="solid", line_color="#00E676", opacity=0.3); fig_zgex.add_hline(y=-1.0, line_dash="solid", line_color="#00E676", opacity=0.3)
            fig_zgex.add_hline(y=-2.0, line_dash="dash", line_color="#FF5252", annotation_text="Collapse")
            st.plotly_chart(apply_dark_layout(fig_zgex), use_container_width=True, key="c_zgex")
            st.markdown('</div>', unsafe_allow_html=True)
        with e4:
            st.markdown('<div class="chart-container"><div class="chart-title">Vanna & Charm Exposure</div>', unsafe_allow_html=True)
            fig_vc = go.Figure()
            fig_vc.add_trace(go.Scatter(x=df_filtered["Strike"], y=df_filtered["Net_VEX"], mode="lines+markers", name="Vanna", line=dict(color="#FFA726", width=2)))
            fig_vc.add_trace(go.Scatter(x=df_filtered["Strike"], y=df_filtered["Net_CHEX"], mode="lines+markers", name="Charm", line=dict(color="#AB47BC", width=2)))
            fig_vc.update_xaxes(tickmode='array', tickvals=df_filtered["Strike"], ticktext=strike_labels)
            st.plotly_chart(apply_dark_layout(fig_vc), use_container_width=True, key="c_vchex")
            st.markdown('</div>', unsafe_allow_html=True)

    with tab3: # ADVANCED ANALYTICS
        a1, a2 = st.columns(2)
        with a1:
            st.markdown('<div class="chart-container"><div class="chart-title">Anchored ATM Straddle Decay vs Expected</div>', unsafe_allow_html=True)
            fig_strad = go.Figure()
            if not strad_df.empty:
                fig_strad.add_trace(go.Scatter(x=strad_df["Time"], y=strad_df["Actual_Straddle"], mode="lines", name="Actual", line=dict(color="#29B6F6", width=2.5)))
                fig_strad.add_trace(go.Scatter(x=strad_df["Time"], y=strad_df["Expected_Straddle"], mode="lines", name="Expected Decay", line=dict(color="#8A93A6", width=1.5, dash="dot")))
            st.plotly_chart(apply_dark_layout(fig_strad), use_container_width=True, key="c_strad")
            st.markdown('</div>', unsafe_allow_html=True)
        with a2:
            st.markdown('<div class="chart-container"><div class="chart-title">Gamma Flip Migration (ΔFlip)</div>', unsafe_allow_html=True)
            fig_flip = go.Figure()
            if not gex_df.empty:
                fig_flip.add_trace(go.Scatter(x=gex_df["Time"], y=gex_df["Spot"], mode="lines", name="Spot", line=dict(color="#FFD700", width=2)))
                fig_flip.add_trace(go.Scatter(x=gex_df["Time"], y=gex_df["Flip_Strike"], mode="lines", name="Flip Level", line=dict(color="#29B6F6", width=2, dash="dash")))
            st.plotly_chart(apply_dark_layout(fig_flip), use_container_width=True, key="c_flipm")
            st.markdown('</div>', unsafe_allow_html=True)

        a3, a4 = st.columns(2)
        with a3:
            st.markdown('<div class="chart-container"><div class="chart-title">Put-Call Parity Discrepancy Index (PCP_Dev)</div>', unsafe_allow_html=True)
            fig_pcp = go.Figure()
            if not synth_df.empty:
                fig_pcp.add_trace(go.Bar(x=synth_df["Time"], y=synth_df["PCP_Dev_Mean"], marker_color=["#00E676" if v > 0 else "#FF5252" for v in synth_df["PCP_Dev_Mean"]]))
            fig_pcp.add_hline(y=3.0, line_dash="dash", line_color="#00E676", annotation_text="+3.0 Call Squeeze")
            fig_pcp.add_hline(y=-3.0, line_dash="dash", line_color="#FF5252", annotation_text="-3.0 Put Squeeze")
            st.plotly_chart(apply_dark_layout(fig_pcp), use_container_width=True, key="c_pcp")
            st.markdown('</div>', unsafe_allow_html=True)
        with a4:
            st.markdown('<div class="chart-container"><div class="chart-title">Multi-Strike Synthetic Parity Engine</div>', unsafe_allow_html=True)
            fig_synth = go.Figure()
            if not synth_df.empty:
                fig_synth.add_trace(go.Scatter(x=synth_df["Time"], y=synth_df["Spot"], mode="lines", name="Spot", line=dict(color="#FFD700", width=2)))
                fig_synth.add_trace(go.Scatter(x=synth_df["Time"], y=synth_df["Synth_M50"], mode="lines", name="ITM Synth", line=dict(color="#00E676", width=1.5, dash="dot")))
                fig_synth.add_trace(go.Scatter(x=synth_df["Time"], y=synth_df["Synth_ATM"], mode="lines", name="ATM Synth", line=dict(color="#29B6F6", width=1.5, dash="dot")))
                fig_synth.add_trace(go.Scatter(x=synth_df["Time"], y=synth_df["Synth_P50"], mode="lines", name="OTM Synth", line=dict(color="#FF5252", width=1.5, dash="dot")))
            st.plotly_chart(apply_dark_layout(fig_synth), use_container_width=True, key="c_synth")
            st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="chart-container"><div class="chart-title">Futures Basis & Heavyweight CVD Filter (Live WebSocket)</div>', unsafe_allow_html=True)
        c_hw1, c_hw2, c_hw3, c_hw4 = st.columns(4)
        n_fut, cvd_val = live_ws_data.get("NIFTY_FUT_LTP", 0.0), live_ws_data.get("CVD", 0.0)
        c_hw1.metric("Live Nifty Futures", f"₹{n_fut:,.2f}" if n_fut > 0 else "Awaiting Tick...")
        c_hw2.markdown(f'<div><div style="color: #8A93A6; font-size: 0.85rem; font-weight: 600;">FUTURES BASIS</div><div style="font-size: 1.5rem; font-weight: 700; margin-top: 5px;" class="{"sub-green" if (n_fut - spot_price) >= 0 else "sub-red"}">{(n_fut - spot_price):+.2f} Pts</div></div>', unsafe_allow_html=True)
        c_hw3.markdown(f'<div><div style="color: #8A93A6; font-size: 0.85rem; font-weight: 600;">HEAVYWEIGHT NET CVD</div><div style="font-size: 1.5rem; font-weight: 700; margin-top: 5px;" class="{"sub-green" if cvd_val >= 0 else "sub-red"}">{cvd_val:+,.0f} Vol</div></div>', unsafe_allow_html=True)
        c_hw4.markdown(f'<div><div style="color: #8A93A6; font-size: 0.85rem; font-weight: 600;">DAEMON STATUS</div><div style="font-size: 1.1rem; font-weight: 700; margin-top: 5px;">{"🟢 ACTIVE" if live_ws_data.get("CONNECTED") else "🔴 RECONNECTING..."}</div></div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with tab4: # OPENBULL & VOLATILITY
        v1, v2 = st.columns(2)
        with v1:
            st.markdown('<div class="chart-container"><div class="chart-title">OpenBull IV Smile (Volatility Skew Profile)</div>', unsafe_allow_html=True)
            fig_smile = go.Figure()
            fig_smile.add_trace(go.Scatter(x=df_filtered["Strike"], y=df_filtered["PE_IV"], mode="lines+markers", name="Put IV", line=dict(color="#29B6F6", width=2)))
            fig_smile.add_trace(go.Scatter(x=df_filtered["Strike"], y=df_filtered["CE_IV"], mode="lines+markers", name="Call IV", line=dict(color="#FF5252", width=2)))
            fig_smile.add_vline(x=spot_price, line_dash="solid", line_color="#FFD700")
            fig_smile.update_xaxes(tickmode='array', tickvals=df_filtered["Strike"], ticktext=strike_labels)
            st.plotly_chart(apply_dark_layout(fig_smile), use_container_width=True, key="c_smile")
            st.markdown('</div>', unsafe_allow_html=True)
        with v2:
            st.markdown('<div class="chart-container"><div class="chart-title">OpenBull Max Pain Pinning Profile</div>', unsafe_allow_html=True)
            fig_pain = go.Figure()
            if not df_pain.empty:
                fig_pain.add_trace(go.Bar(x=df_pain["Strike"], y=df_pain["Writer_Loss"], marker_color="#8A93A6", name="Writer Loss"))
                fig_pain.add_vline(x=spot_price, line_dash="solid", line_color="#FFD700")
                fig_pain.add_vline(x=max_pain_strike, line_dash="dash", line_color="#29B6F6", annotation_text=f"Max Pain: {max_pain_strike}")
            fig_pain.update_xaxes(tickmode='array', tickvals=df_filtered["Strike"], ticktext=strike_labels)
            st.plotly_chart(apply_dark_layout(fig_pain), use_container_width=True, key="c_pain")
            st.markdown('</div>', unsafe_allow_html=True)

        v3, v4 = st.columns(2)
        df_vol_struct, df_surface = fetch_multi_expiry_vol_structure(spot_price)
        with v3:
            st.markdown('<div class="chart-container"><div class="chart-title">Forward Vol Term Structure (4 Expiries)</div>', unsafe_allow_html=True)
            if not df_vol_struct.empty and len(df_vol_struct) >= 2:
                fig_fwd = go.Figure()
                fig_fwd.add_trace(go.Scatter(x=df_vol_struct["Expiry"], y=df_vol_struct["Forward_Vol"], mode="lines+markers", name="Forward Vol", line=dict(color="#00E676", width=2.5)))
                fig_fwd.add_trace(go.Scatter(x=df_vol_struct["Expiry"], y=df_vol_struct["Mean_IV"], mode="lines+markers", name="Mean IV", line=dict(color="#AB47BC", width=2.5, dash="dot")))
                st.plotly_chart(apply_dark_layout(fig_fwd), use_container_width=True, key="c_fwd")
            else: st.info("Loading 4 expiries to build term structure... (Takes ~5 seconds)")
            st.markdown('</div>', unsafe_allow_html=True)
        with v4:
            st.markdown('<div class="chart-container"><div class="chart-title">OpenBull 3D Volatility Surface</div>', unsafe_allow_html=True)
            if not df_surface.empty:
                pivot_surface = df_surface.pivot_table(index='Days', columns='Strike', values='IV', aggfunc='mean').ffill(axis=1).bfill(axis=1).fillna(0)
                fig_surf = go.Figure(data=[go.Surface(z=pivot_surface.values, x=pivot_surface.columns.tolist(), y=pivot_surface.index.tolist(), colorscale='Viridis', showscale=False)])
                fig_surf.update_layout(scene=dict(xaxis_title='Strike', yaxis_title='Days to Expiry', zaxis_title='Implied Vol'), template="plotly_dark", margin=dict(l=0,r=0,t=0,b=0), height=300)
                st.plotly_chart(fig_surf, use_container_width=True, key="c_surf")
            else: st.info("Loading Expiries for 3D Surface... (Requires 4 active chains)")
            st.markdown('</div>', unsafe_allow_html=True)

    with tab5: # DATA GRID
        st.markdown('<div class="chart-container"><div class="chart-title">Institutional Options Chain Grid</div>', unsafe_allow_html=True)
        grid_df = df_filtered[["Strike", "CE_LTP", "PE_LTP", "CE_OI", "PE_OI", "CE_OI_Chg", "PE_OI_Chg", "CE_Delta", "PE_Delta", "Net_Delta_OI", "Net_DEX", "Net_GEX", "Net_VEX", "Net_CHEX", "Net_SPEX", "CE_IV", "PE_IV", "IV_Spread"]].copy()
        st.dataframe(grid_df.style.format({"Strike": "{:.0f}", "CE_LTP": "₹{:.2f}", "PE_LTP": "₹{:.2f}", "CE_OI": "{:,.0f}", "PE_OI": "{:,.0f}", "CE_OI_Chg": "{:,.0f}", "PE_OI_Chg": "{:,.0f}", "CE_Delta": "{:.2f}", "PE_Delta": "{:.2f}", "Net_Delta_OI": "{:+,.0f}", "Net_DEX": "{:+,.1f}L", "Net_GEX": "{:+,.1f}L", "Net_VEX": "{:+,.2f}", "Net_CHEX": "{:+,.2f}", "Net_SPEX": "{:+,.2f}", "CE_IV": "{:.1f}%", "PE_IV": "{:.1f}%", "IV_Spread": "{:+.2f}%"}), use_container_width=True, height=500)
        st.markdown('</div>', unsafe_allow_html=True)
