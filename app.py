import datetime
import math
import time
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st
from streamlit_autorefresh import st_autorefresh

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

    .info-tooltip {
        position: relative;
        display: inline-block;
        cursor: help;
        color: #8A93A6;
        float: right;
        margin-left: 5px;
        font-size: 0.9rem;
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
        z-index: 99999;
        bottom: 130%; 
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
        top: 100%;
        right: 15px;
        border-width: 6px;
        border-style: solid;
        border-color: #3B4252 transparent transparent transparent;
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

# API Credentials
CLIENT_ID = str(st.secrets.get("DHAN_CLIENT_ID", "")).strip().replace('"', "").replace("'", "")
ACCESS_TOKEN = str(st.secrets.get("DHAN_ACCESS_TOKEN", "")).strip().replace('"', "").replace("'", "")

if not CLIENT_ID or not ACCESS_TOKEN:
    st.error("⚠️ API credentials missing. Please update your Streamlit Secrets.")
    st.stop()

NIFTY_LOT_SIZE = 25


# ---------------------------------------------------------
# 2. BLACK-SCHOLES GREEK ENGINE
# ---------------------------------------------------------
def calculate_bs_greeks(S, K, T, sigma, r=0.07):
    if T <= 1e-5 or sigma <= 1e-4 or S <= 0 or K <= 0: return 0.0, 0.0, 0.0
    try:
        d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        pdf_d1 = (1.0 / math.sqrt(2 * math.pi)) * math.exp(-0.5 * d1 * d1)
        gamma = pdf_d1 / (S * sigma * math.sqrt(T))
        vanna = -pdf_d1 * d2 / sigma
        charm = -pdf_d1 * (2 * r * math.sqrt(T) - d2 * sigma) / (2 * T * sigma)
        return gamma, vanna, charm
    except:
        return 0.0, 0.0, 0.0


# ---------------------------------------------------------
# 3. DIRECT REST API DATA ENGINE
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

            exp_date_obj = datetime.datetime.strptime(expiry_date, "%Y-%m-%d").date()
            days_to_exp = max((exp_date_obj - datetime.date.today()).days, 1)
            T_years = days_to_exp / 365.0

            records = []
            for strike_str, details in oc_raw.items():
                strike = int(float(strike_str))
                ce, pe = details.get("ce", {}), details.get("pe", {})

                ce_oi, pe_oi = float(ce.get("oi", 0)), float(pe.get("oi", 0))
                ce_ltp, pe_ltp = float(ce.get("last_price", 0)), float(pe.get("last_price", 0))
                ce_iv, pe_iv = float(ce.get("implied_volatility", 0))/100.0, float(pe.get("implied_volatility", 0))/100.0
                ce_delta, pe_delta = float(ce.get("greeks", {}).get("delta", 0)), float(pe.get("greeks", {}).get("delta", 0))
                ce_gamma, pe_gamma = float(ce.get("greeks", {}).get("gamma", 0)), float(pe.get("greeks", {}).get("gamma", 0))

                ce_gamma, ce_vanna, ce_charm = calculate_bs_greeks(spot_price, strike, T_years, ce_iv if ce_gamma <= 0 else max(ce_iv, 0.15))
                pe_gamma, pe_vanna, pe_charm = calculate_bs_greeks(spot_price, strike, T_years, pe_iv if pe_gamma <= 0 else max(pe_iv, 0.15))

                call_gex = (ce_oi * ce_gamma * (spot_price**2) * 0.01 * NIFTY_LOT_SIZE / 1e5)
                put_gex = (-pe_oi * pe_gamma * (spot_price**2) * 0.01 * NIFTY_LOT_SIZE / 1e5)
                net_gex = call_gex + put_gex

                net_delta_oi = (ce_oi * ce_delta) + (pe_oi * pe_delta)
                net_dex = net_delta_oi * spot_price * NIFTY_LOT_SIZE / 1e5

                records.append({
                    "Strike": strike, "CE_LTP": ce_ltp, "PE_LTP": pe_ltp, "CE_OI": ce_oi, "PE_OI": pe_oi,
                    "CE_Delta": ce_delta, "PE_Delta": pe_delta, "Net_Delta_OI": net_delta_oi, "Net_DEX": net_dex,
                    "Call_GEX": call_gex, "Put_GEX": put_gex, "Net_GEX": net_gex, 
                    "Net_VEX": ((ce_oi * ce_vanna) - (pe_oi * pe_vanna)) * NIFTY_LOT_SIZE / 1e3, 
                    "Net_CHEX": ((ce_oi * ce_charm) - (pe_oi * pe_charm)) * NIFTY_LOT_SIZE / 1e3,
                    "CE_IV": ce_iv * 100.0, "PE_IV": pe_iv * 100.0, "IV_Spread": (ce_iv * 100.0) - (pe_iv * 100.0),
                })
            return pd.DataFrame(records).sort_values("Strike").reset_index(drop=True), spot_price, None
        else:
            return None, 0.0, str(data.get("remarks") or data.get("message") or f"HTTP {res.status_code}")
    except Exception as e:
        return None, 0.0, f"Connection Error: {str(e)}"

# ---------------------------------------------------------
# 4. EXPIRY LIST ENGINE
# ---------------------------------------------------------
@st.cache_data(ttl=300)
def fetch_expiry_list_direct():
    url, headers, payload = "https://api.dhan.co/v2/optionchain/expirylist", {"client-id": CLIENT_ID, "access-token": ACCESS_TOKEN, "Content-Type": "application/json"}, {"UnderlyingScrip": 13, "UnderlyingSeg": "IDX_I"}
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=5)
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

    atm_strike, vol_data = int(round(spot_price / 50) * 50), []
    for idx, exp in enumerate(expiries):
        if idx > 0: time.sleep(1.2)
        df_exp, _, _ = fetch_gex_option_chain(exp)
        if df_exp is not None and not df_exp.empty:
            atm_row = df_exp[df_exp["Strike"] == atm_strike]
            ce_iv = atm_row["CE_IV"].values[0] if not atm_row.empty else df_exp["CE_IV"].mean()
            pe_iv = atm_row["PE_IV"].values[0] if not atm_row.empty else df_exp["PE_IV"].mean()
            days_to_exp = max((datetime.datetime.strptime(exp, "%Y-%m-%d").date() - datetime.date.today()).days, 1)
            vol_data.append({"Expiry": datetime.datetime.strptime(exp, "%Y-%m-%d").strftime("%d %b"), "Tenor_Years": days_to_exp / 365.0, "Mean_IV": (ce_iv + pe_iv) / 2.0})

    df_vol = pd.DataFrame(vol_data)
    if df_vol.empty or len(df_vol) < 2: return pd.DataFrame()

    fwd_vols = []
    for i in range(len(df_vol)):
        if i == 0: fwd_vols.append(df_vol.loc[i, "Mean_IV"])
        else:
            t1, t2 = df_vol.loc[i - 1, "Tenor_Years"], df_vol.loc[i, "Tenor_Years"]
            v1, v2 = df_vol.loc[i - 1, "Mean_IV"] / 100.0, df_vol.loc[i, "Mean_IV"] / 100.0
            var_diff, dt = (v2**2 * t2) - (v1**2 * t1), t2 - t1
            fwd_vols.append(math.sqrt(var_diff / dt) * 100.0 if var_diff > 0 and dt > 0 else v2 * 100.0)
    df_vol["Forward_Vol"] = fwd_vols
    return df_vol

