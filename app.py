import datetime
import math
import time
import os
import threading
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
import streamlit as st
from streamlit_autorefresh import st_autorefresh

# Graceful fallbacks
try:
    from dhanhq import marketfeed
    DHAN_WS_AVAILABLE = True
except ImportError:
    DHAN_WS_AVAILABLE = False

try:
    import yfinance as yf
    YF_AVAILABLE = True
except ImportError:
    YF_AVAILABLE = False

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
    /* Mobile Scroll Fix & Master CSS */
    html, body { overflow-x: hidden; -webkit-overflow-scrolling: touch; }
    .stApp { background-color: #0A0A0A; color: #D1D4DC; font-family: 'Inter', sans-serif; overflow-x: hidden; }
    section[data-testid="stSidebar"] { background-color: #111115 !important; border-right: 1px solid #2A2E39; }
    
    .metric-card {
        background: #14151A; border: 1px solid #2A2E39; border-radius: 6px; padding: 10px 14px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.5); margin-bottom: 12px; border-top: 3px solid #3B4252;
        position: relative; overflow: visible !important;
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
        background: #14151A; border: 1px solid #2A2E39; border-radius: 6px; padding: 12px;
        margin-bottom: 16px; position: relative; overflow: visible !important;
    }
    .chart-title {
        font-size: 0.85rem; font-weight: 700; color: #8A93A6; text-transform: uppercase;
        margin-bottom: 10px; border-bottom: 1px solid #2A2E39; padding-bottom: 5px;
    }

    .interp-box {
        background-color: #121824; border-left: 3px solid #29B6F6; padding: 6px 10px;
        font-size: 0.75rem; color: #D1D4DC; margin-bottom: 8px; border-radius: 0 4px 4px 0; line-height: 1.3;
    }

    .info-tooltip { position: relative; display: inline-block; cursor: help; color: #8A93A6; float: right; margin-left: 5px; font-size: 0.9rem; z-index: 999999; }
    .info-tooltip .tooltip-text {
        visibility: hidden; width: 260px; background-color: #1E2638; color: #E0E6ED; text-align: left;
        border-radius: 6px; padding: 10px 14px; position: absolute; top: 140%; right: -10px;
        opacity: 0; transition: opacity 0.2s; border: 1px solid #3B4252; font-size: 0.75rem;
        font-weight: 500; box-shadow: 0px 4px 15px rgba(0,0,0,0.8); line-height: 1.4;
    }
    .info-tooltip .tooltip-text::after { content: ""; position: absolute; bottom: 100%; right: 15px; border-width: 6px; border-style: solid; border-color: transparent transparent #3B4252 transparent; }
    .info-tooltip:hover .tooltip-text { visibility: visible; opacity: 1; }
    .info-tooltip:hover { color: #FFFFFF; }

    .status-badge { padding: 4px 10px; border-radius: 4px; font-weight: 700; font-size: 0.75rem; display: inline-block; margin-right: 10px; }
    .status-live { background-color: rgba(0, 230, 118, 0.15); border: 1px solid #00E676; color: #00E676; }
    .status-closed { background-color: rgba(255, 167, 38, 0.15); border: 1px solid #FFA726; color: #FFA726; }
    
    div[data-testid="stTabs"] button { color: #8A93A6; font-weight: 600; font-size: 0.9rem; }
    div[data-testid="stTabs"] button[aria-selected="true"] { color: #00E676; border-bottom-color: #00E676; }

    .buildup-table { width: 100%; border-collapse: collapse; font-size: 0.8rem; text-align: right; }
    .buildup-table th { background-color: #1e2638; color: #8b9bb4; padding: 6px; border: 1px solid #2A2E39; text-align: right;}
    .buildup-table th.center { text-align: center; }
    .buildup-table td { padding: 6px; border: 1px solid #2A2E39; color: #D1D4DC; }
    .row-atm { background-color: rgba(41, 182, 246, 0.15); border-left: 3px solid #29B6F6;}
    .tag-badge { padding: 3px 6px; border-radius: 4px; font-weight: 700; font-size: 0.7rem; display: inline-block; text-align: center; width: 100px;}
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------
# 2. CONFIGURATION & SECRETS
# ---------------------------------------------------------
CLIENT_ID = str(st.secrets.get("DHAN_CLIENT_ID", "")).strip().replace('"', "").replace("'", "")
ACCESS_TOKEN = str(st.secrets.get("DHAN_ACCESS_TOKEN", "")).strip().replace('"', "").replace("'", "")
TELEGRAM_BOT_TOKEN = str(st.secrets.get("TELEGRAM_BOT_TOKEN", "")).strip().replace('"', "").replace("'", "")
TELEGRAM_CHAT_ID = str(st.secrets.get("TELEGRAM_CHAT_ID", "")).strip().replace('"', "").replace("'", "")

if not CLIENT_ID or not ACCESS_TOKEN:
    st.error("⚠️ API credentials missing. Please update your Streamlit Secrets.")
    st.stop()

# 2026 LOT SIZE UPDATED TO 65
NIFTY_LOT_SIZE = 65

NIFTY_50_WEIGHTS = {
    "HDFCBANK.NS": 11.6, "RELIANCE.NS": 9.8, "ICICIBANK.NS": 7.9, "INFY.NS": 5.8, "ITC.NS": 4.5,
    "TCS.NS": 4.1, "LT.NS": 3.4, "AXISBANK.NS": 3.2, "KOTAKBANK.NS": 2.8, "SBIN.NS": 2.7,
    "BHARTIARTL.NS": 2.6, "HINDUNILVR.NS": 2.4, "BAJFINANCE.NS": 2.1, "MARUTI.NS": 1.8, "ASIANPAINT.NS": 1.7,
    "M&M.NS": 1.6, "SUNPHARMA.NS": 1.5, "TITAN.NS": 1.5, "HCLTECH.NS": 1.4, "TATASTEEL.NS": 1.3,
    "NTPC.NS": 1.3, "ULTRACEMCO.NS": 1.1, "TATAMOTORS.NS": 1.1, "INDUSINDBK.NS": 1.1, "POWERGRID.NS": 1.0,
    "NESTLEIND.NS": 1.0, "BAJAJFINSV.NS": 1.0, "ONGC.NS": 0.9, "GRASIM.NS": 0.9, "JSWSTEEL.NS": 0.8,
    "TECHM.NS": 0.8, "HINDALCO.NS": 0.8, "ADANIPORTS.NS": 0.8, "WIPRO.NS": 0.7, "COALINDIA.NS": 0.7,
    "DRREDDY.NS": 0.7, "CIPLA.NS": 0.6, "EICHERMOT.NS": 0.6, "APOLLOHOSP.NS": 0.6, "TATACHEM.NS": 0.5,
    "DIVISLAB.NS": 0.5, "BRITANNIA.NS": 0.5, "BAJAJ-AUTO.NS": 0.5, "HEROMOTOCO.NS": 0.4, "SBILIFE.NS": 0.4,
    "LTIM.NS": 0.4, "HDFCLIFE.NS": 0.4, "TATACONSUM.NS": 0.4, "UPL.NS": 0.3, "SHREECEM.NS": 0.3
}

# Plotly config optimized for Mobile Scrolling
PLOT_CONFIG = {'displayModeBar': True, 'scrollZoom': False}

# ---------------------------------------------------------
# 3. HELPERS & ALERTS
# ---------------------------------------------------------
def apply_dark_layout(fig, height=250, is_strike_axis=False, df_filtered=None, atm_strike=None):
    fig.update_layout(
        template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=5, r=5, t=10, b=5), height=height, legend=dict(orientation="h", y=1.1, x=0, font=dict(size=10))
    )
    if is_strike_axis and df_filtered is not None and not df_filtered.empty and atm_strike is not None:
        strike_labels = df_filtered["Strike"].astype(str).tolist()
        fig.update_xaxes(tickmode='array', tickvals=df_filtered["Strike"], ticktext=strike_labels, tickangle=-45, gridcolor="#2A2E39", zerolinecolor="#2A2E39", tickfont=dict(size=10, color="#D1D4DC"))
    else:
        fig.update_xaxes(gridcolor="#2A2E39", zerolinecolor="#2A2E39", tickfont=dict(size=10))
    fig.update_yaxes(gridcolor="#2A2E39", zerolinecolor="#2A2E39", tickfont=dict(size=10))
    return fig

def create_h_bar(title, put_val, call_val, interp_text="", interp_color="#8A93A6"):
    fig = go.Figure()
    fig.add_trace(go.Bar(x=[put_val], y=[''], name='Put (PE)', orientation='h', marker_color="#FF5252", text=f"{put_val:,.0f}", textposition='inside', insidetextanchor='end'))
    fig.add_trace(go.Bar(x=[call_val], y=[''], name='Call (CE)', orientation='h', marker_color="#00E676", text=f"{call_val:,.0f}", textposition='inside', insidetextanchor='start'))
    fig.update_layout(
        title=dict(text=f"<b>{title}</b><br><span style='color:{interp_color}; font-size:10px; font-weight:700;'>{interp_text}</span>", font=dict(size=11, color="#8A93A6"), x=0.5, xanchor='center'),
        barmode='group', margin=dict(l=0, r=0, t=35, b=0), height=85, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", showlegend=False, xaxis=dict(visible=False), yaxis=dict(visible=False), bargap=0.2
    )
    return fig

def get_oi_build_status(dl_p, dl_oi, is_call):
    if is_call:
        if dl_p > 0 and dl_oi > 0: return "Long Buildup", "rgba(0, 230, 118, 0.15)", "#00E676", 1
        elif dl_p < 0 and dl_oi > 0: return "Short Buildup", "rgba(255, 82, 82, 0.15)", "#FF5252", -1
        elif dl_p > 0 and dl_oi < 0: return "Short Cover", "rgba(0, 230, 118, 0.15)", "#00E676", 1
        elif dl_p < 0 and dl_oi < 0: return "Long Unwind", "rgba(255, 82, 82, 0.15)", "#FF5252", -1
        else: return "Neutral", "rgba(138, 147, 166, 0.15)", "#8A93A6", 0
    else:
        if dl_p > 0 and dl_oi > 0: return "Long Buildup", "rgba(255, 82, 82, 0.15)", "#FF5252", -1
        elif dl_p < 0 and dl_oi > 0: return "Short Buildup", "rgba(0, 230, 118, 0.15)", "#00E676", 1
        elif dl_p > 0 and dl_oi < 0: return "Short Cover", "rgba(255, 82, 82, 0.15)", "#FF5252", -1
        elif dl_p < 0 and dl_oi < 0: return "Long Unwind", "rgba(0, 230, 118, 0.15)", "#00E676", 1
        else: return "Neutral", "rgba(138, 147, 166, 0.15)", "#8A93A6", 0

def send_telegram_alert(message: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID: return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try: requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}, timeout=3)
    except: pass

def process_camarilla_alerts(df_camarilla, is_market_live, today_date_str):
    if not is_market_live: return
    if "telegram_cooldowns" not in st.session_state: st.session_state["telegram_cooldowns"] = {}
    
    for _, row in df_camarilla.iterrows():
        sym = row["Symbol"]
        w = row["Weight"]
        ltp = row["LTP"]
        
        # 1 Alert per day per level per stock
        if row["Dist_S3_%"] <= 0.15:
            key = f"{sym}_S3"
            if st.session_state["telegram_cooldowns"].get(key) != today_date_str:
                msg = f"🟢 *CAMARILLA S3 TESTED*\n\n*Stock:* `{sym}` (Weight: {w}%)\n*LTP:* ₹{ltp:,.2f} | *S3:* ₹{row['S3']:,.2f}\n*Distance:* `{row['Dist_S3_%']:.2f}%`\n\n⚡ *Nifty Support / Rebound Candidate*"
                send_telegram_alert(msg)
                st.session_state["telegram_cooldowns"][key] = today_date_str
                
        elif row["Dist_R3_%"] <= 0.15:
            key = f"{sym}_R3"
            if st.session_state["telegram_cooldowns"].get(key) != today_date_str:
                msg = f"🔴 *CAMARILLA R3 TESTED*\n\n*Stock:* `{sym}` (Weight: {w}%)\n*LTP:* ₹{ltp:,.2f} | *R3:* ₹{row['R3']:,.2f}\n*Distance:* `{row['Dist_R3_%']:.2f}%`\n\n⚠️ *Nifty Resistance / Rejection Candidate*"
                send_telegram_alert(msg)
                st.session_state["telegram_cooldowns"][key] = today_date_str

# ---------------------------------------------------------
# 4. YFINANCE & MEMORY ENGINES 
# ---------------------------------------------------------
@st.cache_data(ttl=60)
def get_nifty50_camarilla():
    if not YF_AVAILABLE: return pd.DataFrame()
    tickers = list(NIFTY_50_WEIGHTS.keys())
    try:
        data = yf.download(tickers, period="5d", interval="1d", group_by='ticker', auto_adjust=False, progress=False)
    except Exception:
        return pd.DataFrame(columns=["Symbol", "Weight", "LTP", "S3", "R3", "Dist_S3_%", "Dist_R3_%"])
    
    records = []
    today = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30))).date()
    
    for ticker in tickers:
        try:
            df_t = data[ticker].dropna() if isinstance(data.columns, pd.MultiIndex) else data.dropna()
            if len(df_t) >= 2:
                last_date = df_t.index[-1].date()
                prev_idx = -2 if last_date == today else -1
                
                prev_h = df_t.iloc[prev_idx]['High']
                prev_l = df_t.iloc[prev_idx]['Low']
                prev_c = df_t.iloc[prev_idx]['Close']
                ltp = df_t.iloc[-1]['Close']
                
                r_hl = prev_h - prev_l
                r3 = prev_c + (r_hl * 1.1 / 4)
                s3 = prev_c - (r_hl * 1.1 / 4)
                records.append({
                    "Symbol": ticker.replace(".NS", ""), "Weight": NIFTY_50_WEIGHTS[ticker],
                    "LTP": float(ltp), "S3": float(s3), "R3": float(r3),
                    "Dist_S3_%": float(abs(ltp - s3) / s3 * 100), "Dist_R3_%": float(abs(ltp - r3) / r3 * 100)
                })
        except: pass
    df_cam = pd.DataFrame(records)
    if not df_cam.empty and "Weight" in df_cam.columns: return df_cam.sort_values("Weight", ascending=False)
    return pd.DataFrame(columns=["Symbol", "Weight", "LTP", "S3", "R3", "Dist_S3_%", "Dist_R3_%"])

def get_persisted_df(name, cols):
    if os.path.exists(f"{name}.csv"):
        try:
            df = pd.read_csv(f"{name}.csv")
            if set(cols).issubset(df.columns): return df
        except: pass
    return pd.DataFrame(columns=cols)

def save_persisted_df(df, name):
    try: df.to_csv(f"{name}.csv", index=False)
    except: pass

def check_and_reset(df_name, cols, today_date_str, now_time_str):
    df = get_persisted_df(df_name, cols)
    if not df.empty and str(df.iloc[-1]["Date"]) != today_date_str and now_time_str >= "09:15:00":
        df = pd.DataFrame(columns=cols)
        save_persisted_df(df, df_name)
    return df

# ---------------------------------------------------------
# 5. BLACK-SCHOLES GREEK ENGINE (Nifty 65 Precision)
# ---------------------------------------------------------
def calculate_bs_greeks(S, K, T, sigma, r=0.07):
    if T <= 1e-5 or sigma <= 1e-4 or S <= 0 or K <= 0: return 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
    try:
        d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        pdf_d1 = (1.0 / math.sqrt(2 * math.pi)) * math.exp(-0.5 * d1 * d1)
        ce_delta = 0.5 * (1.0 + math.erf(d1 / math.sqrt(2.0)))
        return ce_delta, ce_delta - 1.0, pdf_d1 / (S * sigma * math.sqrt(T)), -pdf_d1 * d2 / sigma, -pdf_d1 * (2 * r * math.sqrt(T) - d2 * sigma) / (2 * T * sigma), (-pdf_d1 / (S * sigma * math.sqrt(T))) / S * (1 + d1 / (sigma * math.sqrt(T)))
    except: return 0.0, 0.0, 0.0, 0.0, 0.0, 0.0

# ---------------------------------------------------------
# 6. DATA API ENGINE
# ---------------------------------------------------------
def fetch_gex_option_chain_raw(expiry_date):
    url = "https://api.dhan.co/v2/optionchain"
    headers = {"client-id": CLIENT_ID, "access-token": ACCESS_TOKEN, "Content-Type": "application/json"}
    try:
        res = requests.post(url, headers=headers, json={"UnderlyingScrip": 13, "UnderlyingSeg": "IDX_I", "Expiry": expiry_date}, timeout=10)
        data = res.json()
        if res.status_code == 200 and data.get("status") == "success":
            spot_price = float(data.get("data", {}).get("last_price", 0.0))
            oc_raw = data.get("data", {}).get("oc", {})
            if not oc_raw: return None, spot_price, f"No contracts returned."

            # Robust date parsing
            try:
                exp_date_obj = pd.to_datetime(expiry_date[:10], dayfirst=True).date()
            except:
                exp_date_obj = datetime.date.today() + datetime.timedelta(days=1)
                
            T_years = max((exp_date_obj - datetime.date.today()).days, 1) / 365.0
            records = []
            
            for strike_str, details in oc_raw.items():
                strike = int(float(strike_str))
                ce, pe = details.get("ce", {}), details.get("pe", {})
                
                # Fetch Current OI
                ce_oi, pe_oi = float(ce.get("oi", 0)), float(pe.get("oi", 0))
                # Fetch Previous Day OI to reliably calculate OI Change
                ce_prev_val, pe_prev_val = ce.get("previous_oi"), pe.get("previous_oi")
                ce_prev_oi = float(ce_prev_val) if ce_prev_val is not None else ce_oi
                pe_prev_oi = float(pe_prev_val) if pe_prev_val is not None else pe_oi
                
                ce_oichg = ce_oi - ce_prev_oi
                pe_oichg = pe_oi - pe_prev_oi

                ce_vol, pe_vol = float(ce.get("volume") or 0.0), float(pe.get("volume") or 0.0)
                ce_ltp, pe_ltp = float(ce.get("last_price", 0)), float(pe.get("last_price", 0))
                ce_iv, pe_iv = float(ce.get("implied_volatility", 0))/100.0, float(pe.get("implied_volatility", 0))/100.0

                ce_delta, _, ce_gamma, ce_vanna, ce_charm, ce_speed = calculate_bs_greeks(spot_price, strike, T_years, max(ce_iv, 0.01))
                _, pe_delta, pe_gamma, pe_vanna, pe_charm, pe_speed = calculate_bs_greeks(spot_price, strike, T_years, max(pe_iv, 0.01))

                call_gex = ce_oi * NIFTY_LOT_SIZE * ce_gamma * (spot_price**2) * 0.01 / 1e5
                put_gex = -pe_oi * NIFTY_LOT_SIZE * pe_gamma * (spot_price**2) * 0.01 / 1e5
                ce_dex = ce_oi * NIFTY_LOT_SIZE * ce_delta * spot_price / 1e5
                pe_dex = pe_oi * NIFTY_LOT_SIZE * pe_delta * spot_price / 1e5
                ce_vex = ce_oi * NIFTY_LOT_SIZE * ce_vanna * spot_price * 0.01 / 1e5
                pe_vex = pe_oi * NIFTY_LOT_SIZE * pe_vanna * spot_price * 0.01 / 1e5
                ce_chex = ce_oi * NIFTY_LOT_SIZE * ce_charm * (1.0/365.0) * spot_price / 1e5
                pe_chex = pe_oi * NIFTY_LOT_SIZE * pe_charm * (1.0/365.0) * spot_price / 1e5
                ce_spex = ce_oi * NIFTY_LOT_SIZE * ce_speed * (spot_price**3) * 0.0001 / 1e5
                pe_spex = pe_oi * NIFTY_LOT_SIZE * pe_speed * (spot_price**3) * 0.0001 / 1e5

                records.append({
                    "Strike": strike, "CE_LTP": ce_ltp, "PE_LTP": pe_ltp, "CE_OI": ce_oi, "PE_OI": pe_oi, 
                    "CE_OI_Chg": ce_oichg, "PE_OI_Chg": pe_oichg, "CE_Vol": ce_vol, "PE_Vol": pe_vol,
                    "CE_Delta": ce_delta, "PE_Delta": pe_delta, "Net_Delta_OI": (ce_oi * ce_delta) + (pe_oi * pe_delta),
                    "Net_DEX": ce_dex + pe_dex, "ABS_DEX": ce_dex + abs(pe_dex),
                    "Call_GEX": call_gex, "Put_GEX": put_gex, "Net_GEX": call_gex + put_gex, "ABS_GEX": call_gex + abs(put_gex),
                    "CE_VEX": ce_vex, "PE_VEX": pe_vex, "Net_VEX": ce_vex - pe_vex, 
                    "CE_CHEX": ce_chex, "PE_CHEX": pe_chex, "Net_CHEX": ce_chex - pe_chex,
                    "CE_SPEX": ce_spex, "PE_SPEX": pe_spex, "Net_SPEX": ce_spex - pe_spex,
                    "CE_IV": ce_iv * 100.0, "PE_IV": pe_iv * 100.0, "IV_Spread": (ce_iv * 100.0) - (pe_iv * 100.0),
                })
            return pd.DataFrame(records).sort_values("Strike").reset_index(drop=True), spot_price, None
        else: return None, 0.0, str(data.get("remarks") or data.get("message") or f"HTTP {res.status_code}")
    except Exception as e: return None, 0.0, f"Connection Error: {str(e)}"

@st.cache_data(ttl=3)
def fetch_gex_option_chain(expiry_date):
    return fetch_gex_option_chain_raw(expiry_date)

@st.cache_data(ttl=120, show_spinner=False)
def fetch_multi_expiry_vol_structure(spot_price, valid_exp_list):
    vol_data, surface_data = [], []
    for idx, exp in enumerate(valid_exp_list):
        if idx > 0: time.sleep(3.2) # Hard lock 3.2s to bypass Dhan rate limits
        df_exp, exp_spot, _ = fetch_gex_option_chain_raw(exp)
        if df_exp is not None and not df_exp.empty:
            temp_spot_atm = int(round(exp_spot / 50) * 50)
            temp_row = df_exp[df_exp["Strike"] == temp_spot_atm]
            exp_synth = temp_spot_atm + temp_row["CE_LTP"].values[0] - temp_row["PE_LTP"].values[0] if not temp_row.empty else exp_spot
            exp_atm = int(round(exp_synth / 50) * 50)
            atm_row = df_exp[df_exp["Strike"] == exp_atm]
            mean_iv = ( (atm_row["CE_IV"].values[0] if not atm_row.empty else df_exp["CE_IV"].mean()) + (atm_row["PE_IV"].values[0] if not atm_row.empty else df_exp["PE_IV"].mean()) ) / 2.0
            
            # Flawless Date Parser
            try: exp_date_obj = pd.to_datetime(exp[:10], dayfirst=True).date()
            except: continue
            
            days = max((exp_date_obj - datetime.date.today()).days, 1)

            vol_data.append({"Expiry": exp_date_obj.strftime("%d %b"), "Days": days, "Tenor_Years": days / 365.0, "Mean_IV": max(mean_iv, 0.01)})
            for _, r in df_exp.iterrows():
                if exp_atm - 600 <= r["Strike"] <= exp_atm + 600: surface_data.append({"Expiry": exp, "Days": days, "Strike": r["Strike"], "IV": (r["CE_IV"] + r["PE_IV"]) / 2.0})

    df_vol, df_surf = pd.DataFrame(vol_data), pd.DataFrame(surface_data)
    if not df_vol.empty and len(df_vol) > 1:
        df_vol = df_vol.sort_values("Tenor_Years").reset_index(drop=True)
        fwd_vols = [df_vol.loc[0, "Mean_IV"]]
        for i in range(1, len(df_vol)):
            t1, t2, v1, v2 = df_vol.loc[i-1, "Tenor_Years"], df_vol.loc[i, "Tenor_Years"], df_vol.loc[i-1, "Mean_IV"]/100.0, df_vol.loc[i, "Mean_IV"]/100.0
            var_diff, dt = (v2**2 * t2) - (v1**2 * t1), t2 - t1
            fwd_vols.append(math.sqrt(max(var_diff, 0) / dt) * 100.0 if dt > 0 else v2 * 100.0)
        df_vol["Forward_Vol"] = fwd_vols
    return df_vol, df_surf

# BACKGROUND DAEMON
@st.cache_resource
def start_background_daemon(selected_expiry_daemon):
    def daemon_loop():
        while True:
            now_ist = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
            m_open, m_close = now_ist.replace(hour=9, minute=15, second=0, microsecond=0), now_ist.replace(hour=15, minute=30, second=0, microsecond=0)
            is_live = now_ist.weekday() < 5 and (m_open <= now_ist <= m_close)
            
            if is_live:
                try:
                    df_oc, spot_pr, _ = fetch_gex_option_chain_raw(selected_expiry_daemon)
                    if df_oc is not None and not df_oc.empty:
                        now_ts = int(time.time())
                        today_str = now_ist.strftime("%Y-%m-%d")
                        
                        # Mathematically perfect future anchor
                        synth_fut = spot_pr
                        spot_a = int(round(spot_pr / 50) * 50)
                        row_a = df_oc[df_oc["Strike"] == spot_a]
                        if not row_a.empty: synth_fut = spot_a + row_a["CE_LTP"].values[0] - row_a["PE_LTP"].values[0]

                        abs_df = get_persisted_df("absorption_history", ["Date", "Timestamp", "Spot", "Fut_LTP", "CE_OI", "PE_OI", "CE_Vol", "PE_Vol"])
                        if abs_df.empty or (now_ts - abs_df["Timestamp"].max() >= 60):
                            new_abs = pd.DataFrame([{"Date": today_str, "Timestamp": now_ts, "Spot": spot_pr, "Fut_LTP": synth_fut, "CE_OI": df_oc["CE_OI"].sum(), "PE_OI": df_oc["PE_OI"].sum(), "CE_Vol": df_oc["CE_Vol"].sum(), "PE_Vol": df_oc["PE_Vol"].sum()}])
                            save_persisted_df(pd.concat([abs_df, new_abs], ignore_index=True), "absorption_history")
                        
                        oi_snap = get_persisted_df("oi_snapshots", ["Date", "Timestamp", "Strike", "CE_OI", "PE_OI", "CE_LTP", "PE_LTP"])
                        if oi_snap.empty or (now_ts - oi_snap["Timestamp"].max() >= 60):
                            new_snap = df_oc[["Strike", "CE_OI", "PE_OI", "CE_LTP", "PE_LTP"]].copy()
                            new_snap["Timestamp"] = now_ts; new_snap["Date"] = today_str
                            save_persisted_df(pd.concat([oi_snap, new_snap], ignore_index=True), "oi_snapshots")
                except: pass
            time.sleep(60) 
    
    threading.Thread(target=daemon_loop, daemon=True).start()
    return True

# ---------------------------------------------------------
# 7. SESSION & LIVE ENGINE INITIALIZATION
# ---------------------------------------------------------
st.sidebar.header("⚙️ Command Center")

now_ist = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
today_date_str, now_time_str = now_ist.strftime("%Y-%m-%d"), now_ist.strftime("%H:%M:%S")
m_open, m_close = now_ist.replace(hour=9, minute=15, second=0, microsecond=0), now_ist.replace(hour=15, minute=30, second=0, microsecond=0)
is_market_live = now_ist.weekday() < 5 and (m_open <= now_ist <= m_close)

auto_refresh = st.sidebar.checkbox("Live Auto-Refresh (5s)", value=True)
if auto_refresh and is_market_live: st_autorefresh(interval=5000, key="datarefresh")
elif not is_market_live: st.sidebar.info("Market Closed. Dashboard in Static Review Mode.")

try: valid_expiries = requests.post("https://api.dhan.co/v2/optionchain/expirylist", headers={"client-id": CLIENT_ID, "access-token": ACCESS_TOKEN, "Content-Type": "application/json"}, json={"UnderlyingScrip": 13, "UnderlyingSeg": "IDX_I"}, timeout=5).json().get("data", [])
except: valid_expiries = []
selected_expiry = st.sidebar.selectbox("Primary Expiry", valid_expiries) if valid_expiries else st.sidebar.date_input("Primary Expiry").strftime("%Y-%m-%d")

daemon_running = start_background_daemon(selected_expiry)

df_oc, spot_price, error_remark = fetch_gex_option_chain(selected_expiry)

for key, cols in [
    ("absorption_history", ["Date", "Timestamp", "Spot", "Fut_LTP", "CE_OI", "PE_OI", "CE_Vol", "PE_Vol"]),
    ("oi_snapshots", ["Date", "Timestamp", "Strike", "CE_OI", "PE_OI", "CE_LTP", "PE_LTP"]),
    ("iv_spread_history", ["Date", "Time", "Strike", "CE_IV", "PE_IV", "IV_Spread", "Spot"]),
    ("pcr_history", ["Date", "Timestamp_dt", "Time", "PCR", "Vol_PCR", "Delta_PCR_5m", "Delta_PCR_15m", "Total_CE_OI", "Total_PE_OI"]),
    ("gex_history", ["Date", "Timestamp_dt", "Time", "Total_Net_GEX", "Z_GEX", "Flip_Strike", "Spot"]),
    ("synth_history", ["Date", "Time", "Spot", "Strike_M50", "Strike_ATM", "Strike_P50", "Synth_M50", "Synth_ATM", "Synth_P50", "PCP_Dev_Mean"]),
    ("delta_oi_history", ["Date", "Timestamp_dt", "Time", "Total_Net_Delta_OI", "Delta_OI_ROC_1m", "Total_Net_DEX", "DEX_Vel_5m"]),
    ("straddle_history", ["Date", "Time", "Elapsed_Mins", "Actual_Straddle", "Expected_Straddle", "Regime", "Straddle_VWAP"])
]:
    if key not in st.session_state: st.session_state[key] = check_and_reset(key, cols, today_date_str, now_time_str)

if "straddle_anchor_price" not in st.session_state: st.session_state["straddle_anchor_price"] = None

if st.sidebar.button("🗑️ Reset Session Cache"):
    for key in ["absorption_history", "oi_snapshots", "iv_spread_history", "pcr_history", "gex_history", "synth_history", "delta_oi_history", "straddle_history"]:
        st.session_state[key] = pd.DataFrame(columns=st.session_state[key].columns)
    st.session_state["straddle_anchor_price"] = None
    st.cache_data.clear(); st.rerun()

# ---------------------------------------------------------
# 8. QUARANTINED UI RENDERING BLOCK
# ---------------------------------------------------------
st.markdown(f"### PRINCE PAX DASHBOARD")
st.markdown(f'<div class="status-badge {"status-live" if is_market_live else "status-closed"}">{"🟢 LIVE MARKET" if is_market_live else "🟠 MARKET CLOSED"} | Expiry: {selected_expiry} | IST: {now_time_str}</div>', unsafe_allow_html=True)
st.markdown("<br>", unsafe_allow_html=True)

if error_remark: 
    st.error(f"⚠️ Dhan API Error: {error_remark} - Waiting for next refresh tick...")
elif df_oc is None or df_oc.empty:
    st.warning("⚠️ API returned empty data. Rate limit or connection issue. Waiting for next tick...")
else:
    # --- CORE DATA PROCESSING ---
    synthetic_future = spot_price
    spot_atm = int(round(spot_price / 50) * 50)
    row_atm = df_oc[df_oc["Strike"] == spot_atm]
    if not row_atm.empty: synthetic_future = spot_atm + row_atm["CE_LTP"].values[0] - row_atm["PE_LTP"].values[0]

    atm_strike = int(round(synthetic_future / 50) * 50)
    strike_m50, strike_p50 = atm_strike - 50, atm_strike + 50

    selected_target_strike = st.sidebar.selectbox("🎯 Target Strike", df_oc["Strike"].tolist(), index=df_oc["Strike"].tolist().index(atm_strike) if atm_strike in df_oc["Strike"].tolist() else 0)

    df_sorted = df_oc.sort_values("Strike").copy()
    df_sorted["Cum_Net_GEX"] = df_sorted["Net_GEX"].cumsum()
    gamma_flip_strike = int(spot_price)
    for i in range(1, len(df_sorted)):
        if (df_sorted.iloc[i-1]["Cum_Net_GEX"] < 0 and df_sorted.iloc[i]["Cum_Net_GEX"] >= 0) or (df_sorted.iloc[i-1]["Cum_Net_GEX"] > 0 and df_sorted.iloc[i]["Cum_Net_GEX"] <= 0):
            gamma_flip_strike = int((df_sorted.iloc[i-1]["Strike"] + df_sorted.iloc[i]["Strike"]) / 2.0)
            break

    df_filtered = df_oc[(df_oc["Strike"] >= atm_strike - 550) & (df_oc["Strike"] <= atm_strike + 550)].copy()

    total_ce_oi_sum = df_oc["CE_OI"].sum()
    total_pe_oi_sum = df_oc["PE_OI"].sum()
    now_ts = int(time.time())

    # Update Memory Only When Valid
    if is_market_live:
        abs_df = st.session_state["absorption_history"]
        if abs_df.empty or (now_ts - abs_df["Timestamp"].max() >= 60):
            new_abs = pd.DataFrame([{"Date": today_date_str, "Timestamp": now_ts, "Spot": spot_price, "Fut_LTP": synthetic_future, "CE_OI": total_ce_oi_sum, "PE_OI": total_pe_oi_sum, "CE_Vol": df_oc["CE_Vol"].sum(), "PE_Vol": df_oc["PE_Vol"].sum()}])
            st.session_state["absorption_history"] = pd.concat([abs_df, new_abs], ignore_index=True)
            save_persisted_df(st.session_state["absorption_history"], "absorption_history")

        oi_snap = st.session_state["oi_snapshots"]
        if oi_snap.empty or (now_ts - oi_snap["Timestamp"].max() >= 60):
            new_snap = df_oc[["Strike", "CE_OI", "PE_OI", "CE_LTP", "PE_LTP"]].copy()
            new_snap["Timestamp"] = now_ts; new_snap["Date"] = today_date_str
            st.session_state["oi_snapshots"] = pd.concat([oi_snap, new_snap], ignore_index=True)
            save_persisted_df(st.session_state["oi_snapshots"], "oi_snapshots")

        iv_hist = st.session_state["iv_spread_history"]
        if iv_hist.empty or str(iv_hist.iloc[-1]["Time"]) != now_time_str:
            new_ticks = [{"Date": today_date_str, "Time": now_time_str, "Strike": r["Strike"], "CE_IV": r["CE_IV"], "PE_IV": r["PE_IV"], "IV_Spread": r["IV_Spread"], "Spot": spot_price} for _, r in df_filtered.iterrows()]
            st.session_state["iv_spread_history"] = pd.concat([iv_hist, pd.DataFrame(new_ticks)], ignore_index=True)
            save_persisted_df(st.session_state["iv_spread_history"], "iv_spread_history")
            
        pcr_df = st.session_state["pcr_history"]
        current_pcr = total_pe_oi_sum / total_ce_oi_sum if total_ce_oi_sum > 0 else 0.0
        vol_pcr = df_oc["PE_Vol"].sum() / df_oc["CE_Vol"].sum() if df_oc["CE_Vol"].sum() > 0 else 0.0
        if pcr_df.empty or str(pcr_df.iloc[-1]["Time"]) != now_time_str:
            dp_15m = current_pcr - pcr_df[pcr_df["Timestamp_dt"] <= now_ist - datetime.timedelta(minutes=15)].iloc[-1]["PCR"] if not pcr_df[pcr_df["Timestamp_dt"] <= now_ist - datetime.timedelta(minutes=15)].empty else 0.0
            st.session_state["pcr_history"] = pd.concat([pcr_df, pd.DataFrame([{"Date": today_date_str, "Timestamp_dt": now_ist, "Time": now_time_str, "PCR": current_pcr, "Vol_PCR": vol_pcr, "Delta_PCR_5m": 0.0, "Delta_PCR_15m": dp_15m, "Total_CE_OI": total_ce_oi_sum, "Total_PE_OI": total_pe_oi_sum}])], ignore_index=True)
            save_persisted_df(st.session_state["pcr_history"], "pcr_history")

        gex_df = st.session_state["gex_history"]
        if gex_df.empty or str(gex_df.iloc[-1]["Time"]) != now_time_str:
            z_gex = (df_oc["Net_GEX"].sum() - gex_df["Total_Net_GEX"].tail(20).mean()) / gex_df["Total_Net_GEX"].tail(20).std() if len(gex_df) >= 2 and gex_df["Total_Net_GEX"].tail(20).std() > 0 else 0.0
            st.session_state["gex_history"] = pd.concat([gex_df, pd.DataFrame([{"Date": today_date_str, "Timestamp_dt": now_ist, "Time": now_time_str, "Total_Net_GEX": df_oc["Net_GEX"].sum(), "Z_GEX": z_gex, "Flip_Strike": gamma_flip_strike, "Spot": spot_price}])], ignore_index=True)
            save_persisted_df(st.session_state["gex_history"], "gex_history")

        synth_df = st.session_state["synth_history"]
        if synth_df.empty or str(synth_df.iloc[-1]["Time"]) != now_time_str:
            r_m50, r_atm, r_p50 = df_oc[df_oc["Strike"] == strike_m50], df_oc[df_oc["Strike"] == atm_strike], df_oc[df_oc["Strike"] == strike_p50]
            s_m50 = strike_m50 + r_m50["CE_LTP"].values[0] - r_m50["PE_LTP"].values[0] if not r_m50.empty else spot_price
            s_atm = atm_strike + r_atm["CE_LTP"].values[0] - r_atm["PE_LTP"].values[0] if not r_atm.empty else spot_price
            s_p50 = strike_p50 + r_p50["CE_LTP"].values[0] - r_p50["PE_LTP"].values[0] if not r_p50.empty else spot_price
            st.session_state["synth_history"] = pd.concat([synth_df, pd.DataFrame([{"Date": today_date_str, "Time": now_time_str, "Spot": spot_price, "Strike_M50": strike_m50, "Strike_ATM": atm_strike, "Strike_P50": strike_p50, "Synth_M50": s_m50, "Synth_ATM": s_atm, "Synth_P50": s_p50, "PCP_Dev_Mean": ((s_m50 - spot_price) + (s_atm - spot_price) + (s_p50 - spot_price)) / 3.0}])], ignore_index=True)
            save_persisted_df(st.session_state["synth_history"], "synth_history")

        doi_df = st.session_state["delta_oi_history"]
        if doi_df.empty or str(doi_df.iloc[-1]["Time"]) != now_time_str:
            d_roc_1m = df_oc["Net_Delta_OI"].sum() - doi_df[doi_df["Timestamp_dt"] <= now_ist - datetime.timedelta(minutes=1)].iloc[-1]["Total_Net_Delta_OI"] if not doi_df[doi_df["Timestamp_dt"] <= now_ist - datetime.timedelta(minutes=1)].empty else 0.0
            dex_vel = (df_oc["Net_DEX"].sum()) - doi_df[doi_df["Timestamp_dt"] <= now_ist - datetime.timedelta(minutes=5)].iloc[-1]["Total_Net_DEX"] if not doi_df[doi_df["Timestamp_dt"] <= now_ist - datetime.timedelta(minutes=5)].empty else 0.0
            st.session_state["delta_oi_history"] = pd.concat([doi_df, pd.DataFrame([{"Date": today_date_str, "Timestamp_dt": now_ist, "Time": now_time_str, "Total_Net_Delta_OI": df_oc["Net_Delta_OI"].sum(), "Delta_OI_ROC_1m": d_roc_1m, "Total_Net_DEX": df_oc["Net_DEX"].sum(), "DEX_Vel_5m": dex_vel}])], ignore_index=True)
            save_persisted_df(st.session_state["delta_oi_history"], "delta_oi_history")

        strad_df = st.session_state["straddle_history"]
        if strad_df.empty or str(strad_df.iloc[-1]["Time"]) != now_time_str:
            r_atm_cur = df_oc[df_oc["Strike"] == atm_strike]
            c_strad = (r_atm_cur["CE_LTP"].values[0] if not r_atm_cur.empty else 0.0) + (r_atm_cur["PE_LTP"].values[0] if not r_atm_cur.empty else 0.0)
            e_mins = max(0, min((now_ist - m_open).total_seconds() / 60.0, 375)) 
            if e_mins >= 5.0 and st.session_state["straddle_anchor_price"] is None: st.session_state["straddle_anchor_price"] = c_strad
            e_strad = (st.session_state["straddle_anchor_price"] or c_strad) * (1 - (0.15 * math.sqrt(e_mins / 375)))
            prev_vwap = strad_df.iloc[-1]["Straddle_VWAP"] if not strad_df.empty and "Straddle_VWAP" in strad_df.columns else c_strad
            strad_vwap = ((prev_vwap * max(1, len(strad_df))) + c_strad) / (len(strad_df) + 1)
            regime = "VOL COIL 🟢" if c_strad > e_strad + 2.0 else ("IV CRUSH 🔴" if c_strad < e_strad - 2.0 else "NORMAL DECAY")
            st.session_state["straddle_history"] = pd.concat([strad_df, pd.DataFrame([{"Date": today_date_str, "Time": now_time_str, "Elapsed_Mins": e_mins, "Actual_Straddle": c_strad, "Expected_Straddle": e_strad, "Regime": regime, "Straddle_VWAP": strad_vwap}])], ignore_index=True)
            save_persisted_df(st.session_state["straddle_history"], "straddle_history")
            
    # Load Memory for UI
    abs_df = st.session_state["absorption_history"]
    oi_snap = st.session_state["oi_snapshots"]
    iv_hist = st.session_state["iv_spread_history"]
    pcr_df = st.session_state["pcr_history"]
    gex_df = st.session_state["gex_history"]
    synth_df = st.session_state["synth_history"]
    doi_df = st.session_state["delta_oi_history"]
    strad_df = st.session_state["straddle_history"]

    # SINGLE PREMIUM HERO BANNER
    st.markdown(f'<div class="metric-card metric-card-amber" style="text-align:center;"><div class="metric-title" style="font-size:0.8rem;">NIFTY SYNTH FUT (ATM)</div><div class="metric-value" style="font-size:2.2rem;">₹{synthetic_future:,.2f}</div><div class="metric-sub sub-amber" style="font-size:0.9rem;">Spot: ₹{spot_price:,.2f} | Gamma Flip: {gamma_flip_strike}</div></div>', unsafe_allow_html=True)

    # --- HORIZONTAL AGGREGATE METRICS WITH DYNAMIC SENTIMENT INTERPRETATIONS ---
    st.markdown('<div class="chart-title" style="margin-top:10px;">Aggregate Options Flow (Total PE vs CE)</div>', unsafe_allow_html=True)
    
    tot_pe_oi, tot_ce_oi = df_filtered["PE_OI"].sum(), df_filtered["CE_OI"].sum()
    oi_interp = "🟢 Uptrend / Strong Support" if tot_pe_oi > tot_ce_oi * 1.15 else ("🔴 Downtrend / Resistance" if tot_ce_oi > tot_pe_oi * 1.15 else "⚪ Balanced Structure")
    oi_col = "#00E676" if "Uptrend" in oi_interp else ("#FF5252" if "Downtrend" in oi_interp else "#8A93A6")

    # True Full Day OI Change using Exchange Values natively from df_filtered
    tot_ce_oichg, tot_pe_oichg = df_filtered["CE_OI_Chg"].sum(), df_filtered["PE_OI_Chg"].sum()

    chg_interp = "🟢 Bullish Momentum" if tot_pe_oichg > tot_ce_oichg * 1.2 else ("🔴 Bearish Pressure" if tot_ce_oichg > tot_pe_oichg * 1.2 else "⚪ Neutral Building")
    chg_col = "#00E676" if "Bullish" in chg_interp else ("#FF5252" if "Bearish" in chg_interp else "#8A93A6")

    tot_pe_vol, tot_ce_vol = df_filtered["PE_Vol"].sum(), df_filtered["CE_Vol"].sum()
    vol_interp = "🟢 Bullish Call Sweeps" if tot_ce_vol > tot_pe_vol * 1.15 else ("🔴 Bearish Put Sweeps" if tot_pe_vol > tot_ce_vol * 1.15 else "⚪ Even Turnover")
    vol_col = "#00E676" if "Bullish" in vol_interp else ("#FF5252" if "Bearish" in vol_interp else "#8A93A6")

    tot_pe_chex, tot_ce_chex = df_filtered["PE_CHEX"].sum(), df_filtered["CE_CHEX"].sum()
    chex_interp = "🟢 Time Decay Bullish" if tot_pe_chex > tot_ce_chex else "🔴 Time Bleed Bearish"
    chex_col = "#00E676" if tot_pe_chex > tot_ce_chex else "#FF5252"

    tot_pe_vex, tot_ce_vex = df_filtered["PE_VEX"].sum(), df_filtered["CE_VEX"].sum()
    vex_interp = "🟢 Vol Squeeze Risk" if tot_pe_vex > tot_ce_vex else "🔴 Vol Crush Expected"
    vex_col = "#00E676" if tot_pe_vex > tot_ce_vex else "#FF5252"

    tot_put_gex, tot_call_gex = abs(df_filtered["Put_GEX"].sum()), df_filtered["Call_GEX"].sum()
    gex_interp = "⚪ Sideways / Pinning" if tot_call_gex > tot_put_gex * 1.3 else ("🔴 Trend Acceleration" if tot_put_gex > tot_call_gex else "🟢 Stable Bounds")
    gex_col = "#FFD700" if "Sideways" in gex_interp else ("#FF5252" if "Acceleration" in gex_interp else "#00E676")

    h1, h2, h3, h4, h5, h6 = st.columns(6)
    h1.plotly_chart(create_h_bar("Total OI", tot_pe_oi, tot_ce_oi, oi_interp, oi_col), use_container_width=True)
    h2.plotly_chart(create_h_bar("OI Change (Full Day)", tot_pe_oichg, tot_ce_oichg, chg_interp, chg_col), use_container_width=True)
    h3.plotly_chart(create_h_bar("Volume", tot_pe_vol, tot_ce_vol, vol_interp, vol_col), use_container_width=True)
    h4.plotly_chart(create_h_bar("Theta Exp (CHEX)", tot_pe_chex, tot_ce_chex, chex_interp, chex_col), use_container_width=True)
    h5.plotly_chart(create_h_bar("Vega Exp (VEX)", tot_pe_vex, tot_ce_vex, vex_interp, vex_col), use_container_width=True)
    h6.plotly_chart(create_h_bar("Gamma Exp (GEX)", tot_put_gex, tot_call_gex, gex_interp, gex_col), use_container_width=True)

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "👑 Prince Analysis",
        "🛡️ Greek Exposure Profiles", 
        "🚀 Intraday & Advanced Analytics", 
        "📈 OpenBull & Fyers Skew", 
        "📊 Options Chain Grid",
        "🎯 Nifty 50 Camarilla Radar"
    ])

    with tab1: # PRINCE ANALYSIS
        v1, v2 = st.columns(2)
        with v1:
            st.markdown('<div class="chart-container"><div class="chart-title">Forward Vol Term Structure (Active + 3 Expiries)</div>', unsafe_allow_html=True)
            exp_list = [selected_expiry] + [x for x in valid_expiries if x != selected_expiry][:3]
            df_vol_struct, df_surface = fetch_multi_expiry_vol_structure(spot_price, exp_list)
            
            if not df_vol_struct.empty and len(df_vol_struct) >= 2:
                is_backwardation = df_vol_struct.iloc[0]["Mean_IV"] > df_vol_struct.iloc[-1]["Mean_IV"]
                term_str = "🔴 <b>Live Structure: Backwardation</b> (Front IV > Far IV) — Near-term panic pricing in." if is_backwardation else "🟢 <b>Live Structure: Contango</b> (Front IV < Far IV) — Normal market decay."
                st.markdown(f'<div class="interp-box">{term_str}</div>', unsafe_allow_html=True)
                fig_fwd = go.Figure()
                fig_fwd.add_trace(go.Scatter(x=df_vol_struct["Expiry"], y=df_vol_struct["Forward_Vol"], mode="lines+markers", name="Forward Vol", line=dict(color="#00E676", width=2.5)))
                fig_fwd.add_trace(go.Scatter(x=df_vol_struct["Expiry"], y=df_vol_struct["Mean_IV"], mode="lines+markers", name="Mean IV", line=dict(color="#AB47BC", width=2.5, dash="dot")))
                st.plotly_chart(apply_dark_layout(fig_fwd), use_container_width=True, config=PLOT_CONFIG)
            else: st.info("Loading Term Structure Data... Bypassing Dhan Rate Limits (Takes ~10 seconds)")
            st.markdown('</div>', unsafe_allow_html=True)
            
        with v2:
            st.markdown('<div class="chart-container"><div class="chart-title">ATM IV vs Nifty Spot Price</div>', unsafe_allow_html=True)
            st.markdown('<div class="interp-box">💡 <b>IV/Spot Divergence:</b> Rising Spot + Falling IV = Bullish Continuation. Falling Spot + Rising IV = Bearish Panic.</div>', unsafe_allow_html=True)
            fig_iv_price = make_subplots(specs=[[{"secondary_y": True}]])
            if not iv_hist.empty:
                atm_hist = iv_hist[iv_hist["Strike"] == atm_strike]
                if not atm_hist.empty:
                    fig_iv_price.add_trace(go.Scatter(x=atm_hist["Time"], y=(atm_hist["CE_IV"]+atm_hist["PE_IV"])/2.0*100, mode="lines", name="ATM IV", line=dict(color="#AB47BC", width=2)), secondary_y=False)
                    fig_iv_price.add_trace(go.Scatter(x=atm_hist["Time"], y=atm_hist["Spot"], mode="lines", name="Price", line=dict(color="#FF5252", width=2)), secondary_y=True)
            fig_iv_price.update_yaxes(title_text="ATM IV (%)", secondary_y=False, gridcolor="#2A2E39")
            fig_iv_price.update_yaxes(title_text="Nifty Price", secondary_y=True, showgrid=False)
            st.plotly_chart(apply_dark_layout(fig_iv_price), use_container_width=True, config=PLOT_CONFIG)
            st.markdown('</div>', unsafe_allow_html=True)

        oi_col1, oi_col2 = st.columns(2)
        with oi_col1:
            st.markdown('<div class="chart-container"><div class="chart-title">OI Tracker (CE/PE Profile)</div>', unsafe_allow_html=True)
            fig_oi_prof = go.Figure()
            fig_oi_prof.add_trace(go.Bar(x=df_filtered["Strike"], y=df_filtered["PE_OI"], name="Put OI (PE)", marker_color="#FF5252"))
            fig_oi_prof.add_trace(go.Bar(x=df_filtered["Strike"], y=df_filtered["CE_OI"], name="Call OI (CE)", marker_color="#00E676"))
            fig_oi_prof.add_vline(x=spot_price, line_dash="solid", line_color="#FFD700")
            fig_oi_prof.update_layout(barmode='group')
            st.plotly_chart(apply_dark_layout(fig_oi_prof, 250, True, df_filtered, atm_strike), use_container_width=True, config=PLOT_CONFIG)
            st.markdown('</div>', unsafe_allow_html=True)
        with oi_col2:
            st.markdown('<div class="chart-container"><div class="chart-title">OI Change Tracker (Full Day)</div>', unsafe_allow_html=True)
            fig_oichg_prof = go.Figure()
            fig_oichg_prof.add_trace(go.Bar(x=df_filtered["Strike"], y=df_filtered["PE_OI_Chg"], name="Put OI Chg", marker_color="#FF5252"))
            fig_oichg_prof.add_trace(go.Bar(x=df_filtered["Strike"], y=df_filtered["CE_OI_Chg"], name="Call OI Chg", marker_color="#00E676"))
            fig_oichg_prof.add_vline(x=spot_price, line_dash="solid", line_color="#FFD700")
            fig_oichg_prof.update_layout(barmode='group')
            st.plotly_chart(apply_dark_layout(fig_oichg_prof, 250, True, df_filtered, atm_strike), use_container_width=True, config=PLOT_CONFIG)
            st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="chart-container" style="padding-bottom:10px;"><div class="chart-title">Intraday Absorption & Exhaustion Engine (Synthetic Future vs Options)</div>', unsafe_allow_html=True)
        abs_data = []
        windows = [5, 10, 15, 30, 60]
        
        if not abs_df.empty:
            current_row = abs_df.iloc[-1]
            now_ts_abs = current_row["Timestamp"]
            
            for w in windows:
                target_ts = now_ts_abs - (w * 60)
                past_df = abs_df[abs_df["Timestamp"] <= target_ts]
                
                if not past_df.empty:
                    past_row = past_df.iloc[-1]
                    actual_min = int((now_ts_abs - past_row["Timestamp"]) / 60)
                    
                    d_fut = current_row["Fut_LTP"] - past_row["Fut_LTP"]
                    d_ce_oi = current_row["CE_OI"] - past_row["CE_OI"]
                    d_pe_oi = current_row["PE_OI"] - past_row["PE_OI"]
                    
                    oi_diff = abs(d_ce_oi - d_pe_oi)
                    signal, color = "⚪ Neutral Flow", "#8A93A6"
                    
                    if d_ce_oi > d_pe_oi and oi_diff > 15000 and d_fut <= 15:
                        signal, color = "🔴 Call Absorption (Sellers Defending Ceiling)", "#FF5252"
                    elif d_pe_oi > d_ce_oi and oi_diff > 15000 and d_fut >= -15:
                        signal, color = "🟢 Put Absorption (Buyers Defending Floor)", "#00E676"
                    elif d_ce_oi < 0 and d_pe_oi < 0 and d_fut > 20:
                        signal, color = "🔴 Exhaustion (Price Up, but OI Unwinding)", "#FFD700"
                    elif d_ce_oi < 0 and d_pe_oi < 0 and d_fut < -20:
                        signal, color = "🟢 Exhaustion (Price Down, but OI Unwinding)", "#FFD700"
                    elif d_ce_oi > d_pe_oi and d_fut > 15:
                        signal, color = "🔴 Call Writing (Trailing Resistance)", "#FF5252"
                    elif d_pe_oi > d_ce_oi and d_fut < -15:
                        signal, color = "🟢 Put Writing (Trailing Support)", "#00E676"

                    abs_data.append({"Timeframe": f"Last {actual_min} Min", "Δ Future": f"{d_fut:+.1f} pts", "Δ Call OI": f"{d_ce_oi:+,.0f}", "Δ Put OI": f"{d_pe_oi:+,.0f}", "Signal": f"<span style='color:{color}; font-weight:700;'>{signal}</span>"})
                else:
                    abs_data.append({"Timeframe": f"Last {w} Min", "Δ Future": "Gathering...", "Δ Call OI": "Gathering...", "Δ Put OI": "Gathering...", "Signal": "<span style='color:#8A93A6;'>Gathering...</span>"})
        
        if abs_data:
            table_html = "<table style='width:100%; text-align:left; color:#D1D4DC; border-collapse:collapse; font-size:0.9rem;'><tr style='border-bottom: 1px solid #2A2E39;'><th style='padding:10px;'>Time Window</th><th style='padding:10px;'>Δ Nifty Future</th><th style='padding:10px; color:#00E676;'>Δ Call OI (CE)</th><th style='padding:10px; color:#FF5252;'>Δ Put OI (PE)</th><th style='padding:10px;'>Flow Analysis</th></tr>"
            for row in abs_data: table_html += f"<tr style='border-bottom: 1px solid #2A2E39;'><td style='padding:10px;'><b>{row['Timeframe']}</b></td><td style='padding:10px;'>{row['Δ Future']}</td><td style='padding:10px;'>{row['Δ Call OI']}</td><td style='padding:10px;'>{row['Δ Put OI']}</td><td style='padding:10px;'>{row['Signal']}</td></tr>"
            table_html += "</table>"
            st.markdown(table_html, unsafe_allow_html=True)
        else: st.info("Gathering historical data for Intraday Engine. Please wait.")
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="chart-container"><div class="chart-title">ATM ±5 Strike Options Buildup Analyzer</div>', unsafe_allow_html=True)
        b_win = st.radio("Select Buildup Timeframe:", ["5m", "10m", "15m", "30m", "1H"], horizontal=True, key="buildup_win")
        mins = int(b_win.replace("m", "").replace("H", "")) * (60 if "H" in b_win else 1)
        target_ts = int(time.time()) - (mins * 60)
        
        past_df = oi_snap[oi_snap["Timestamp"] <= target_ts]
        
        if not past_df.empty:
            closest_ts = past_df["Timestamp"].max()
            actual_mins = int((int(time.time()) - closest_ts) / 60)
            
            if actual_mins != mins:
                st.caption(f"ℹ️ Requested {b_win} timeframe, but displaying maximum available history: **{actual_mins} minutes**.")

            past_oi = past_df[past_df["Timestamp"] == closest_ts]
            b_df = df_oc[(df_oc["Strike"] >= atm_strike - 250) & (df_oc["Strike"] <= atm_strike + 250)].copy()
            b_df = b_df.merge(past_oi, on="Strike", suffixes=("", "_past"))
            b_df["CE_P_Chg"], b_df["CE_O_Chg"] = b_df["CE_LTP"] - b_df["CE_LTP_past"], b_df["CE_OI"] - b_df["CE_OI_past"]
            b_df["PE_P_Chg"], b_df["PE_O_Chg"] = b_df["PE_LTP"] - b_df["PE_LTP_past"], b_df["PE_OI"] - b_df["PE_OI_past"]

            ce_rows, pe_rows, net_score = [], [], 0
            for _, r in b_df.iterrows():
                st_ce, bg_ce, col_ce, scr_ce = get_oi_build_status(r["CE_P_Chg"], r["CE_O_Chg"], True)
                st_pe, bg_pe, col_pe, scr_pe = get_oi_build_status(r["PE_P_Chg"], r["PE_O_Chg"], False)
                net_score += (scr_ce * abs(r["CE_O_Chg"])) + (scr_pe * abs(r["PE_O_Chg"]))
                
                atm_class = " class='row-atm'" if r["Strike"] == atm_strike else ""
                ce_rows.append(f"<tr{atm_class}><td>{r['Strike']:.0f}</td><td style='color:{'#00E676' if r['CE_P_Chg']>0 else '#FF5252'}'>{r['CE_P_Chg']:+.1f}</td><td style='color:{'#00E676' if r['CE_O_Chg']>0 else '#FF5252'}'>{r['CE_O_Chg']:+,.0f}</td><td><span class='tag-badge' style='background-color:{bg_ce}; color:{col_ce}'>{st_ce}</span></td></tr>")
                pe_rows.append(f"<tr{atm_class}><td>{r['Strike']:.0f}</td><td style='color:{'#00E676' if r['PE_P_Chg']>0 else '#FF5252'}'>{r['PE_P_Chg']:+.1f}</td><td style='color:{'#00E676' if r['PE_O_Chg']>0 else '#FF5252'}'>{r['PE_O_Chg']:+,.0f}</td><td><span class='tag-badge' style='background-color:{bg_pe}; color:{col_pe}'>{st_pe}</span></td></tr>")

            sent_text = "🟢 Bullish Options Flow Dominating" if net_score > 0 else ("🔴 Bearish Options Flow Dominating" if net_score < 0 else "⚪ Neutral Options Flow")
            sent_col = "#00E676" if net_score > 0 else ("#FF5252" if net_score < 0 else "#8A93A6")
            st.markdown(f"<div style='text-align:center; padding:10px; border:1px solid {sent_col}; border-radius:5px; margin-bottom:15px; color:{sent_col}; font-weight:bold;'>Net {actual_mins}m Sentiment: {sent_text}</div>", unsafe_allow_html=True)
            
            c1, c2 = st.columns(2)
            c1.markdown(f"<div style='color:#00E676; font-weight:bold; margin-bottom:5px;'>CALL (CE) BUILDUP</div><table class='buildup-table'><tr><th class='center'>Strike</th><th>LTP Chg</th><th>OI Chg</th><th class='center'>Status</th></tr>{''.join(ce_rows)}</table>", unsafe_allow_html=True)
            c2.markdown(f"<div style='color:#FF5252; font-weight:bold; margin-bottom:5px;'>PUT (PE) BUILDUP</div><table class='buildup-table'><tr><th class='center'>Strike</th><th>LTP Chg</th><th>OI Chg</th><th class='center'>Status</th></tr>{''.join(pe_rows)}</table>", unsafe_allow_html=True)
        else: st.info(f"Gathering historical data for {b_win} buildup analysis. Please wait.")
        st.markdown('</div>', unsafe_allow_html=True)

    with tab2: # GREEK EXPOSURES
        call_wall_dex = df_filtered.loc[df_filtered['Net_DEX'].idxmax()]['Strike'] if not df_filtered.empty else atm_strike
        put_wall_dex = df_filtered.loc[df_filtered['Net_DEX'].idxmin()]['Strike'] if not df_filtered.empty else atm_strike
        call_wall_gex = df_filtered.loc[df_filtered['Net_GEX'].idxmax()]['Strike'] if not df_filtered.empty else atm_strike
        put_wall_gex = df_filtered.loc[df_filtered['Net_GEX'].idxmin()]['Strike'] if not df_filtered.empty else atm_strike

        e1, e2 = st.columns(2)
        with e1:
            st.markdown('<div class="chart-container"><div class="chart-title">Net Delta Exposure (DEX) By Strike</div>', unsafe_allow_html=True)
            dex_tot = df_filtered['Net_DEX'].sum() if not df_filtered.empty else 0
            dex_interp_str = f"🟢 <b>Live Delta Bias ({dex_tot:+.1f}L):</b> Market Makers are Long Delta. They will sell underlying to hedge down-moves (Support)." if dex_tot > 0 else f"🔴 <b>Live Delta Bias ({dex_tot:+.1f}L):</b> Market Makers are Short Delta. They will buy underlying to hedge up-moves (Resistance)."
            st.markdown(f'<div class="interp-box">{dex_interp_str}</div>', unsafe_allow_html=True)
            
            fig_dex = go.Figure()
            fig_dex.add_trace(go.Bar(x=df_filtered["Strike"], y=df_filtered["Net_DEX"], marker_color=["#00E676" if val >= 0 else "#FF5252" for val in df_filtered["Net_DEX"]], name="Net DEX", opacity=0.75))
            fig_dex.add_trace(go.Scatter(x=df_filtered["Strike"], y=df_filtered["ABS_DEX"], mode="lines", name="Absolute DEX", line=dict(color="#FFA726", width=2, shape="spline", smoothing=1.3)))
            y_max_dex = max(df_filtered["ABS_DEX"].max() if not df_filtered.empty else 1, df_filtered["Net_DEX"].max() if not df_filtered.empty else 1) * 1.1
            fig_dex.add_vline(x=spot_price, line_dash="solid", line_color="#FFD700"); fig_dex.add_annotation(x=spot_price, y=y_max_dex*0.95, text=f"Spot: {spot_price:.1f}", showarrow=False, font=dict(color="#FFD700", size=9))
            fig_dex.add_vline(x=call_wall_dex, line_dash="dash", line_color="#00E676"); fig_dex.add_annotation(x=call_wall_dex, y=y_max_dex*0.85, text=f"Call Wall: {call_wall_dex}", showarrow=False, font=dict(color="#00E676", size=9))
            fig_dex.add_vline(x=put_wall_dex, line_dash="dash", line_color="#FF5252"); fig_dex.add_annotation(x=put_wall_dex, y=y_max_dex*0.75, text=f"Put Wall: {put_wall_dex}", showarrow=False, font=dict(color="#FF5252", size=9))
            st.plotly_chart(apply_dark_layout(fig_dex, 350, True, df_filtered, atm_strike), use_container_width=True, config=PLOT_CONFIG)
            st.markdown('</div>', unsafe_allow_html=True)
        with e2:
            st.markdown('<div class="chart-container"><div class="chart-title">Net Gamma Exposure (GEX) By Strike</div>', unsafe_allow_html=True)
            gex_tot = df_filtered['Net_GEX'].sum() if not df_filtered.empty else 0
            gex_interp_str = f"🟢 <b>Live Gamma Regime ({gex_tot:+.1f}L):</b> Market Makers are Long Gamma. They buy dips and sell rips (Volatility Dampening)." if gex_tot > 0 else f"🔴 <b>Live Gamma Regime ({gex_tot:+.1f}L):</b> Market Makers are Short Gamma. They sell dips and buy rips (Volatility Accelerating)."
            st.markdown(f'<div class="interp-box">{gex_interp_str}</div>', unsafe_allow_html=True)

            fig_gex = go.Figure()
            fig_gex.add_trace(go.Bar(x=df_filtered["Strike"], y=df_filtered["Net_GEX"], marker_color=["#00E676" if g >= 0 else "#FF5252" for g in df_filtered["Net_GEX"]], name="Net GEX", opacity=0.75))
            fig_gex.add_trace(go.Scatter(x=df_filtered["Strike"], y=df_filtered["ABS_GEX"], mode="lines", name="Absolute GEX", line=dict(color="#29B6F6", width=2, shape="spline", smoothing=1.3)))
            y_max_gex = max(df_filtered["ABS_GEX"].max() if not df_filtered.empty else 1, df_filtered["Net_GEX"].max() if not df_filtered.empty else 1) * 1.1
            fig_gex.add_vline(x=spot_price, line_dash="solid", line_color="#FFD700"); fig_gex.add_annotation(x=spot_price, y=y_max_gex*0.95, text=f"Spot: {spot_price:.1f}", showarrow=False, font=dict(color="#FFD700", size=9))
            fig_gex.add_vline(x=gamma_flip_strike, line_dash="dash", line_color="#29B6F6"); fig_gex.add_annotation(x=gamma_flip_strike, y=y_max_gex*0.85, text=f"Flip: {gamma_flip_strike}", showarrow=False, font=dict(color="#29B6F6", size=9))
            fig_gex.add_vline(x=call_wall_gex, line_dash="dash", line_color="#00E676"); fig_gex.add_annotation(x=call_wall_gex, y=y_max_gex*0.65, text=f"Call Wall: {call_wall_gex}", showarrow=False, font=dict(color="#00E676", size=9))
            fig_gex.add_vline(x=put_wall_gex, line_dash="dash", line_color="#FF5252"); fig_gex.add_annotation(x=put_wall_gex, y=y_max_gex*0.55, text=f"Put Wall: {put_wall_gex}", showarrow=False, font=dict(color="#FF5252", size=9))
            st.plotly_chart(apply_dark_layout(fig_gex, 350, True, df_filtered, atm_strike), use_container_width=True, config=PLOT_CONFIG)
            st.markdown('</div>', unsafe_allow_html=True)

        e3, e4 = st.columns(2)
        with e3:
            st.markdown('<div class="chart-container"><div class="chart-title">Tradytics Vanna Exposure (VEX)</div>', unsafe_allow_html=True)
            net_vex_tot = df_filtered["Net_VEX"].sum()
            vex_interp_str = f"🟢 <b>Live Vanna Signal (+{net_vex_tot:.2f}L):</b> Positive Net Vanna means IV expansion forces dealers to buy futures, dampening downside sell-offs." if net_vex_tot > 0 else f"🔴 <b>Live Vanna Signal ({net_vex_tot:.2f}L):</b> Negative Net Vanna means IV expansion forces dealers to sell futures, accelerating market downturns."
            st.markdown(f'<div class="interp-box">{vex_interp_str}</div>', unsafe_allow_html=True)
            fig_vex = go.Figure()
            fig_vex.add_trace(go.Bar(x=df_filtered["Strike"], y=df_filtered["PE_VEX"], name="Put VEX (PE)", marker_color="#FF5252"))
            fig_vex.add_trace(go.Bar(x=df_filtered["Strike"], y=df_filtered["CE_VEX"], name="Call VEX (CE)", marker_color="#00E676"))
            fig_vex.update_layout(barmode='group')
            st.plotly_chart(apply_dark_layout(fig_vex, 250, True, df_filtered, atm_strike), use_container_width=True, config=PLOT_CONFIG)
            st.markdown('</div>', unsafe_allow_html=True)
        with e4:
            st.markdown('<div class="chart-container"><div class="chart-title">Tradytics Charm Exposure (CHEX)</div>', unsafe_allow_html=True)
            net_chex_tot = df_filtered["Net_CHEX"].sum()
            chex_interp_str = f"🟢 <b>Live Charm Signal (+{net_chex_tot:.2f}L):</b> Positive Net Charm indicates time decay forces dealers to steadily buy futures (Bullish drift)." if net_chex_tot > 0 else f"🔴 <b>Live Charm Signal ({net_chex_tot:.2f}L):</b> Negative Net Charm indicates time decay forces dealers to sell futures (Bearish drift)."
            st.markdown(f'<div class="interp-box">{chex_interp_str}</div>', unsafe_allow_html=True)
            fig_chex = go.Figure()
            fig_chex.add_trace(go.Bar(x=df_filtered["Strike"], y=df_filtered["PE_CHEX"], name="Put CHEX (PE)", marker_color="#FF5252"))
            fig_chex.add_trace(go.Bar(x=df_filtered["Strike"], y=df_filtered["CE_CHEX"], name="Call CHEX (CE)", marker_color="#00E676"))
            fig_chex.update_layout(barmode='group')
            st.plotly_chart(apply_dark_layout(fig_chex, 250, True, df_filtered, atm_strike), use_container_width=True, config=PLOT_CONFIG)
            st.markdown('</div>', unsafe_allow_html=True)

    with tab3: # INTRADAY & ADVANCED ANALYTICS (MERGED)
        r1c1, r1c2 = st.columns(2)
        with r1c1:
            st.markdown(f'<div class="chart-container"><div class="chart-title">Intraday IV Spread Movement ({selected_target_strike})</div>', unsafe_allow_html=True)
            fig_ts = go.Figure()
            if not iv_hist.empty: 
                strike_history = iv_hist[iv_hist["Strike"] == selected_target_strike]
                if not strike_history.empty: fig_ts.add_trace(go.Scatter(x=strike_history["Time"], y=strike_history["IV_Spread"], mode="lines+markers", line=dict(color="#29B6F6", width=2), marker=dict(size=3)))
            fig_ts.add_hline(y=0, line_dash="dash", line_color="white", opacity=0.3)
            st.plotly_chart(apply_dark_layout(fig_ts), use_container_width=True, config=PLOT_CONFIG)
            st.markdown('</div>', unsafe_allow_html=True)
        with r1c2:
            st.markdown('<div class="chart-container"><div class="chart-title">15-Min PCR Velocity (ΔPCR)</div>', unsafe_allow_html=True)
            fig_pcr = go.Figure()
            if not pcr_df.empty: fig_pcr.add_trace(go.Bar(x=pcr_df["Time"], y=pcr_df["Delta_PCR_15m"], marker_color=["#00E676" if v >= 0.15 else ("#FF5252" if v <= -0.15 else "#8A93A6") for v in pcr_df["Delta_PCR_15m"]]))
            fig_pcr.add_hline(y=0.15, line_dash="dash", line_color="#00E676"); fig_pcr.add_hline(y=-0.15, line_dash="dash", line_color="#FF5252")
            st.plotly_chart(apply_dark_layout(fig_pcr), use_container_width=True, config=PLOT_CONFIG)
            st.markdown('</div>', unsafe_allow_html=True)

        r2c1, r2c2 = st.columns(2)
        with r2c1:
            st.markdown('<div class="chart-container"><div class="chart-title">Cumulative Open Interest Trend (Cr)</div>', unsafe_allow_html=True)
            fig_oi_trend = go.Figure()
            if not pcr_df.empty:
                fig_oi_trend.add_trace(go.Scatter(x=pcr_df["Time"], y=pcr_df["Total_PE_OI"]/1e7, mode="lines", name="Put OI (PE)", line=dict(color="#FF5252", width=2)))
                fig_oi_trend.add_trace(go.Scatter(x=pcr_df["Time"], y=pcr_df["Total_CE_OI"]/1e7, mode="lines", name="Call OI (CE)", line=dict(color="#00E676", width=2)))
                fig_oi_trend.add_trace(go.Scatter(x=pcr_df["Time"], y=(pcr_df["Total_PE_OI"]-pcr_df["Total_CE_OI"])/1e7, mode="lines", name="PE-CE Diff", line=dict(color="#AB47BC", width=2)))
            st.plotly_chart(apply_dark_layout(fig_oi_trend), use_container_width=True, config=PLOT_CONFIG)
            st.markdown('</div>', unsafe_allow_html=True)
        with r2c2:
            st.markdown('<div class="chart-container"><div class="chart-title">Intraday PCR & Vol PCR Trend</div>', unsafe_allow_html=True)
            fig_pcr_t = go.Figure()
            if not pcr_df.empty:
                fig_pcr_t.add_trace(go.Scatter(x=pcr_df["Time"], y=pcr_df["PCR"], mode="lines", name="OI PCR", line=dict(color="#29B6F6", width=2)))
                if "Vol_PCR" in pcr_df.columns: fig_pcr_t.add_trace(go.Scatter(x=pcr_df["Time"], y=pcr_df["Vol_PCR"], mode="lines", name="Vol PCR", line=dict(color="#FFA726", width=2)))
            st.plotly_chart(apply_dark_layout(fig_pcr_t), use_container_width=True, config=PLOT_CONFIG)
            st.markdown('</div>', unsafe_allow_html=True)

        r3c1, r3c2 = st.columns(2)
        with r3c1:
            st.markdown('<div class="chart-container"><div class="chart-title">Real-Time Delta-Weighted Net OI</div>', unsafe_allow_html=True)
            st.markdown('<div class="interp-box">💡 <b>Delta-Weighted OI:</b> <span style="color:#00E676;">Positive = Market Makers are Long Delta (Bullish).</span> <span style="color:#FF5252;">Negative = Market Makers are Short Delta (Bearish).</span></div>', unsafe_allow_html=True)
            fig_doi = go.Figure()
            if not doi_df.empty: fig_doi.add_trace(go.Scatter(x=doi_df["Time"], y=doi_df["Total_Net_Delta_OI"], mode="lines", fill='tozeroy', line=dict(color="#00E676", width=2)))
            fig_doi.add_hline(y=0, line_dash="dash", line_color="white", opacity=0.3)
            st.plotly_chart(apply_dark_layout(fig_doi), use_container_width=True, config=PLOT_CONFIG)
            st.markdown('</div>', unsafe_allow_html=True)
        with r3c2:
            st.markdown('<div class="chart-container"><div class="chart-title">Dealer Delta Velocity (DEX 5m ROC)</div>', unsafe_allow_html=True)
            st.markdown('<div class="interp-box">💡 Tracks the 5-minute rate of change of Dealer Delta Exposure to detect rapid hedging moves.</div>', unsafe_allow_html=True)
            fig_dvel = go.Figure()
            if not doi_df.empty: fig_dvel.add_trace(go.Bar(x=doi_df["Time"], y=doi_df["DEX_Vel_5m"], marker_color=["#00E676" if v >= 0 else "#FF5252" for v in doi_df["DEX_Vel_5m"]]))
            fig_dvel.add_hline(y=0, line_dash="dash", line_color="white", opacity=0.3)
            st.plotly_chart(apply_dark_layout(fig_dvel), use_container_width=True, config=PLOT_CONFIG)
            st.markdown('</div>', unsafe_allow_html=True)

        a1, a2 = st.columns(2)
        with a1:
            st.markdown('<div class="chart-container"><div class="chart-title">Fyers ATM Straddle LTP vs Price vs Straddle VWAP</div>', unsafe_allow_html=True)
            fig_fyers_strad = make_subplots(specs=[[{"secondary_y": True}]])
            if not strad_df.empty:
                fig_fyers_strad.add_trace(go.Scatter(x=strad_df["Time"], y=strad_df["Actual_Straddle"], mode="lines", name="ATM Straddle LTP", line=dict(color="#FF5252", width=2)), secondary_y=False)
                if "Straddle_VWAP" in strad_df.columns:
                    fig_fyers_strad.add_trace(go.Scatter(x=strad_df["Time"], y=strad_df["Straddle_VWAP"], mode="lines", name="Straddle VWAP", line=dict(color="#00E676", width=1.5, dash="dot")), secondary_y=False)
                if not synth_df.empty:
                    fig_fyers_strad.add_trace(go.Scatter(x=synth_df["Time"], y=synth_df["Spot"], mode="lines", name="Nifty Price", line=dict(color="#29B6F6", width=1.5, dash="dash")), secondary_y=True)
            fig_fyers_strad.update_yaxes(title_text="Straddle Premium (₹)", secondary_y=False, gridcolor="#2A2E39")
            fig_fyers_strad.update_yaxes(title_text="Nifty Price", secondary_y=True, showgrid=False)
            st.plotly_chart(apply_dark_layout(fig_fyers_strad), use_container_width=True, config=PLOT_CONFIG)
            st.markdown('</div>', unsafe_allow_html=True)
        with a2:
            st.markdown('<div class="chart-container"><div class="chart-title">Gamma Flip Migration (ΔFlip)</div>', unsafe_allow_html=True)
            fig_flip = go.Figure()
            if not gex_df.empty:
                fig_flip.add_trace(go.Scatter(x=gex_df["Time"], y=gex_df["Spot"], mode="lines", name="Spot", line=dict(color="#FFD700", width=2)))
                fig_flip.add_trace(go.Scatter(x=gex_df["Time"], y=gex_df["Flip_Strike"], mode="lines", name="Flip Level", line=dict(color="#29B6F6", width=2, dash="dash")))
            st.plotly_chart(apply_dark_layout(fig_flip), use_container_width=True, config=PLOT_CONFIG)
            st.markdown('</div>', unsafe_allow_html=True)

        a3, a4 = st.columns(2)
        with a3:
            st.markdown('<div class="chart-container"><div class="chart-title">Put-Call Parity Discrepancy Index (PCP_Dev)</div>', unsafe_allow_html=True)
            fig_pcp = go.Figure()
            if not synth_df.empty:
                fig_pcp.add_trace(go.Bar(x=synth_df["Time"], y=synth_df["PCP_Dev_Mean"], marker_color=["#00E676" if v > 0 else "#FF5252" for v in synth_df["PCP_Dev_Mean"]]))
            fig_pcp.add_hline(y=3.0, line_dash="dash", line_color="#00E676", annotation_text="+3.0 Call Squeeze")
            fig_pcp.add_hline(y=-3.0, line_dash="dash", line_color="#FF5252", annotation_text="-3.0 Put Squeeze")
            st.plotly_chart(apply_dark_layout(fig_pcp), use_container_width=True, config=PLOT_CONFIG)
            st.markdown('</div>', unsafe_allow_html=True)
        with a4:
            st.markdown('<div class="chart-container"><div class="chart-title">Multi-Strike Synthetic Parity Engine</div>', unsafe_allow_html=True)
            fig_synth = go.Figure()
            if not synth_df.empty:
                fig_synth.add_trace(go.Scatter(x=synth_df["Time"], y=synth_df["Spot"], mode="lines", name="Spot", line=dict(color="#FFD700", width=2)))
                fig_synth.add_trace(go.Scatter(x=synth_df["Time"], y=synth_df["Synth_M50"], mode="lines", name="ITM Synth", line=dict(color="#00E676", width=1.5, dash="dot")))
                fig_synth.add_trace(go.Scatter(x=synth_df["Time"], y=synth_df["Synth_ATM"], mode="lines", name="ATM Synth", line=dict(color="#29B6F6", width=1.5, dash="dot")))
                fig_synth.add_trace(go.Scatter(x=synth_df["Time"], y=synth_df["Synth_P50"], mode="lines", name="OTM Synth", line=dict(color="#FF5252", width=1.5, dash="dot")))
            st.plotly_chart(apply_dark_layout(fig_synth), use_container_width=True, config=PLOT_CONFIG)
            st.markdown('</div>', unsafe_allow_html=True)

    with tab4: # OPENBULL & FYERS SKEW
        f1, f2 = st.columns(2)
        with f1:
            st.markdown('<div class="chart-container"><div class="chart-title">Fyers Multi-Day Macro Overlay (PCR vs Price)</div>', unsafe_allow_html=True)
            fig_macro = make_subplots(specs=[[{"secondary_y": True}]])
            if not pcr_df.empty:
                fig_macro.add_trace(go.Scatter(x=pcr_df["Time"], y=pcr_df["PCR"], mode="lines", name="PCR", line=dict(color="#AB47BC", width=2)), secondary_y=False)
                if not gex_df.empty:
                    fig_macro.add_trace(go.Scatter(x=gex_df["Time"], y=gex_df["Spot"], mode="lines", name="Nifty Price", line=dict(color="#FF5252", width=2)), secondary_y=True)
            fig_macro.update_yaxes(title_text="PCR", secondary_y=False, gridcolor="#2A2E39")
            fig_macro.update_yaxes(title_text="Nifty Price", secondary_y=True, showgrid=False)
            st.plotly_chart(apply_dark_layout(fig_macro), use_container_width=True, config=PLOT_CONFIG)
            st.markdown('</div>', unsafe_allow_html=True)

        with f2:
            st.markdown('<div class="chart-container"><div class="chart-title">Fyers Selected Strikes IV Overlay vs Price</div>', unsafe_allow_html=True)
            selected_iv_strikes = st.multiselect("Select Strikes to Track IV:", options=df_filtered["Strike"].tolist(), default=[atm_strike-50, atm_strike, atm_strike+50], key="fyers_ms_iv")
            fig_ms_iv = make_subplots(specs=[[{"secondary_y": True}]])
            if not iv_hist.empty and selected_iv_strikes:
                colors_list = ["#AB47BC", "#00E676", "#29B6F6", "#FFA726", "#FF5252"]
                for idx_s, st_val in enumerate(selected_iv_strikes):
                    st_h = iv_hist[iv_hist["Strike"] == st_val]
                    if not st_h.empty:
                        c_col = colors_list[idx_s % len(colors_list)]
                        fig_ms_iv.add_trace(go.Scatter(x=st_h["Time"], y=(st_h["CE_IV"]+st_h["PE_IV"])/2.0*100, mode="lines", name=f"IV ({st_val})", line=dict(color=c_col, width=1.5)), secondary_y=False)
                if not synth_df.empty:
                    fig_ms_iv.add_trace(go.Scatter(x=synth_df["Time"], y=synth_df["Spot"], mode="lines", name="Nifty Price", line=dict(color="#29B6F6", width=2)), secondary_y=True)
            fig_ms_iv.update_yaxes(title_text="Implied Volatility (%)", secondary_y=False, gridcolor="#2A2E39")
            fig_ms_iv.update_yaxes(title_text="Nifty Price", secondary_y=True, showgrid=False)
            st.plotly_chart(apply_dark_layout(fig_ms_iv, 300), use_container_width=True, config=PLOT_CONFIG)
            st.markdown('</div>', unsafe_allow_html=True)

        v1, v2 = st.columns(2)
        with v1:
            st.markdown('<div class="chart-container"><div class="chart-title">OpenBull IV Smile (Volatility Skew Profile)</div>', unsafe_allow_html=True)
            fig_smile = go.Figure()
            fig_smile.add_trace(go.Scatter(x=df_filtered["Strike"], y=df_filtered["PE_IV"], mode="lines+markers", name="Put IV (PE)", line=dict(color="#FF5252", width=2)))
            fig_smile.add_trace(go.Scatter(x=df_filtered["Strike"], y=df_filtered["CE_IV"], mode="lines+markers", name="Call IV (CE)", line=dict(color="#00E676", width=2)))
            fig_smile.add_vline(x=spot_price, line_dash="solid", line_color="#FFD700")
            st.plotly_chart(apply_dark_layout(fig_smile, 250, True, df_filtered, atm_strike), use_container_width=True, config=PLOT_CONFIG)
            st.markdown('</div>', unsafe_allow_html=True)
            
        with v2:
            st.markdown('<div class="chart-container"><div class="chart-title">OpenBull 3D Volatility Surface</div>', unsafe_allow_html=True)
            st.markdown('<div class="interp-box">💡 <b>3D Vol Skew Surface:</b> Visualizes IV across Strike (X) and Days (Y). Peaks indicate localized options demand.</div>', unsafe_allow_html=True)
            exp_list_surf = [selected_expiry] + [x for x in valid_expiries if x != selected_expiry][:3]
            _, df_surface = fetch_multi_expiry_vol_structure(spot_price, exp_list_surf)
            if not df_surface.empty:
                pivot_surface = df_surface.pivot_table(index='Days', columns='Strike', values='IV', aggfunc='mean').ffill(axis=1).bfill(axis=1).fillna(0)
                fig_surf = go.Figure(data=[go.Surface(z=pivot_surface.values, x=pivot_surface.columns.tolist(), y=pivot_surface.index.tolist(), colorscale='Viridis', showscale=False)])
                fig_surf.update_layout(scene=dict(xaxis_title='Strike', yaxis_title='Days to Expiry', zaxis_title='Implied Vol'), template="plotly_dark", margin=dict(l=0,r=0,t=0,b=0), height=250)
                st.plotly_chart(fig_surf, use_container_width=True, config=PLOT_CONFIG)
            else: st.info("Loading Expiries for 3D Surface... (Requires 4 active chains)")
            st.markdown('</div>', unsafe_allow_html=True)

    with tab5: # DATA GRID
        st.markdown('<div class="chart-container"><div class="chart-title">Institutional Options Chain Grid</div>', unsafe_allow_html=True)
        grid_df = df_filtered[["Strike", "CE_LTP", "PE_LTP", "CE_OI", "PE_OI", "CE_OI_Chg", "PE_OI_Chg", "CE_Delta", "PE_Delta", "Net_Delta_OI", "Net_DEX", "Net_GEX", "CE_VEX", "PE_VEX", "CE_CHEX", "PE_CHEX", "CE_SPEX", "PE_SPEX", "CE_IV", "PE_IV"]].copy()
        st.dataframe(grid_df.style.format({"Strike": "{:.0f}", "CE_LTP": "₹{:.2f}", "PE_LTP": "₹{:.2f}", "CE_OI": "{:,.0f}", "PE_OI": "{:,.0f}", "CE_OI_Chg": "{:,.0f}", "PE_OI_Chg": "{:,.0f}", "CE_Delta": "{:.2f}", "PE_Delta": "{:.2f}", "Net_Delta_OI": "{:+,.0f}", "Net_DEX": "{:+,.1f}L", "Net_GEX": "{:+,.1f}L", "CE_VEX": "{:.2f}", "PE_VEX": "{:.2f}", "CE_CHEX": "{:.2f}", "PE_CHEX": "{:.2f}", "CE_SPEX": "{:.2f}", "PE_SPEX": "{:.2f}", "CE_IV": "{:.1f}%", "PE_IV": "{:.1f}%"}), use_container_width=True, height=500)
        st.markdown('</div>', unsafe_allow_html=True)

    with tab6: # NIFTY 50 CAMARILLA RADAR
        st.markdown('<div class="chart-container"><div class="chart-title">Nifty 50 Weighted Camarilla Matrix (S3/R3 Reversal Zones)</div>', unsafe_allow_html=True)
        st.markdown('<div class="interp-box">💡 <b>Camarilla Radar:</b> Tracks all Nifty 50 stocks for touches of Camarilla S3 (Buy Zone) and R3 (Sell Zone). Sends instant Telegram alerts when tested.</div>', unsafe_allow_html=True)
        
        df_cam = get_nifty50_camarilla()
        if not df_cam.empty:
            process_camarilla_alerts(df_cam, is_market_live, today_date_str)
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("<h4 style='color:#00E676; font-size:1rem; margin-bottom:10px;'>🟢 Approaching S3 Support (Mean Reversion Buy)</h4>", unsafe_allow_html=True)
                s3_df = df_cam[df_cam["Dist_S3_%"] < 1.0].sort_values(["Dist_S3_%", "Weight"], ascending=[True, False]).head(10)
                if not s3_df.empty: st.dataframe(s3_df[["Symbol", "Weight", "LTP", "S3", "Dist_S3_%"]].style.format({"Weight": "{:.2f}%", "LTP": "₹{:.2f}", "S3": "₹{:.2f}", "Dist_S3_%": "{:.2f}%"}), use_container_width=True)
                else: st.info("No Nifty 50 constituents currently testing S3 Support.")
            with c2:
                st.markdown("<h4 style='color:#FF5252; font-size:1rem; margin-bottom:10px;'>🔴 Approaching R3 Resistance (Mean Reversion Sell)</h4>", unsafe_allow_html=True)
                r3_df = df_cam[df_cam["Dist_R3_%"] < 1.0].sort_values(["Dist_R3_%", "Weight"], ascending=[True, False]).head(10)
                if not r3_df.empty: st.dataframe(r3_df[["Symbol", "Weight", "LTP", "R3", "Dist_R3_%"]].style.format({"Weight": "{:.2f}%", "LTP": "₹{:.2f}", "R3": "₹{:.2f}", "Dist_R3_%": "{:.2f}%"}), use_container_width=True)
                else: st.info("No Nifty 50 constituents currently testing R3 Resistance.")
        else:
            st.warning("Fetching Nifty 50 OHLC data. Please wait...")
        st.markdown('</div>', unsafe_allow_html=True)
