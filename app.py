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

# Plotly config optimized for Mobile Scrolling (Touch Drag = Scroll Page, Box Select = Zoom)
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
# 4. YFINANCE & MEMORY ENGINES (CVD Filter Deleted)
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

            T_years = max((datetime.datetime.strptime(expiry_date, "%Y-%m-%d").date() - datetime.date.today()).days, 1) / 365.0
            records = []
            for strike_str, details in oc_raw.items():
                strike = int(float(strike_str))
                ce, pe = details.get("ce", {}), details.get("pe", {})
                ce_oi, pe_oi = float(ce.get("oi", 0)), float(pe.get("oi", 0))
                ce_oichg, pe_oichg = float(ce.get("oi_change", ce.get("change_in_oi", 0))), float(pe.get("oi_change", pe.get("change_in_oi", 0)))
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
            
            try: 
                # Upgraded Date Engine: Handles DD.MM.YYYY and YYYY-MM-DD flawlessly
                exp_date_obj = pd.to_datetime(exp[:10], dayfirst=True).date()
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
# 8. QUARANTINED UI RENDERING BLOCK (Prevents Live Crashes)
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

    # Calculate max_pain_strike
    max_pain_strike = atm_strike
    pain_records = [{"Strike": k, "Writer_Loss": (df_oc["CE_OI"] * (k - df_oc["Strike"]).clip(lower=0)).sum() + (df_oc["PE_OI"] * (df_oc["Strike"] - k).clip(lower=0)).sum()} for k in df_oc["Strike"] if atm_strike - 1500 <= k <= atm_strike + 1500]
    if pain_records:
        df_pain_temp = pd.DataFrame(pain_records)
        max_pain_strike = df_pain_temp.loc[df_pain_temp["Writer_Loss"].idxmin()]["Strike"]

    target_row = df_oc[df_oc["Strike"] == selected_target_strike]
    target_iv_spread = (target_row["CE_IV"].values[0] if not target_row.empty else 0.0) - (target_row["PE_IV"].values[0] if not target_row.empty else 0.0)

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
Here is the updated layout incorporating all 4 modifications:

---

# NIFTY OPTIONS ANALYTICS DASHBOARD

## 📍 HEADER
* **Nifty Synthetic Level:** [ Insert Value / Plot ]

---

## 1. EXPOSURE SECTION
* **Gamma Exposure (GEX):** [ Positive / Negative / Flip Strike ]
* **Delta Exposure (DEX):** [ Net Directional Bias ]
* **Vanna & Charm Exposure:** [ Dealer Delta Drift Impact ]
* **Key Pin Risk & Wall Strikes:**
  * **Call Wall (Resistance):** [ Strike ]
  * **Put Wall (Support):** [ Strike ]

---

## 2. INTRADAY FLOW & ADVANCED TOOLS
*(Combined Intraday Flow & Quantitative Analytics)*

* **Cumulative Delta & Order Flow:** [ Intraday Net Buying/Selling Pressure ]
* **Premium Breakdown (Intrinsic Value Curve):** Tracking $CE - PE$ ($IV$) vs Time Value ($TV$)
* **Curve Sloping Entry Signals:** Reversal triggers based on strike premium slope dynamics
* **GEX Score:** [ Consolidated Gamma Position Metric ]
* **Delta Score:** [ Consolidated Directional Flow Strength ]
* **Volatility Risk Premium (VRP):** [ Implied Volatility vs Realized Volatility Spread ]

---

## 3. ATM IV VS NIFTY SPOT PRICE

| Nifty Spot Level | ATM Strike | Call Premium | Put Premium | ATM IV |
| :--- | :--- | :--- | :--- | :--- |
| **[ Live Spot ]** | **[ ATM Strike ]** | **[ CE ]** | **[ PE ]** | **[ IV % ]** |

> **Interpretation Summary:** *Rising Nifty Spot accompanied by dropping ATM IV indicates strong bullish momentum supported by volatility crush (favorable for short option/spread structures).*

---

## 4. IV TERM STRUCTURE

| Expiry Cycle | Expiry Date | ATM IV | IV Rank / Skew | Term Structure State |
| :--- | :--- | :--- | :--- | :--- |
| **Current Expiry (Weekly)** | [ DD-MMM-YYYY ] | [ IV % ] | [ IVR ] | **[ Anchor ]** |
| **Next Expiry (Next Week)** | [ DD-MMM-YYYY ] | [ IV % ] | [ IVR ] | [ Contango / Backwardation ] |
| **Far Expiry (Monthly)** | [ DD-MMM-YYYY ] | [ IV % ] | [ IVR ] | [ Contango / Backwardation ] |