# ---------------------------------------------------------
# 5. CONTROLS, MEMORY INIT & LIVE SESSION LOGIC
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
selected_expiry = st.sidebar.selectbox("Primary Expiry", valid_expiries) if valid_expiries else st.sidebar.date_input("Primary Expiry", now_ist).strftime("%Y-%m-%d")

df_oc, spot_price, error_remark = fetch_gex_option_chain(selected_expiry)

selected_target_strike = None
if df_oc is not None and not df_oc.empty:
    atm_strike_val = int(round(spot_price / 50) * 50)
    selected_target_strike = st.sidebar.selectbox("🎯 Target Strike", df_oc["Strike"].tolist(), index=df_oc["Strike"].tolist().index(atm_strike_val) if atm_strike_val in df_oc["Strike"].tolist() else 0)

# Memory Config
REQUIRED_HIST_COLS = ["Date", "Time", "Strike", "CE_IV", "PE_IV", "IV_Spread", "Spot"]
REQUIRED_PCR_COLS = ["Date", "Timestamp_dt", "Time", "PCR", "Delta_PCR_5m", "Delta_PCR_15m"]
REQUIRED_GEX_COLS = ["Date", "Timestamp_dt", "Time", "Total_Net_GEX", "Z_GEX", "Total_Net_Delta_OI"]
REQUIRED_SYNTH_COLS = ["Date", "Time", "Spot", "Strike_M50", "Strike_ATM", "Strike_P50", "Synth_M50", "Synth_ATM", "Synth_P50"]
REQUIRED_STRADDLE_COLS = ["Date", "Timestamp_dt", "Time", "Spot", "ATM_Strike", "Straddle_Price", "Expected_Price"]

def init_df(name, cols):
    if name not in st.session_state or not set(cols).issubset(st.session_state[name].columns):
        st.session_state[name] = pd.DataFrame(columns=cols)

init_df("iv_spread_history", REQUIRED_HIST_COLS)
init_df("pcr_history", REQUIRED_PCR_COLS)
init_df("gex_history", REQUIRED_GEX_COLS)
init_df("synth_history", REQUIRED_SYNTH_COLS)
init_df("straddle_history", REQUIRED_STRADDLE_COLS)

if "anchor_0920_price" not in st.session_state:
    st.session_state["anchor_0920_price"] = None

if st.sidebar.button("🗑️ Reset Session Cache"):
    for k in ["iv_spread_history", "pcr_history", "gex_history", "synth_history", "straddle_history"]: st.session_state[k] = pd.DataFrame(columns=eval(f"REQUIRED_{k.split('_')[0].upper()}_COLS") if k != "iv_spread_history" else REQUIRED_HIST_COLS)
    st.session_state["anchor_0920_price"] = None
    st.cache_data.clear()
    st.rerun()

