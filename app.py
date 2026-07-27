import datetime
import math
import time
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st
from streamlit_autorefresh import st_autorefresh

# ---------------------------------------------------------
# 1. PAGE SETUP & TRADYTICS-STYLE TERMINAL CSS
# ---------------------------------------------------------
st.set_page_config(
    page_title="Nifty Quant & Vol Desk | Tradytics Style",
    layout="wide",
    initial_sidebar_state="collapsed", # Collapsed by default for full-screen dashboard
)

st.markdown(
    """
    <style>
    .stApp { background-color: #0A0A0A; color: #D1D4DC; font-family: 'Inter', sans-serif; }
    section[data-testid="stSidebar"] { background-color: #111115 !important; border-right: 1px solid #2A2E39; }
    
    /* Sleek Dense Metric Cards */
    .metric-card {
        background: #14151A;
        border: 1px solid #2A2E39;
        border-radius: 6px;
        padding: 10px 14px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.5);
        margin-bottom: 12px;
        border-top: 3px solid #3B4252;
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

    /* Container for Charts */
    .chart-container {
        background: #14151A;
        border: 1px solid #2A2E39;
        border-radius: 6px;
        padding: 12px;
        margin-bottom: 16px;
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

    /* Status Badges */
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
# 2. BLACK-SCHOLES GREEK ENGINE
# ---------------------------------------------------------
def calculate_bs_greeks(S, K, T, sigma, r=0.07):
    if T <= 1e-5 or sigma <= 1e-4 or S <= 0 or K <= 0:
        return 0.0, 0.0, 0.0
    try:
        d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        pdf_d1 = (1.0 / math.sqrt(2 * math.pi)) * math.exp(-0.5 * d1 * d1)
        gamma = pdf_d1 / (S * sigma * math.sqrt(T))
        vanna = -pdf_d1 * d2 / sigma
        charm = -pdf_d1 * (2 * r * math.sqrt(T) - d2 * sigma) / (2 * T * sigma)
        return gamma, vanna, charm
    except Exception:
        return 0.0, 0.0, 0.0


# ---------------------------------------------------------
# 3. DIRECT REST API DATA ENGINE
# ---------------------------------------------------------
@st.cache_data(ttl=3)
def fetch_gex_option_chain(expiry_date):
    url = "https://api.dhan.co/v2/optionchain"
    headers = {
        "client-id": CLIENT_ID,
        "access-token": ACCESS_TOKEN,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = {"UnderlyingScrip": 13, "UnderlyingSeg": "IDX_I", "Expiry": expiry_date}

    try:
        res = requests.post(url, headers=headers, json=payload, timeout=10)
        data = res.json()

        if res.status_code == 200 and data.get("status") == "success":
            raw_data = data.get("data", {})
            spot_price = float(raw_data.get("last_price", 0.0))
            oc_raw = raw_data.get("oc", {})

            if not oc_raw:
                return None, spot_price, f"No contracts returned for expiry {expiry_date}."

            exp_date_obj = datetime.datetime.strptime(expiry_date, "%Y-%m-%d").date()
            days_to_exp = max((exp_date_obj - datetime.date.today()).days, 1)
            T_years = days_to_exp / 365.0

            records = []
            for strike_str, details in oc_raw.items():
                strike = int(float(strike_str))
                ce = details.get("ce", {})
                pe = details.get("pe", {})

                ce_oi = float(ce.get("oi", 0))
                pe_oi = float(pe.get("oi", 0))
                ce_ltp = float(ce.get("last_price", 0))
                pe_ltp = float(pe.get("last_price", 0))
                ce_iv = float(ce.get("implied_volatility", 0)) / 100.0
                pe_iv = float(pe.get("implied_volatility", 0)) / 100.0
                ce_delta = float(ce.get("greeks", {}).get("delta", 0))
                pe_delta = float(pe.get("greeks", {}).get("delta", 0))
                ce_gamma = float(ce.get("greeks", {}).get("gamma", 0))
                pe_gamma = float(pe.get("greeks", {}).get("gamma", 0))

                if ce_gamma <= 0 and ce_iv > 0:
                    ce_gamma, ce_vanna, ce_charm = calculate_bs_greeks(spot_price, strike, T_years, ce_iv)
                else:
                    _, ce_vanna, ce_charm = calculate_bs_greeks(spot_price, strike, T_years, max(ce_iv, 0.15))

                if pe_gamma <= 0 and pe_iv > 0:
                    pe_gamma, pe_vanna, pe_charm = calculate_bs_greeks(spot_price, strike, T_years, pe_iv)
                else:
                    _, pe_vanna, pe_charm = calculate_bs_greeks(spot_price, strike, T_years, max(pe_iv, 0.15))

                call_gex = (ce_oi * ce_gamma * (spot_price**2) * 0.01 * NIFTY_LOT_SIZE / 1e5)
                put_gex = (-pe_oi * pe_gamma * (spot_price**2) * 0.01 * NIFTY_LOT_SIZE / 1e5)
                net_gex = call_gex + put_gex

                ce_delta_oi = ce_oi * ce_delta
                pe_delta_oi = pe_oi * pe_delta
                net_delta_oi = ce_delta_oi + pe_delta_oi
                net_dex = net_delta_oi * spot_price * NIFTY_LOT_SIZE / 1e5

                net_vex = ((ce_oi * ce_vanna) - (pe_oi * pe_vanna)) * NIFTY_LOT_SIZE / 1e3
                net_chex = ((ce_oi * ce_charm) - (pe_oi * pe_charm)) * NIFTY_LOT_SIZE / 1e3

                records.append({
                    "Strike": strike, "CE_LTP": ce_ltp, "PE_LTP": pe_ltp, "CE_OI": ce_oi, "PE_OI": pe_oi,
                    "CE_Delta": ce_delta, "PE_Delta": pe_delta, "Net_Delta_OI": net_delta_oi, "Net_DEX": net_dex,
                    "Call_GEX": call_gex, "Put_GEX": put_gex, "Net_GEX": net_gex, "Net_VEX": net_vex, "Net_CHEX": net_chex,
                    "CE_IV": ce_iv * 100.0, "PE_IV": pe_iv * 100.0, "IV_Spread": (ce_iv * 100.0) - (pe_iv * 100.0),
                })

            df = pd.DataFrame(records).sort_values("Strike").reset_index(drop=True)
            return df, spot_price, None
        else:
            return None, 0.0, str(data.get("remarks") or data.get("message") or f"HTTP {res.status_code}")
    except Exception as e:
        return None, 0.0, f"Connection Error: {str(e)}"

@st.cache_data(ttl=300)
def fetch_expiry_list_direct():
    url = "https://api.dhan.co/v2/optionchain/expirylist"
    headers = {"client-id": CLIENT_ID, "access-token": ACCESS_TOKEN, "Content-Type": "application/json"}
    payload = {"UnderlyingScrip": 13, "UnderlyingSeg": "IDX_I"}
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=5)
        data = res.json()
        if res.status_code == 200 and data.get("status") == "success":
            return data.get("data", [])
    except:
        pass
    return []


# ---------------------------------------------------------
# 4. CONTROLS, MEMORY INIT & LIVE SESSION LOGIC
# ---------------------------------------------------------
st.sidebar.header("⚙️ Command Center Controls")

auto_refresh = st.sidebar.checkbox("Live Auto-Refresh (5s)", value=True)
if auto_refresh:
    st_autorefresh(interval=5000, key="datarefresh")

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

df_oc, spot_price, error_remark = fetch_gex_option_chain(selected_expiry)

selected_target_strike = None
if df_oc is not None and not df_oc.empty:
    atm_strike_val = int(round(spot_price / 50) * 50)
    all_strikes = df_oc["Strike"].tolist()
    default_index = all_strikes.index(atm_strike_val) if atm_strike_val in all_strikes else 0
    selected_target_strike = st.sidebar.selectbox("🎯 Target Strike", all_strikes, index=default_index)

# Data Memory DataFrames (Ensure required columns to avoid KeyErrors)
REQUIRED_HIST_COLS = ["Date", "Time", "Strike", "CE_IV", "PE_IV", "IV_Spread", "Spot"]
REQUIRED_PCR_COLS = ["Date", "Timestamp_dt", "Time", "PCR", "Delta_PCR_5m", "Delta_PCR_15m"]
REQUIRED_GEX_COLS = ["Date", "Timestamp_dt", "Time", "Total_Net_GEX", "Z_GEX"]

if "iv_spread_history" not in st.session_state or not set(REQUIRED_HIST_COLS).issubset(st.session_state["iv_spread_history"].columns):
    st.session_state["iv_spread_history"] = pd.DataFrame(columns=REQUIRED_HIST_COLS)
if "pcr_history" not in st.session_state or not set(REQUIRED_PCR_COLS).issubset(st.session_state["pcr_history"].columns):
    st.session_state["pcr_history"] = pd.DataFrame(columns=REQUIRED_PCR_COLS)
if "gex_history" not in st.session_state or not set(REQUIRED_GEX_COLS).issubset(st.session_state["gex_history"].columns):
    st.session_state["gex_history"] = pd.DataFrame(columns=REQUIRED_GEX_COLS)

if st.sidebar.button("🗑️ Reset Session Cache"):
    st.session_state["iv_spread_history"] = pd.DataFrame(columns=REQUIRED_HIST_COLS)
    st.session_state["pcr_history"] = pd.DataFrame(columns=REQUIRED_PCR_COLS)
    st.session_state["gex_history"] = pd.DataFrame(columns=REQUIRED_GEX_COLS)
    st.cache_data.clear()
    st.rerun()


# ---------------------------------------------------------
# 5. DATA PROCESSING & Z-SCORE ENGINE
# ---------------------------------------------------------
if error_remark:
    st.error(f"⚠️ **Dhan Server Error:** {error_remark}")
elif df_oc is not None and not df_oc.empty:
    atm_strike = int(round(spot_price / 50) * 50)
    
    # Base Option Data
    target_row = df_oc[df_oc["Strike"] == selected_target_strike]
    target_ce_iv = target_row["CE_IV"].values[0] if not target_row.empty else 0.0
    target_pe_iv = target_row["PE_IV"].values[0] if not target_row.empty else 0.0
    target_iv_spread = target_ce_iv - target_pe_iv

    df_filtered = df_oc[(df_oc["Strike"] >= atm_strike - 500) & (df_oc["Strike"] <= atm_strike + 500)].copy()
    df_filtered["Strike_Label"] = df_filtered["Strike"].astype(str)

    total_net_gex = df_oc["Net_GEX"].sum()
    total_net_delta_oi = df_oc["Net_Delta_OI"].sum()
    total_net_dex_crores = df_oc["Net_DEX"].sum() / 100.0

    # 1. IV Spread Memory Update
    hist_df = st.session_state["iv_spread_history"]
    if is_market_live and not hist_df.empty and hist_df.iloc[-1]["Date"] != today_date_str:
        hist_df = pd.DataFrame(columns=REQUIRED_HIST_COLS)
    
    if is_market_live or hist_df.empty:
        if hist_df.empty or hist_df.iloc[-1]["Time"] != now_time_str:
            new_ticks = [{"Date": today_date_str, "Time": now_time_str, "Strike": int(r["Strike"]), "CE_IV": float(r["CE_IV"]), "PE_IV": float(r["PE_IV"]), "IV_Spread": float(r["IV_Spread"]), "Spot": spot_price} for _, r in df_filtered.iterrows()]
            st.session_state["iv_spread_history"] = pd.concat([hist_df, pd.DataFrame(new_ticks)], ignore_index=True)

    # 2. PCR Velocity Memory Update
    total_call_oi = df_oc["CE_OI"].sum()
    total_put_oi = df_oc["PE_OI"].sum()
    current_pcr = total_put_oi / total_call_oi if total_call_oi > 0 else 0.0

    pcr_df = st.session_state["pcr_history"]
    if is_market_live and not pcr_df.empty and pcr_df.iloc[-1]["Date"] != today_date_str:
        pcr_df = pd.DataFrame(columns=REQUIRED_PCR_COLS)

    delta_pcr_15m = 0.0
    if is_market_live or pcr_df.empty:
        if pcr_df.empty or pcr_df.iloc[-1]["Time"] != now_time_str:
            if not pcr_df.empty:
                past_15m = pcr_df[pcr_df["Timestamp_dt"] <= (now_ist - datetime.timedelta(minutes=15))]
                if not past_15m.empty: delta_pcr_15m = current_pcr - past_15m.iloc[-1]["PCR"]
            new_pcr = pd.DataFrame([{"Date": today_date_str, "Timestamp_dt": now_ist, "Time": now_time_str, "PCR": current_pcr, "Delta_PCR_5m": 0.0, "Delta_PCR_15m": delta_pcr_15m}])
            st.session_state["pcr_history"] = pd.concat([pcr_df, new_pcr], ignore_index=True)
            pcr_df = st.session_state["pcr_history"]
    else:
        if not pcr_df.empty: delta_pcr_15m = pcr_df.iloc[-1]["Delta_PCR_15m"]

    # 3. Normalized Gamma Z-Score Engine
    gex_df = st.session_state["gex_history"]
    if is_market_live and not gex_df.empty and gex_df.iloc[-1]["Date"] != today_date_str:
        gex_df = pd.DataFrame(columns=REQUIRED_GEX_COLS)

    current_z_gex = 0.0
    if is_market_live or gex_df.empty:
        if gex_df.empty or gex_df.iloc[-1]["Time"] != now_time_str:
            # Calculate rolling stats on the previous records before appending the current tick
            if len(gex_df) >= 2:
                # Approximate rolling 20 periods based on ticks (for simplicity of the metric)
                recent_20 = gex_df["Total_Net_GEX"].tail(20)
                mu = recent_20.mean()
                sigma = recent_20.std()
                if sigma > 0:
                    current_z_gex = (total_net_gex - mu) / sigma
            
            new_gex = pd.DataFrame([{"Date": today_date_str, "Timestamp_dt": now_ist, "Time": now_time_str, "Total_Net_GEX": total_net_gex, "Z_GEX": current_z_gex}])
            st.session_state["gex_history"] = pd.concat([gex_df, new_gex], ignore_index=True)
            gex_df = st.session_state["gex_history"]
    else:
        if not gex_df.empty: current_z_gex = gex_df.iloc[-1]["Z_GEX"]

    # Z-GEX Interpretation
    if current_z_gex < -2.0:
        z_signal = "GAMMA COLLAPSE"
        z_color = "sub-red"
        z_desc = "Dealer stabilizing power collapsed. High directional velocity expected. BUY OPTS."
        z_card_border = "metric-card-red"
    elif -1.0 <= current_z_gex <= 1.0:
        z_signal = "NORMAL DAMPENING"
        z_color = "sub-green"
        z_desc = "Dealers actively stabilizing. Expect mean-reversion & theta decay."
        z_card_border = "metric-card-green"
    else:
        z_signal = "TRANSITION ZONE"
        z_color = "sub-amber"
        z_desc = "GEX structural shift in progress. Wait for clear regime."
        z_card_border = "metric-card-amber"

    # ---------------------------------------------------------
    # 6. DASHBOARD UI (TRADYTICS GRID LAYOUT)
    # ---------------------------------------------------------
    st.markdown(f"### NIFTY OPTIONS COMMAND CENTER")
    status_class = "status-live" if is_market_live else "status-closed"
    status_text = "🟢 LIVE MARKET" if is_market_live else "🟠 MARKET CLOSED (Recorded Data)"
    st.markdown(f'<div class="status-badge {status_class}">{status_text} | Expiry: {selected_expiry} | IST: {now_time_str}</div>', unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    # ROW 1: TOP SUMMARY BANNER (6 Columns)
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    
    with m1:
        st.markdown(f"""
            <div class="metric-card metric-card-amber">
                <div class="metric-title">NIFTY SPOT</div>
                <div class="metric-value">₹{spot_price:,.2f}</div>
                <div class="metric-sub sub-amber">ATM: {atm_strike}</div>
            </div>
        """, unsafe_allow_html=True)

    with m2:
        spread_class = "sub-green" if target_iv_spread >= 0 else "sub-red"
        border_class = "metric-card-green" if target_iv_spread >= 0 else "metric-card-red"
        st.markdown(f"""
            <div class="metric-card {border_class}">
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
                <div class="metric-title">ΔPCR 15M VELOCITY</div>
                <div class="metric-value">{delta_pcr_15m:+.2f}</div>
                <div class="metric-sub {pcr_color}">PCR: {current_pcr:.2f}</div>
            </div>
        """, unsafe_allow_html=True)

    with m4:
        dir_color = "sub-green" if total_net_delta_oi >= 0 else "sub-red"
        d_border = "metric-card-green" if total_net_delta_oi >= 0 else "metric-card-red"
        st.markdown(f"""
            <div class="metric-card {d_border}">
                <div class="metric-title">NET DELTA DEX</div>
                <div class="metric-value">₹{total_net_dex_crores:+.2f} Cr</div>
                <div class="metric-sub {dir_color}">{total_net_delta_oi:+,.0f} Cont</div>
            </div>
        """, unsafe_allow_html=True)

    with m5:
        gex_color = "sub-green" if total_net_gex >= 0 else "sub-red"
        g_border = "metric-card-green" if total_net_gex >= 0 else "metric-card-red"
        st.markdown(f"""
            <div class="metric-card {g_border}">
                <div class="metric-title">RAW NET GEX</div>
                <div class="metric-value">₹{total_net_gex:,.1f}L</div>
                <div class="metric-sub {gex_color}">Across Chain</div>
            </div>
        """, unsafe_allow_html=True)

    with m6:
        st.markdown(f"""
            <div class="metric-card {z_card_border}">
                <div class="metric-title">Z-GEX SCORE</div>
                <div class="metric-value">{current_z_gex:+.2f}</div>
                <div class="metric-sub {z_color}">{z_signal}</div>
            </div>
        """, unsafe_allow_html=True)


    # ROW 2: LIVE INTRADAY VELOCITY CHARTS (IV Spread & PCR)
    r2_col1, r2_col2 = st.columns(2)

    with r2_col1:
        st.markdown('<div class="chart-container"><div class="chart-title">Intraday IV Spread Movement (' + str(selected_target_strike) + ')</div>', unsafe_allow_html=True)
        fig_ts = go.Figure()
        strike_history = st.session_state["iv_spread_history"]
        strike_history = strike_history[strike_history["Strike"] == selected_target_strike]
        if not strike_history.empty:
            fig_ts.add_trace(go.Scatter(x=strike_history["Time"], y=strike_history["IV_Spread"], mode="lines+markers", line=dict(color="#29B6F6", width=2), marker=dict(size=3)))
        fig_ts.add_hline(y=0, line_dash="dash", line_color="white", opacity=0.3)
        fig_ts.update_xaxes(range=["09:15:00", "15:30:00"], dtick="3600000", gridcolor="#2A2E39")
        fig_ts.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=10, b=0), height=250)
        st.plotly_chart(fig_ts, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with r2_col2:
        st.markdown('<div class="chart-container"><div class="chart-title">15-Min PCR Velocity (ΔPCR)</div>', unsafe_allow_html=True)
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


    # ROW 3: EXPOSURE PROFILES (Delta vs Gamma Z-Score Tracker)
    r3_col1, r3_col2 = st.columns(2)

    with r3_col1:
        st.markdown('<div class="chart-container"><div class="chart-title">Net Delta Exposure (DEX) By Strike</div>', unsafe_allow_html=True)
        fig_dex = go.Figure()
        colors_dex = ["#00E676" if val >= 0 else "#FF5252" for val in df_filtered["Net_DEX"]]
        fig_dex.add_trace(go.Bar(x=df_filtered["Strike_Label"], y=df_filtered["Net_DEX"], marker_color=colors_dex))
        fig_dex.update_xaxes(type="category", gridcolor="#2A2E39")
        fig_dex.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=10, b=0), height=250)
        st.plotly_chart(fig_dex, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with r3_col2:
        st.markdown('<div class="chart-container"><div class="chart-title">Normalized Gamma Z-Score (ZGEX) Tracker</div>', unsafe_allow_html=True)
        fig_zgex = go.Figure()
        if not gex_df.empty:
            fig_zgex.add_trace(go.Scatter(x=gex_df["Time"], y=gex_df["Z_GEX"], mode="lines", fill='tozeroy', line=dict(color="#AB47BC", width=2)))
        # Regime thresholds
        fig_zgex.add_hline(y=1.0, line_dash="solid", line_color="#00E676", opacity=0.3)
        fig_zgex.add_hline(y=-1.0, line_dash="solid", line_color="#00E676", opacity=0.3)
        fig_zgex.add_hline(y=-2.0, line_dash="dash", line_color="#FF5252", annotation_text="Collapse")
        fig_zgex.update_xaxes(range=["09:15:00", "15:30:00"], dtick="3600000", gridcolor="#2A2E39")
        fig_zgex.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=10, b=0), height=250)
        st.plotly_chart(fig_zgex, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)


    # ROW 4: DATA GRID
    st.markdown('<div class="chart-container"><div class="chart-title">Institutional Options Chain Grid</div>', unsafe_allow_html=True)
    grid_df = df_filtered[["Strike", "CE_LTP", "PE_LTP", "CE_OI", "PE_OI", "CE_Delta", "PE_Delta", "Net_Delta_OI", "Net_DEX", "Net_GEX", "Net_VEX", "Net_CHEX", "CE_IV", "PE_IV", "IV_Spread"]].copy()
    st.dataframe(
        grid_df.style.format({
            "Strike": "{:.0f}", "CE_LTP": "₹{:.2f}", "PE_LTP": "₹{:.2f}", "CE_OI": "{:,.0f}", "PE_OI": "{:,.0f}", 
            "CE_Delta": "{:.2f}", "PE_Delta": "{:.2f}", "Net_Delta_OI": "{:+,.0f}", "Net_DEX": "{:+,.1f}L", 
            "Net_GEX": "{:+,.1f}L", "Net_VEX": "{:+,.2f}", "Net_CHEX": "{:+,.2f}", "CE_IV": "{:.1f}%", 
            "PE_IV": "{:.1f}%", "IV_Spread": "{:+.2f}%"
        }),
        use_container_width=True, height=350
    )
    st.markdown('</div>', unsafe_allow_html=True)