# ---------------------------------------------------------
# 6. DATA PROCESSING & NEW ENGINES LOGIC
# ---------------------------------------------------------
if error_remark: st.error(f"⚠️ **Dhan Server Error:** {error_remark}")
elif df_oc is not None and not df_oc.empty:
    atm_strike = int(round(spot_price / 50) * 50)
    df_sorted = df_oc.sort_values("Strike").copy()
    df_sorted["Cum_Net_GEX"] = df_sorted["Net_GEX"].cumsum()
    gamma_flip_strike = int(spot_price)
    for i in range(1, len(df_sorted)):
        if (df_sorted.iloc[i - 1]["Cum_Net_GEX"] < 0 and df_sorted.iloc[i]["Cum_Net_GEX"] >= 0) or (df_sorted.iloc[i - 1]["Cum_Net_GEX"] > 0 and df_sorted.iloc[i]["Cum_Net_GEX"] <= 0):
            gamma_flip_strike = int((df_sorted.iloc[i - 1]["Strike"] + df_sorted.iloc[i]["Strike"]) / 2.0)
            break

    target_row = df_oc[df_oc["Strike"] == selected_target_strike]
    target_ce_iv, target_pe_iv = (target_row["CE_IV"].values[0], target_row["PE_IV"].values[0]) if not target_row.empty else (0.0, 0.0)
    target_iv_spread = target_ce_iv - target_pe_iv

    df_filtered = df_oc[(df_oc["Strike"] >= atm_strike - 550) & (df_oc["Strike"] <= atm_strike + 550)].copy()
    strike_labels = df_filtered["Strike"].astype(str).tolist()

    total_net_gex = df_oc["Net_GEX"].sum()
    total_net_delta_oi = df_oc["Net_Delta_OI"].sum()
    total_net_dex_crores = df_oc["Net_DEX"].sum() / 100.0
    current_pcr = df_oc["PE_OI"].sum() / df_oc["CE_OI"].sum() if df_oc["CE_OI"].sum() > 0 else 0.0

    # Strict Session Cleansing when Date Changes AT 09:15 AM
    # This preserves yesterday's data on the screen until the market officially opens today.
    for hist_key in ["iv_spread_history", "pcr_history", "gex_history", "synth_history", "straddle_history"]:
        h_df = st.session_state[hist_key]
        if not h_df.empty:
            last_date = h_df.iloc[-1].get("Date")
            # If the last recorded date is not today, AND we have crossed 09:15 AM today -> WIPE IT
            if last_date != today_date_str and now_ist.time() >= datetime.time(9, 15):
                st.session_state[hist_key] = h_df.iloc[0:0] 
                if hist_key == "straddle_history": st.session_state["anchor_0920_price"] = None

    # INTRADAY TICK RECORDING (Runs only during 09:15 - 15:30 IST)
    if is_market_live:
        # IV Spread Update
        hist_df = st.session_state["iv_spread_history"]
        if hist_df.empty or hist_df.iloc[-1]["Time"] != now_time_str:
            new_ticks = [{"Date": today_date_str, "Time": now_time_str, "Strike": int(r["Strike"]), "CE_IV": float(r["CE_IV"]), "PE_IV": float(r["PE_IV"]), "IV_Spread": float(r["IV_Spread"]), "Spot": spot_price} for _, r in df_filtered.iterrows()]
            st.session_state["iv_spread_history"] = pd.concat([hist_df, pd.DataFrame(new_ticks)], ignore_index=True)

        # PCR Update
        pcr_df = st.session_state["pcr_history"]
        delta_pcr_15m = 0.0
        if pcr_df.empty or pcr_df.iloc[-1]["Time"] != now_time_str:
            if not pcr_df.empty:
                past_15m = pcr_df[pcr_df["Timestamp_dt"] <= (now_ist - datetime.timedelta(minutes=15))]
                if not past_15m.empty: delta_pcr_15m = current_pcr - past_15m.iloc[-1]["PCR"]
            st.session_state["pcr_history"] = pd.concat([pcr_df, pd.DataFrame([{"Date": today_date_str, "Timestamp_dt": now_ist, "Time": now_time_str, "PCR": current_pcr, "Delta_PCR_5m": 0.0, "Delta_PCR_15m": delta_pcr_15m}])], ignore_index=True)

        # Z-GEX & Delta OI Update
        gex_df = st.session_state["gex_history"]
        current_z_gex = 0.0
        if gex_df.empty or gex_df.iloc[-1]["Time"] != now_time_str:
            if len(gex_df) >= 2:
                recent_20 = gex_df["Total_Net_GEX"].tail(20)
                sigma = recent_20.std()
                if sigma > 0: current_z_gex = (total_net_gex - recent_20.mean()) / sigma
            st.session_state["gex_history"] = pd.concat([gex_df, pd.DataFrame([{"Date": today_date_str, "Timestamp_dt": now_ist, "Time": now_time_str, "Total_Net_GEX": total_net_gex, "Z_GEX": current_z_gex, "Total_Net_Delta_OI": total_net_delta_oi}])], ignore_index=True)

        # Synthetic Engine Update
        synth_df = st.session_state["synth_history"]
        s_m50, s_p50 = atm_strike - 50, atm_strike + 50
        r_m50, r_atm, r_p50 = df_oc[df_oc["Strike"] == s_m50], df_oc[df_oc["Strike"] == atm_strike], df_oc[df_oc["Strike"] == s_p50]
        sy_m50 = s_m50 + r_m50["CE_LTP"].values[0] - r_m50["PE_LTP"].values[0] if not r_m50.empty else spot_price
        sy_atm = atm_strike + r_atm["CE_LTP"].values[0] - r_atm["PE_LTP"].values[0] if not r_atm.empty else spot_price
        sy_p50 = s_p50 + r_p50["CE_LTP"].values[0] - r_p50["PE_LTP"].values[0] if not r_p50.empty else spot_price
        
        if synth_df.empty or synth_df.iloc[-1]["Time"] != now_time_str:
            st.session_state["synth_history"] = pd.concat([synth_df, pd.DataFrame([{"Date": today_date_str, "Time": now_time_str, "Spot": spot_price, "Strike_M50": s_m50, "Strike_ATM": atm_strike, "Strike_P50": s_p50, "Synth_M50": sy_m50, "Synth_ATM": sy_atm, "Synth_P50": sy_p50}])], ignore_index=True)

        # 09:20 AM Straddle Decay Anchor Update
        straddle_df = st.session_state["straddle_history"]
        atm_straddle_price = (r_atm["CE_LTP"].values[0] + r_atm["PE_LTP"].values[0]) if not r_atm.empty else 0.0
        
        if now_ist.time() >= datetime.time(9, 20):
            if st.session_state["anchor_0920_price"] is None and atm_straddle_price > 0:
                st.session_state["anchor_0920_price"] = atm_straddle_price
            
            anchor_p = st.session_state["anchor_0920_price"]
            if anchor_p:
                t_elapsed = (now_ist - now_ist.replace(hour=9, minute=20, second=0)).total_seconds() / 60.0
                expected_p = anchor_p * (1 - 0.25 * math.sqrt(t_elapsed / 375.0)) if t_elapsed > 0 else anchor_p
                
                if straddle_df.empty or straddle_df.iloc[-1]["Time"] != now_time_str:
                    st.session_state["straddle_history"] = pd.concat([straddle_df, pd.DataFrame([{"Date": today_date_str, "Timestamp_dt": now_ist, "Time": now_time_str, "Spot": spot_price, "ATM_Strike": atm_strike, "Straddle_Price": atm_straddle_price, "Expected_Price": expected_p}])], ignore_index=True)

    # Read latest values
    pcr_df, gex_df, synth_df, straddle_df = st.session_state["pcr_history"], st.session_state["gex_history"], st.session_state["synth_history"], st.session_state["straddle_history"]
    delta_pcr_15m = pcr_df.iloc[-1]["Delta_PCR_15m"] if not pcr_df.empty else 0.0
    current_z_gex = gex_df.iloc[-1]["Z_GEX"] if not gex_df.empty else 0.0
    
    delta_oi_roc_1m = 0.0
    if not gex_df.empty:
        past_1m = gex_df[gex_df["Timestamp_dt"] <= (now_ist - datetime.timedelta(minutes=1))]
        if not past_1m.empty: delta_oi_roc_1m = total_net_delta_oi - past_1m.iloc[-1]["Total_Net_Delta_OI"]

    s_m50, s_p50 = atm_strike - 50, atm_strike + 50
    r_m50, r_atm, r_p50 = df_oc[df_oc["Strike"] == s_m50], df_oc[df_oc["Strike"] == atm_strike], df_oc[df_oc["Strike"] == s_p50]
    sy_m50 = s_m50 + r_m50["CE_LTP"].values[0] - r_m50["PE_LTP"].values[0] if not r_m50.empty else spot_price
    sy_atm = atm_strike + r_atm["CE_LTP"].values[0] - r_atm["PE_LTP"].values[0] if not r_atm.empty else spot_price
    sy_p50 = s_p50 + r_p50["CE_LTP"].values[0] - r_p50["PE_LTP"].values[0] if not r_p50.empty else spot_price

    # Regime Interpretation Logics
    if current_z_gex < -2.0: z_signal, z_color, z_card_border = "GAMMA COLLAPSE", "sub-red", "metric-card-red"
    elif -1.0 <= current_z_gex <= 1.0: z_signal, z_color, z_card_border = "NORMAL DAMPENING", "sub-green", "metric-card-green"
    else: z_signal, z_color, z_card_border = "TRANSITION ZONE", "sub-amber", "metric-card-amber"

    if total_net_delta_oi > 50000: dir_signal, dir_color = "STRONGLY BULLISH", "sub-green"
    elif total_net_delta_oi > 10000: dir_signal, dir_color = "MILDLY BULLISH", "sub-green"
    elif total_net_delta_oi < -50000: dir_signal, dir_color = "STRONGLY BEARISH", "sub-red"
    elif total_net_delta_oi < -10000: dir_signal, dir_color = "MILDLY BEARISH", "sub-red"
    else: dir_signal, dir_color = "NEUTRAL / RANGEBOUND", "sub-amber"

    if (sy_m50 > spot_price + 1.0) and (sy_atm > spot_price + 1.0) and (sy_p50 > spot_price + 1.0): synth_flag_text, synth_flag_color = "🟢 BULLISH ACCUMULATION FLAG: Synthetics Pricing at Premium (Spot Lags)", "#00E676"
    elif (sy_m50 < spot_price - 1.0) and (sy_atm < spot_price - 1.0) and (sy_p50 < spot_price - 1.0): synth_flag_text, synth_flag_color = "🔴 BEARISH DISTRIBUTION FLAG: Synthetics Pricing at Discount (Spot Leads)", "#FF5252"
    else: synth_flag_text, synth_flag_color = "⚪ NEUTRAL: Synthetic Parity Tracking Spot Closely", "#8A93A6"
    
    straddle_regime = "AWAITING 09:20 ANCHOR"
    straddle_color = "#8A93A6"
    if not straddle_df.empty:
        last_s = straddle_df.iloc[-1]
        if last_s["Straddle_Price"] > last_s["Expected_Price"] + 5: straddle_regime, straddle_color = "🔴 VOLATILITY COIL (IV Expanding)", "#FF5252"
        elif last_s["Straddle_Price"] < last_s["Expected_Price"] - 5: straddle_regime, straddle_color = "🟢 IV CRUSH (Rapid Decay)", "#00E676"
        else: straddle_regime, straddle_color = "⚪ NORMAL THEORETICAL DECAY", "#29B6F6"


    # ---------------------------------------------------------
    # 7. DASHBOARD UI (PRINCE PAX COMMAND CENTER)
    # ---------------------------------------------------------
    st.markdown(f"### PRINCE PAX DASHBOARD")
    status_class = "status-live" if is_market_live else "status-closed"
    status_text = "🟢 LIVE MARKET" if is_market_live else "🟠 MARKET CLOSED (Showing Previous Session Data)"
    st.markdown(f'<div class="status-badge {status_class}">{status_text} | Expiry: {selected_expiry} | IST: {now_time_str}</div>', unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    # ================= ROW 1: TOP SUMMARY BANNER =================
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    with m1: st.markdown(f'<div class="metric-card metric-card-amber"><div class="info-tooltip">ⓘ<span class="tooltip-text">Current Spot Price of Nifty 50.</span></div><div class="metric-title">NIFTY SPOT</div><div class="metric-value">₹{spot_price:,.2f}</div><div class="metric-sub sub-amber">ATM: {atm_strike}</div></div>', unsafe_allow_html=True)
    with m2: st.markdown(f'<div class="metric-card {"metric-card-green" if target_iv_spread >= 0 else "metric-card-red"}"><div class="info-tooltip">ⓘ<span class="tooltip-text"><b>IV Spread = Call IV - Put IV.</b><br>Rising values indicate Call accumulation.</span></div><div class="metric-title">{selected_target_strike} IV SPREAD</div><div class="metric-value">{target_iv_spread:+.2f}%</div><div class="metric-sub {"sub-green" if target_iv_spread >= 0 else "sub-red"}">CE {target_ce_iv:.1f}% | PE {target_pe_iv:.1f}%</div></div>', unsafe_allow_html=True)
    with m3: st.markdown(f'<div class="metric-card {"metric-card-green" if delta_pcr_15m >= 0.15 else ("metric-card-red" if delta_pcr_15m <= -0.15 else "metric-card-amber")}"><div class="info-tooltip">ⓘ<span class="tooltip-text"><b>15m PCR Velocity.</b><br>> +0.15 = Bullish.<br>< -0.15 = Bearish.</span></div><div class="metric-title">ΔPCR 15M VELOCITY</div><div class="metric-value">{delta_pcr_15m:+.2f}</div><div class="metric-sub {"sub-green" if delta_pcr_15m >= 0.15 else ("sub-red" if delta_pcr_15m <= -0.15 else "sub-amber")}">PCR: {current_pcr:.2f}</div></div>', unsafe_allow_html=True)
    with m4: st.markdown(f'<div class="metric-card {"metric-card-green" if total_net_delta_oi >= 0 else "metric-card-red"}"><div class="info-tooltip">ⓘ<span class="tooltip-text"><b>Net Delta Exposure (Rupee Value).</b><br>Positive = Dealers buy dips (Supportive).</span></div><div class="metric-title">NET DELTA DEX</div><div class="metric-value">₹{total_net_dex_crores:+.2f} Cr</div><div class="metric-sub {dir_color}">{total_net_delta_oi:+,.0f} Cont</div></div>', unsafe_allow_html=True)
    with m5: st.markdown(f'<div class="metric-card {"metric-card-green" if total_net_gex >= 0 else "metric-card-red"}"><div class="info-tooltip">ⓘ<span class="tooltip-text"><b>Raw Gamma Exposure (Total).</b><br>Positive = Volatility Dampening.</span></div><div class="metric-title">RAW NET GEX</div><div class="metric-value">₹{total_net_gex:,.1f}L</div><div class="metric-sub {"sub-green" if total_net_gex >= 0 else "sub-red"}">Across Chain</div></div>', unsafe_allow_html=True)
    with m6: st.markdown(f'<div class="metric-card {z_card_border}"><div class="info-tooltip">ⓘ<span class="tooltip-text"><b>Statistical Gamma Regime.</b><br>Below -2.0 = Dealer power collapsed (Squeeze).</span></div><div class="metric-title">Z-GEX SCORE</div><div class="metric-value">{current_z_gex:+.2f}</div><div class="metric-sub {z_color}">{z_signal}</div></div>', unsafe_allow_html=True)

    # ================= ROW 2: LIVE INTRADAY VELOCITY CHARTS =================
    r2_col1, r2_col2 = st.columns(2)
    with r2_col1:
        st.markdown(f'<div class="chart-container"><div class="info-tooltip">ⓘ<span class="tooltip-text">Tracks the tick-by-tick difference between Call IV and Put IV. Watch for divergences from spot price.</span></div><div class="chart-title">Intraday IV Spread Movement ({selected_target_strike})</div>', unsafe_allow_html=True)
        fig_ts = go.Figure()
        sh = st.session_state["iv_spread_history"]
        if not sh.empty: fig_ts.add_trace(go.Scatter(x=sh[sh["Strike"] == selected_target_strike]["Time"], y=sh[sh["Strike"] == selected_target_strike]["IV_Spread"], mode="lines+markers", line=dict(color="#29B6F6", width=2), marker=dict(size=3)))
        fig_ts.add_hline(y=0, line_dash="dash", line_color="white", opacity=0.3)
        fig_ts.update_xaxes(range=["09:15:00", "15:30:00"], dtick="3600000", gridcolor="#2A2E39")
        fig_ts.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=10, b=0), height=250)
        st.plotly_chart(fig_ts, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with r2_col2:
        st.markdown('<div class="chart-container"><div class="info-tooltip">ⓘ<span class="tooltip-text">Measures speed of option writing. >+0.15 signals aggressive put writing (support). <-0.15 signals aggressive call writing (resistance).</span></div><div class="chart-title">15-Min PCR Velocity (ΔPCR)</div>', unsafe_allow_html=True)
        fig_pcr = go.Figure()
        if not pcr_df.empty:
            colors = ["#00E676" if v >= 0.15 else ("#FF5252" if v <= -0.15 else "#8A93A6") for v in pcr_df["Delta_PCR_15m"]]
            fig_pcr.add_trace(go.Bar(x=pcr_df["Time"], y=pcr_df["Delta_PCR_15m"], marker_color=colors))
        fig_pcr.add_hline(y=0.15, line_dash="dash", line_color="#00E676")
        fig_pcr.add_hline(y=-0.15, line_dash="dash", line_color="#FF5252")
        fig_pcr.update_xaxes(range=["09:15:00", "15:30:00"], dtick="3600000", gridcolor="#2A2E39")
        fig_pcr.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=10, b=0), height=250)
        st.plotly_chart(fig_pcr, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # ================= ROW 3: REAL-TIME DELTA OI & Z-GEX =================
    r3_col1, r3_col2 = st.columns(2)
    with r3_col1:
        st.markdown(f'<div class="chart-container"><div class="info-tooltip">ⓘ<span class="tooltip-text"><b>Real-Time Delta-Weighted Net OI.</b><br>Tracks total directional risk. A sudden drop while near resistance signals a short-covering squeeze. Current 1m ROC: {delta_oi_roc_1m:+.0f}</span></div><div class="chart-title">Real-Time Net Delta OI Curve (Contracts)</div>', unsafe_allow_html=True)
        fig_doi = go.Figure()
        if not gex_df.empty: fig_doi.add_trace(go.Scatter(x=gex_df["Time"], y=gex_df["Total_Net_Delta_OI"], mode="lines", fill='tozeroy', line=dict(color="#00E676" if total_net_delta_oi>0 else "#FF5252", width=2)))
        fig_doi.add_hline(y=0, line_dash="dash", line_color="white", opacity=0.3)
        fig_doi.update_xaxes(range=["09:15:00", "15:30:00"], dtick="3600000", gridcolor="#2A2E39")
        fig_doi.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=10, b=0), height=250)
        st.plotly_chart(fig_doi, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with r3_col2:
        st.markdown('<div class="chart-container"><div class="info-tooltip">ⓘ<span class="tooltip-text">Isolates structural regime shifts by comparing current GEX to its rolling mean. Watch for breakdowns past -2.0.</span></div><div class="chart-title">Normalized Gamma Z-Score (ZGEX) Tracker</div>', unsafe_allow_html=True)
        fig_zgex = go.Figure()
        if not gex_df.empty: fig_zgex.add_trace(go.Scatter(x=gex_df["Time"], y=gex_df["Z_GEX"], mode="lines", fill='tozeroy', line=dict(color="#AB47BC", width=2)))
        fig_zgex.add_hline(y=1.0, line_dash="solid", line_color="#00E676", opacity=0.3)
        fig_zgex.add_hline(y=-1.0, line_dash="solid", line_color="#00E676", opacity=0.3)
        fig_zgex.add_hline(y=-2.0, line_dash="dash", line_color="#FF5252")
        fig_zgex.update_xaxes(range=["09:15:00", "15:30:00"], dtick="3600000", gridcolor="#2A2E39")
        fig_zgex.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=10, b=0), height=250)
        st.plotly_chart(fig_zgex, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # ================= ROW 4: STRADDLE DECAY & SYNTHETIC ENGINE =================
    r4_col1, r4_col2 = st.columns(2)
    with r4_col1:
        st.markdown(f'<div class="chart-container"><div class="info-tooltip">ⓘ<span class="tooltip-text"><b>Anchored ATM Straddle Decay.</b><br>Tracks total ATM Straddle vs Theoretical Decay. If actual price holds steady/rises while Spot is boxed, Volatility Coil is active (Breakout imminent).</span></div><div class="chart-title">09:20 Anchored Straddle vs Theoretical Decay</div>', unsafe_allow_html=True)
        st.markdown(f"**Regime Status:** <span style='color: {straddle_color};'>{straddle_regime}</span>", unsafe_allow_html=True)
        fig_str = go.Figure()
        if not straddle_df.empty:
            fig_str.add_trace(go.Scatter(x=straddle_df["Time"], y=straddle_df["Straddle_Price"], mode="lines", name="Actual Straddle", line=dict(color="#FFD700", width=2)))
            fig_str.add_trace(go.Scatter(x=straddle_df["Time"], y=straddle_df["Expected_Price"], mode="lines", name="Theoretical (√T)", line=dict(color="#29B6F6", width=2, dash="dot")))
        fig_str.update_xaxes(range=["09:15:00", "15:30:00"], dtick="3600000", gridcolor="#2A2E39")
        fig_str.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=10, b=0), height=270, legend=dict(orientation="h", y=1.1))
        st.plotly_chart(fig_str, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with r4_col2:
        st.markdown(f'<div class="chart-container"><div class="info-tooltip">ⓘ<span class="tooltip-text"><b>Multi-Strike Synthetic Parity (K+C-P).</b><br>If all synthetics jump above Spot, it signals institutional stealth accumulation via options before spot moves.</span></div><div class="chart-title">Multi-Strike Synthetic Parity Engine</div>', unsafe_allow_html=True)
        st.markdown(f"**Live Regime Signal:** <span style='color: {synth_flag_color};'>{synth_flag_text}</span>", unsafe_allow_html=True)
        fig_synth = go.Figure()
        if not synth_df.empty:
            fig_synth.add_trace(go.Scatter(x=synth_df["Time"], y=synth_df["Spot"], mode="lines", name="Nifty Spot", line=dict(color="#FFD700", width=2)))
            fig_synth.add_trace(go.Scatter(x=synth_df["Time"], y=synth_df["Synth_M50"], mode="lines", name=f"ITM ({strike_m50})", line=dict(color="#00E676", width=1.5, dash="dot")))
            fig_synth.add_trace(go.Scatter(x=synth_df["Time"], y=synth_df["Synth_ATM"], mode="lines", name=f"ATM ({atm_strike})", line=dict(color="#29B6F6", width=1.5, dash="dot")))
            fig_synth.add_trace(go.Scatter(x=synth_df["Time"], y=synth_df["Synth_P50"], mode="lines", name=f"OTM ({strike_p50})", line=dict(color="#FF5252", width=1.5, dash="dot")))
        fig_synth.update_xaxes(range=["09:15:00", "15:30:00"], dtick="3600000", gridcolor="#2A2E39")
        fig_synth.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=10, b=0), height=270, legend=dict(orientation="h", y=1.1))
        st.plotly_chart(fig_synth, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # ================= ROW 5: EXPOSURE PROFILES (DEX & GEX) =================
    r5_col1, r5_col2 = st.columns(2)
    with r5_col1:
        st.markdown('<div class="chart-container"><div class="info-tooltip">ⓘ<span class="tooltip-text">Total Rupee Value of Delta per strike. Includes Spot line.</span></div><div class="chart-title">Net Delta Exposure (DEX) By Strike</div>', unsafe_allow_html=True)
        fig_dex = go.Figure()
        fig_dex.add_trace(go.Bar(x=df_filtered["Strike"], y=df_filtered["Net_DEX"], marker_color=["#00E676" if val >= 0 else "#FF5252" for val in df_filtered["Net_DEX"]]))
        fig_dex.add_vline(x=spot_price, line_dash="solid", line_color="#FFD700")
        fig_dex.add_annotation(x=spot_price, y=0.95, yref="paper", text="Spot", showarrow=False, font=dict(color="#FFD700", size=10), xanchor="left")
        fig_dex.update_xaxes(range=[atm_strike - 550, atm_strike + 550], tickmode='array', tickvals=df_filtered["Strike"], ticktext=strike_labels, tickangle=-45, gridcolor="#2A2E39")
        fig_dex.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=10, b=0), height=250)
        st.plotly_chart(fig_dex, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with r5_col2:
        st.markdown('<div class="chart-container"><div class="info-tooltip">ⓘ<span class="tooltip-text">Resistance (Call Walls - Red) and Support (Put Walls - Green). Yellow = Spot, Blue = Gamma Flip.</span></div><div class="chart-title">Net GEX Profile</div>', unsafe_allow_html=True)
        fig_gex = go.Figure()
        fig_gex.add_trace(go.Bar(x=df_filtered["Strike"], y=df_filtered["Net_GEX"], marker_color=["#00E676" if g >= 0 else "#FF5252" for g in df_filtered["Net_GEX"]]))
        fig_gex.add_vline(x=spot_price, line_dash="solid", line_color="#FFD700")
        fig_gex.add_annotation(x=spot_price, y=0.95, yref="paper", text="Spot", showarrow=False, font=dict(color="#FFD700", size=10), xanchor="left")
        fig_gex.add_vline(x=gamma_flip_strike, line_dash="dash", line_color="#29B6F6")
        fig_gex.add_annotation(x=gamma_flip_strike, y=0.85, yref="paper", text="Flip", showarrow=False, font=dict(color="#29B6F6", size=10), xanchor="left")
        fig_gex.update_xaxes(range=[atm_strike - 550, atm_strike + 550], tickmode='array', tickvals=df_filtered["Strike"], ticktext=strike_labels, tickangle=-45, gridcolor="#2A2E39")
        fig_gex.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=10, b=0), height=250, showlegend=False)
        st.plotly_chart(fig_gex, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # ================= ROW 6: VOLATILITY TERM STRUCTURE =================
    r6_col1, r6_col2 = st.columns(2)
    df_vol_struct = fetch_multi_expiry_vol_structure(spot_price)
    with r6_col1:
        st.markdown('<div class="chart-container"><div class="info-tooltip">ⓘ<span class="tooltip-text">Implied forward variance (4 Expiries).</span></div><div class="chart-title">Forward Vol Term Structure</div>', unsafe_allow_html=True)
        if not df_vol_struct.empty and len(df_vol_struct) >= 2:
            fig_fwd = go.Figure()
            fig_fwd.add_trace(go.Scatter(x=df_vol_struct["Expiry"], y=df_vol_struct["Forward_Vol"], mode="lines+markers", line=dict(color="#00E676", width=2.5), marker=dict(size=8)))
            fig_fwd.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=10, b=0), height=220)
            st.plotly_chart(fig_fwd, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with r6_col2:
        st.markdown('<div class="chart-container"><div class="info-tooltip">ⓘ<span class="tooltip-text">Cumulative Average IV across 4 Expiries.</span></div><div class="chart-title">Cumulative Vol Curve</div>', unsafe_allow_html=True)
        if not df_vol_struct.empty and len(df_vol_struct) >= 2:
            fig_vol_curve = go.Figure()
            fig_vol_curve.add_trace(go.Scatter(x=df_vol_struct["Expiry"], y=df_vol_struct["Mean_IV"], mode="lines+markers", line=dict(color="#AB47BC", width=2.5), marker=dict(size=8)))
            fig_vol_curve.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=10, b=0), height=220)
            st.plotly_chart(fig_vol_curve, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # ================= ROW 7: HEAVYWEIGHT FILTER (PROXY UI) =================
    st.markdown('<div class="chart-container"><div class="info-tooltip">ⓘ<span class="tooltip-text"><b>Hard Execution Filter.</b> If Spot breaks out but Heavyweights dump, avoid the trade. (Uses simulated synthetic proxy until Websocket integration is active).</span></div><div class="chart-title">⚖️ Top-3 Heavyweight Basket & Futures Basis Filter [SYNTHETIC PROXY]</div>', unsafe_allow_html=True)
    
    # Placeholder proxy generation to demonstrate UI for user
    hf_times = pd.date_range(start="09:15", end="15:30", freq="5min").strftime("%H:%M:%S")
    proxy_basis = np.linspace(15, -5, len(hf_times)) + np.random.normal(0, 2, len(hf_times))
    proxy_cvd = np.cumsum(np.random.normal(0, 100, len(hf_times)))
    
    r7_col1, r7_col2 = st.columns(2)
    with r7_col1:
        fig_basis = go.Figure()
        fig_basis.add_trace(go.Scatter(x=hf_times, y=proxy_basis, mode="lines", fill='tozeroy', line=dict(color="#FFD700", width=2)))
        fig_basis.add_hline(y=0, line_dash="dash", line_color="white", opacity=0.3)
        fig_basis.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=10, b=0), height=200, title="Simulated Nifty Futures Basis")
        st.plotly_chart(fig_basis, use_container_width=True)
    with r7_col2:
        fig_cvd = go.Figure()
        fig_cvd.add_trace(go.Scatter(x=hf_times, y=proxy_cvd, mode="lines", fill='tozeroy', line=dict(color="#29B6F6", width=2)))
        fig_cvd.add_hline(y=0, line_dash="dash", line_color="white", opacity=0.3)
        fig_cvd.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=10, b=0), height=200, title="Simulated Heavyweight CVD (HDFCBANK/RELIANCE/ICICI)")
        st.plotly_chart(fig_cvd, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # ================= ROW 8: DATA GRID =================
    st.markdown('<div class="chart-container"><div class="chart-title">Institutional Options Chain Grid</div>', unsafe_allow_html=True)
    grid_df = df_filtered[["Strike", "CE_LTP", "PE_LTP", "CE_OI", "PE_OI", "CE_Delta", "PE_Delta", "Net_Delta_OI", "Net_DEX", "Net_GEX", "Net_VEX", "Net_CHEX", "CE_IV", "PE_IV", "IV_Spread"]].copy()
    st.dataframe(grid_df.style.format({"Strike": "{:.0f}", "CE_LTP": "₹{:.2f}", "PE_LTP": "₹{:.2f}", "CE_OI": "{:,.0f}", "PE_OI": "{:,.0f}", "CE_Delta": "{:.2f}", "PE_Delta": "{:.2f}", "Net_Delta_OI": "{:+,.0f}", "Net_DEX": "{:+,.1f}L", "Net_GEX": "{:+,.1f}L", "Net_VEX": "{:+,.2f}", "Net_CHEX": "{:+,.2f}", "CE_IV": "{:.1f}%", "PE_IV": "{:.1f}%", "IV_Spread": "{:+.2f}%"}), use_container_width=True, height=350)
    st.markdown('</div>', unsafe_allow_html=True)
