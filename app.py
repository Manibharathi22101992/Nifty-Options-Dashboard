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
# 1. PAGE SETUP & TERMINAL STYLING
# ---------------------------------------------------------
st.set_page_config(
    page_title="Nifty Quant & Vol Desk | Dhan API",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .stApp { background-color: #0b0e14; color: #e0e6ed; }
    section[data-testid="stSidebar"] { background-color: #121721 !important; border-right: 1px solid #1e2638; }
    
    .metric-card {
        background: #161c28;
        border: 1px solid #232d42;
        border-radius: 8px;
        padding: 12px 16px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
        margin-bottom: 8px;
    }
    .metric-title { color: #8b9bb4; font-size: 0.75rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }
    .metric-value { color: #ffffff; font-size: 1.35rem; font-weight: 700; margin-top: 2px; }
    .metric-sub { font-size: 0.8rem; font-weight: 600; margin-top: 2px; }
    
    .sub-green { color: #00E676; }
    .sub-red { color: #FF5252; }
    .sub-amber { color: #FFD700; }
    .sub-blue { color: #29B6F6; }

    .summary-box {
        background: #121824;
        border: 1px solid #232d42;
        border-radius: 8px;
        padding: 16px 20px;
        margin-bottom: 20px;
    }
    .summary-title {
        font-size: 1.1rem;
        font-weight: 700;
        color: #ffffff;
        margin-bottom: 8px;
    }

    .status-live {
        background-color: rgba(0, 230, 118, 0.15);
        border: 1px solid #00E676;
        color: #00E676;
        padding: 6px 12px;
        border-radius: 6px;
        font-weight: 700;
        display: inline-block;
        font-size: 0.85rem;
    }
    .status-closed {
        background-color: rgba(255, 167, 38, 0.15);
        border: 1px solid #FFA726;
        color: #FFA726;
        padding: 6px 12px;
        border-radius: 6px;
        font-weight: 700;
        display: inline-block;
        font-size: 0.85rem;
    }

    .regime-badge-pos {
        background-color: rgba(0, 230, 118, 0.15);
        border: 1px solid #00E676;
        color: #00E676;
        padding: 6px 12px;
        border-radius: 6px;
        font-weight: 700;
        text-align: center;
        font-size: 0.9rem;
    }
    .regime-badge-neg {
        background-color: rgba(255, 82, 82, 0.15);
        border: 1px solid #FF5252;
        color: #FF5252;
        padding: 6px 12px;
        border-radius: 6px;
        font-weight: 700;
        text-align: center;
        font-size: 0.9rem;
    }

    .stTabs [data-baseweb="tab-list"] { gap: 8px; background-color: #121721; padding: 6px; border-radius: 8px; border: 1px solid #1e2638; }
    .stTabs [data-baseweb="tab"] { height: 40px; background-color: transparent; border-radius: 6px; color: #8b9bb4; font-weight: 600; }
    .stTabs [aria-selected="true"] { background-color: #232d42 !important; color: #ffffff !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("⚡ NIFTY 50 Quantitative & Volatility Desk")

# Clean API Credentials
CLIENT_ID = (
    str(st.secrets.get("DHAN_CLIENT_ID", ""))
    .strip()
    .replace('"', "")
    .replace("'", "")
)
ACCESS_TOKEN = (
    str(st.secrets.get("DHAN_ACCESS_TOKEN", ""))
    .strip()
    .replace('"', "")
    .replace("'", "")
)

if not CLIENT_ID or not ACCESS_TOKEN:
    st.error(
        "⚠️ API credentials missing. Please update your Streamlit Secrets."
    )
    st.stop()

NIFTY_LOT_SIZE = 25


# ---------------------------------------------------------
# 2. BLACK-SCHOLES GREEK ENGINE
# ---------------------------------------------------------
def calculate_bs_greeks(S, K, T, sigma, r=0.07):
    if T <= 1e-5 or sigma <= 1e-4 or S <= 0 or K <= 0:
        return 0.0, 0.0, 0.0

    try:
        d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (
            sigma * math.sqrt(T)
        )
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
    payload = {
        "UnderlyingScrip": 13,
        "UnderlyingSeg": "IDX_I",
        "Expiry": expiry_date,
    }

    try:
        res = requests.post(url, headers=headers, json=payload, timeout=10)
        data = res.json()

        if res.status_code == 200 and data.get("status") == "success":
            raw_data = data.get("data", {})
            spot_price = float(raw_data.get("last_price", 0.0))
            oc_raw = raw_data.get("oc", {})

            if not oc_raw:
                return (
                    None,
                    spot_price,
                    f"No contracts returned for expiry {expiry_date}.",
                )

            exp_date_obj = datetime.datetime.strptime(
                expiry_date, "%Y-%m-%d"
            ).date()
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
                    ce_gamma, ce_vanna, ce_charm = calculate_bs_greeks(
                        spot_price, strike, T_years, ce_iv
                    )
                else:
                    _, ce_vanna, ce_charm = calculate_bs_greeks(
                        spot_price, strike, T_years, max(ce_iv, 0.15)
                    )

                if pe_gamma <= 0 and pe_iv > 0:
                    pe_gamma, pe_vanna, pe_charm = calculate_bs_greeks(
                        spot_price, strike, T_years, pe_iv
                    )
                else:
                    _, pe_vanna, pe_charm = calculate_bs_greeks(
                        spot_price, strike, T_years, max(pe_iv, 0.15)
                    )

                call_gex = (
                    ce_oi
                    * ce_gamma
                    * (spot_price**2)
                    * 0.01
                    * NIFTY_LOT_SIZE
                    / 1e5
                )
                put_gex = (
                    -pe_oi
                    * pe_gamma
                    * (spot_price**2)
                    * 0.01
                    * NIFTY_LOT_SIZE
                    / 1e5
                )
                net_gex = call_gex + put_gex

                ce_delta_oi = ce_oi * ce_delta
                pe_delta_oi = pe_oi * pe_delta
                net_delta_oi = ce_delta_oi + pe_delta_oi
                net_dex = net_delta_oi * spot_price * NIFTY_LOT_SIZE / 1e5

                net_vex = (
                    (ce_oi * ce_vanna) - (pe_oi * pe_vanna)
                ) * NIFTY_LOT_SIZE / 1e3
                net_chex = (
                    (ce_oi * ce_charm) - (pe_oi * pe_charm)
                ) * NIFTY_LOT_SIZE / 1e3

                records.append(
                    {
                        "Strike": strike,
                        "CE_LTP": ce_ltp,
                        "PE_LTP": pe_ltp,
                        "CE_OI": ce_oi,
                        "PE_OI": pe_oi,
                        "Total_OI": ce_oi + pe_oi,
                        "CE_Delta": ce_delta,
                        "PE_Delta": pe_delta,
                        "Net_Delta_OI": net_delta_oi,
                        "Net_DEX": net_dex,
                        "Call_GEX": call_gex,
                        "Put_GEX": put_gex,
                        "Net_GEX": net_gex,
                        "Net_VEX": net_vex,
                        "Net_CHEX": net_chex,
                        "CE_IV": ce_iv * 100.0,
                        "PE_IV": pe_iv * 100.0,
                        "IV_Spread": (ce_iv * 100.0) - (pe_iv * 100.0),
                    }
                )

            df = (
                pd.DataFrame(records)
                .sort_values("Strike")
                .reset_index(drop=True)
            )
            return df, spot_price, None
        else:
            remark = (
                data.get("remarks")
                or data.get("message")
                or f"HTTP {res.status_code}"
            )
            return None, 0.0, str(remark)

    except Exception as e:
        return None, 0.0, f"Connection Error: {str(e)}"


# ---------------------------------------------------------
# 4. DYNAMIC EXPIRY LIST & MULTI-EXPIRY TERM STRUCTURE
# ---------------------------------------------------------
@st.cache_data(ttl=300)
def fetch_expiry_list_direct():
    """Fetches exact listed expiry dates for Nifty directly from Dhan API."""
    url = "https://api.dhan.co/v2/optionchain/expirylist"
    headers = {
        "client-id": CLIENT_ID,
        "access-token": ACCESS_TOKEN,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = {"UnderlyingScrip": 13, "UnderlyingSeg": "IDX_I"}

    try:
        res = requests.post(url, headers=headers, json=payload, timeout=5)
        data = res.json()
        if res.status_code == 200 and data.get("status") == "success":
            return data.get("data", [])
    except Exception:
        pass
    return []


@st.cache_data(ttl=120)
def fetch_multi_expiry_vol_structure(spot_price):
    """Fetches ATM IV across upcoming valid expiries to build Vol Term Structure & Forward Vol."""
    expiries = fetch_expiry_list_direct()

    # Fallback to calculated Thursdays if expiry list endpoint is unavailable
    if not expiries:
        today = datetime.date.today()
        expiries = []
        for i in range(1, 45):
            d = today + datetime.timedelta(days=i)
            if d.weekday() == 3:  # Thursday
                expiries.append(d.strftime("%Y-%m-%d"))
            if len(expiries) >= 4:
                break
    else:
        expiries = expiries[:4]  # Take nearest 4 valid expiries to prevent rate limit limits

    atm_strike = int(round(spot_price / 50) * 50)
    vol_data = []

    for idx, exp in enumerate(expiries):
        if idx > 0:
            time.sleep(1.1)  # Rate limit protection for Dhan API (1 req / 3s)

        df_exp, _, err = fetch_gex_option_chain(exp)
        if df_exp is not None and not df_exp.empty:
            atm_row = df_exp[df_exp["Strike"] == atm_strike]
            if not atm_row.empty:
                ce_iv = atm_row["CE_IV"].values[0]
                pe_iv = atm_row["PE_IV"].values[0]
            else:
                ce_iv = df_exp["CE_IV"].mean()
                pe_iv = df_exp["PE_IV"].mean()

            mean_iv = (ce_iv + pe_iv) / 2.0
            exp_date_obj = datetime.datetime.strptime(exp, "%Y-%m-%d").date()
            days_to_exp = max((exp_date_obj - datetime.date.today()).days, 1)

            vol_data.append(
                {
                    "Expiry": exp_date_obj.strftime("%d %b"),
                    "Full_Expiry": exp,
                    "Days": days_to_exp,
                    "Tenor_Years": days_to_exp / 365.0,
                    "CE_IV": ce_iv,
                    "PE_IV": pe_iv,
                    "Mean_IV": mean_iv,
                }
            )

    df_vol = pd.DataFrame(vol_data)
    if df_vol.empty or len(df_vol) < 2:
        return pd.DataFrame()

    # Calculate Forward Volatility
    fwd_vols = []
    for i in range(len(df_vol)):
        if i == 0:
            fwd_vols.append(df_vol.loc[i, "Mean_IV"])
        else:
            t1 = df_vol.loc[i - 1, "Tenor_Years"]
            t2 = df_vol.loc[i, "Tenor_Years"]
            v1 = df_vol.loc[i - 1, "Mean_IV"] / 100.0
            v2 = df_vol.loc[i, "Mean_IV"] / 100.0

            var_diff = (v2**2 * t2) - (v1**2 * t1)
            dt = t2 - t1

            if var_diff > 0 and dt > 0:
                fwd_v = math.sqrt(var_diff / dt) * 100.0
            else:
                fwd_v = v2 * 100.0

            fwd_vols.append(fwd_v)

    df_vol["Forward_Vol"] = fwd_vols
    return df_vol


# ---------------------------------------------------------
# 5. CONTROLS & SAFE SESSION MEMORY INITIALIZATION
# ---------------------------------------------------------
st.sidebar.header("⚙️ Controls & Feeds")

auto_refresh = st.sidebar.checkbox("Enable Live Auto-Refresh (5s)", value=True)
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

# Dynamic Expiry Date Selection
valid_expiries = fetch_expiry_list_direct()
if valid_expiries:
    selected_expiry = st.sidebar.selectbox("Primary Expiry Date", valid_expiries)
else:
    days_until_thursday = (3 - now_ist.weekday()) % 7
    default_expiry = (now_ist + datetime.timedelta(days=days_until_thursday)).strftime("%Y-%m-%d")
    selected_expiry = st.sidebar.date_input(
        "Primary Expiry Date", datetime.datetime.strptime(default_expiry, "%Y-%m-%d")
    ).strftime("%Y-%m-%d")

df_oc, spot_price, error_remark = fetch_gex_option_chain(selected_expiry)

selected_target_strike = None
if df_oc is not None and not df_oc.empty:
    atm_strike_val = int(round(spot_price / 50) * 50)
    all_strikes = df_oc["Strike"].tolist()

    default_index = (
        all_strikes.index(atm_strike_val) if atm_strike_val in all_strikes else 0
    )
    selected_target_strike = st.sidebar.selectbox(
        "🎯 Target Strike (Intraday IV Spread)",
        all_strikes,
        index=default_index,
    )

REQUIRED_HIST_COLS = [
    "Date",
    "Time",
    "ATM_Strike",
    "Target_Strike",
    "ATM_CE_IV",
    "ATM_PE_IV",
    "ATM_IV_Spread",
    "Target_IV_Spread",
    "Spot",
]

if "iv_spread_history" not in st.session_state or not set(
    REQUIRED_HIST_COLS
).issubset(st.session_state["iv_spread_history"].columns):
    st.session_state["iv_spread_history"] = pd.DataFrame(
        columns=REQUIRED_HIST_COLS
    )

if st.sidebar.button("🗑️ Clear Intraday History"):
    st.session_state["iv_spread_history"] = pd.DataFrame(
        columns=REQUIRED_HIST_COLS
    )
    st.cache_data.clear()
    st.rerun()


# ---------------------------------------------------------
# 6. DASHBOARD RENDER & TOOLS
# ---------------------------------------------------------
if error_remark:
    st.error(f"⚠️ **Dhan Server Error:** {error_remark}")
elif df_oc is not None and not df_oc.empty:
    atm_strike = int(round(spot_price / 50) * 50)

    call_wall_strike = int(df_oc.loc[df_oc["Call_GEX"].idxmax()]["Strike"])
    put_wall_strike = int(df_oc.loc[df_oc["Put_GEX"].idxmin()]["Strike"])

    df_sorted = df_oc.sort_values("Strike").copy()
    gamma_flip_strike = int(spot_price)
    for i in range(1, len(df_sorted)):
        prev_val = df_sorted.iloc[i - 1]["Net_GEX"]
        curr_val = df_sorted.iloc[i]["Net_GEX"]
        if (prev_val < 0 and curr_val >= 0) or (
            prev_val > 0 and curr_val <= 0
        ):
            s1, s2 = (
                df_sorted.iloc[i - 1]["Strike"],
                df_sorted.iloc[i]["Strike"],
            )
            gamma_flip_strike = int((s1 + s2) / 2.0)
            break

    # ATM Strike IV Details
    atm_row = df_oc[df_oc["Strike"] == atm_strike]
    if not atm_row.empty:
        atm_ce_iv = atm_row["CE_IV"].values[0]
        atm_pe_iv = atm_row["PE_IV"].values[0]
        atm_iv_spread = atm_ce_iv - atm_pe_iv
    else:
        atm_ce_iv, atm_pe_iv, atm_iv_spread = 0.0, 0.0, 0.0

    # Selected Target Strike Details
    target_row = df_oc[df_oc["Strike"] == selected_target_strike]
    if not target_row.empty:
        target_ce_iv = target_row["CE_IV"].values[0]
        target_pe_iv = target_row["PE_IV"].values[0]
        target_iv_spread = target_ce_iv - target_pe_iv
    else:
        target_ce_iv, target_pe_iv, target_iv_spread = 0.0, 0.0, 0.0

    # Intraday Accumulation Logic
    hist_df = st.session_state["iv_spread_history"]
    if is_market_live and not hist_df.empty:
        last_rec_date = hist_df.iloc[-1].get("Date", "")
        if last_rec_date != today_date_str:
            st.session_state["iv_spread_history"] = pd.DataFrame(
                columns=REQUIRED_HIST_COLS
            )
            hist_df = st.session_state["iv_spread_history"]

    if is_market_live or hist_df.empty:
        if hist_df.empty or hist_df.iloc[-1]["Time"] != now_time_str:
            new_row = pd.DataFrame(
                [
                    {
                        "Date": today_date_str,
                        "Time": now_time_str,
                        "ATM_Strike": atm_strike,
                        "Target_Strike": selected_target_strike,
                        "ATM_CE_IV": atm_ce_iv,
                        "ATM_PE_IV": atm_pe_iv,
                        "ATM_IV_Spread": atm_iv_spread,
                        "Target_IV_Spread": target_iv_spread,
                        "Spot": spot_price,
                    }
                ]
            )
            st.session_state["iv_spread_history"] = pd.concat(
                [hist_df, new_row], ignore_index=True
            )

    # Market Direction Logic
    total_net_delta_oi = df_oc["Net_Delta_OI"].sum()
    total_net_dex_lakhs = df_oc["Net_DEX"].sum()
    total_net_dex_crores = total_net_dex_lakhs / 100.0

    if total_net_delta_oi > 50000:
        dir_signal, dir_color = "STRONGLY BULLISH", "sub-green"
        dir_desc = "Heavy Call Delta & Put Writing domination. Market Makers are net short delta, forcing them to buy Nifty futures on upward moves."
    elif total_net_delta_oi > 10000:
        dir_signal, dir_color = "MILDLY BULLISH", "sub-green"
        dir_desc = "Moderate positive delta skew. Market shows upward bias with decent support."
    elif total_net_delta_oi < -50000:
        dir_signal, dir_color = "STRONGLY BEARISH", "sub-red"
        dir_desc = "Heavy Put Delta & Call Writing domination. Market Makers are forced to sell Nifty futures on downward moves."
    elif total_net_delta_oi < -10000:
        dir_signal, dir_color = "MILDLY BEARISH", "sub-red"
        dir_desc = "Moderate negative delta skew. Downward pressure favored."
    else:
        dir_signal, dir_color = "NEUTRAL / RANGEBOUND", "sub-amber"
        dir_desc = "Net Delta exposure is balanced near zero. Expect consolidation or rangebound trading."

    total_net_gex = df_oc["Net_GEX"].sum()
    is_pos_gamma = spot_price >= gamma_flip_strike or total_net_gex > 0
    regime_text = (
        "POSITIVE GAMMA (PINNING / LOW VOL)"
        if is_pos_gamma
        else "NEGATIVE GAMMA (AMPLIFICATION / HIGH VOL)"
    )

    # TOP METRICS CARDS
    c1, c2, c3, c4, c5 = st.columns(5)

    with c1:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-title">NIFTY SPOT</div>
                <div class="metric-value">₹{spot_price:,.2f}</div>
                <div class="metric-sub sub-amber">ATM: {atm_strike}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with c2:
        atm_spread_class = "sub-green" if atm_iv_spread >= 0 else "sub-red"
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-title">ATM ({atm_strike}) IV SPREAD</div>
                <div class="metric-value">{atm_iv_spread:+.2f}%</div>
                <div class="metric-sub {atm_spread_class}">CE: {atm_ce_iv:.1f}% | PE: {atm_pe_iv:.1f}%</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with c3:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-title">MARKET DIRECTION BIAS</div>
                <div class="metric-value">{dir_signal.split()[0]}</div>
                <div class="metric-sub {dir_color}">{dir_signal}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with c4:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-title">NET DEX (RUPEE CASH)</div>
                <div class="metric-value">₹{total_net_dex_crores:+.2f} Cr</div>
                <div class="metric-sub sub-blue">Contracts: {total_net_delta_oi:+,.0f}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with c5:
        net_gex_class = "sub-green" if total_net_gex >= 0 else "sub-red"
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-title">TOTAL NET GEX</div>
                <div class="metric-value">₹{total_net_gex:,.1f}L</div>
                <div class="metric-sub {net_gex_class}">Flip: ₹{gamma_flip_strike:,}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    badge_style = "regime-badge-pos" if is_pos_gamma else "regime-badge-neg"
    st.markdown(
        f'<div class="{badge_style}">DEALER REGIME: {regime_text}</div><br>',
        unsafe_allow_html=True,
    )

    df_filtered = df_oc[
        (df_oc["Strike"] >= atm_strike - 500)
        & (df_oc["Strike"] <= atm_strike + 500)
    ].copy()

    df_filtered["Strike_Label"] = df_filtered["Strike"].astype(str)

    # ---------------------------------------------------------
    # TABBED ANALYTICS DASHBOARD
    # ---------------------------------------------------------
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
        [
            "🎯 Net Delta OI & DEX",
            "⚡ Intraday ATM IV Spread",
            "📈 Term Structure & Forward Vol",
            "📊 Net GEX Profile",
            "🌀 Higher-Order Exposures",
            "📋 Data Grid",
        ]
    )

    # TAB 1: Direction Summary
    with tab1:
        st.markdown(
            f"""
            <div class="summary-box">
                <div class="summary-title">🧭 Market Direction Summary (DEX & Delta-Weighted OI)</div>
                <table style="width:100%; border-collapse: collapse; font-size: 0.95rem;">
                    <tr style="border-bottom: 1px solid #232d42;">
                        <td style="padding: 6px; color:#8b9bb4;"><b>Directional Signal:</b></td>
                        <td style="padding: 6px;"><b class="{dir_color}">{dir_signal}</b></td>
                        <td style="padding: 6px; color:#8b9bb4;"><b>Net Delta OI:</b></td>
                        <td style="padding: 6px; color:#ffffff;"><b>{total_net_delta_oi:+,.0f} Contracts</b></td>
                    </tr>
                    <tr>
                        <td style="padding: 6px; color:#8b9bb4;"><b>Net DEX (Rupee Value):</b></td>
                        <td style="padding: 6px; color:#ffffff;"><b>₹{total_net_dex_crores:+.2f} Crores</b></td>
                        <td style="padding: 6px; color:#8b9bb4;"><b>Primary Driver:</b></td>
                        <td style="padding: 6px; color:#ffffff;">{"Call Dominance" if total_net_delta_oi >= 0 else "Put Dominance"}</td>
                    </tr>
                </table>
                <div style="margin-top: 10px; font-size: 0.85rem; color: #b0bec5; background: #161c28; padding: 10px; border-radius: 6px;">
                    💡 <b>Institutional Context:</b> {dir_desc}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        d_col1, d_col2 = st.columns(2)
        with d_col1:
            st.subheader("Net Delta-Weighted Open Interest")
            fig_delta_oi = go.Figure()
            colors_delta = [
                "#26A69A" if val >= 0 else "#EF5350"
                for val in df_filtered["Net_Delta_OI"]
            ]
            fig_delta_oi.add_trace(
                go.Bar(
                    x=df_filtered["Strike_Label"],
                    y=df_filtered["Net_Delta_OI"],
                    marker_color=colors_delta,
                )
            )
            fig_delta_oi.update_xaxes(type="category", title="Strike Price")
            fig_delta_oi.update_layout(
                template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                yaxis_title="Delta Contracts",
            )
            st.plotly_chart(fig_delta_oi, use_container_width=True)

        with d_col2:
            st.subheader("Delta Exposure - DEX (₹ Lakhs)")
            fig_dex = go.Figure()
            colors_dex = [
                "#26A69A" if val >= 0 else "#EF5350"
                for val in df_filtered["Net_DEX"]
            ]
            fig_dex.add_trace(
                go.Bar(
                    x=df_filtered["Strike_Label"],
                    y=df_filtered["Net_DEX"],
                    marker_color=colors_dex,
                )
            )
            fig_dex.update_xaxes(type="category", title="Strike Price")
            fig_dex.update_layout(
                template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                yaxis_title="Net DEX (₹ Lakhs)",
            )
            st.plotly_chart(fig_dex, use_container_width=True)

    # TAB 2: Intraday ATM IV Spread Engine
    with tab2:
        st.subheader(
            f"📈 Live Intraday ATM ({atm_strike}) & Target ({selected_target_strike}) IV Spread Tracker"
        )

        status_html = (
            '<span class="status-live">🟢 LIVE MARKET SESSION (09:15 - 15:30 IST)</span>'
            if is_market_live
            else '<span class="status-closed">🟠 MARKET CLOSED (Showing Recorded Session Data)</span>'
        )
        st.markdown(status_html, unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

        col_iv1, col_iv2, col_iv3, col_iv4 = st.columns(4)
        col_iv1.metric("ATM Strike", f"{atm_strike}")
        col_iv2.metric("ATM Call IV", f"{atm_ce_iv:.2f}%")
        col_iv3.metric("ATM Put IV", f"{atm_pe_iv:.2f}%")
        col_iv4.metric(
            "ATM IV Spread (CE - PE)",
            f"{atm_iv_spread:+.2f}%",
            "Call Premium" if atm_iv_spread >= 0 else "Put Premium",
        )

        st.markdown("---")

        history_df = st.session_state["iv_spread_history"]

        if not history_df.empty:
            recorded_date = history_df.iloc[-1].get("Date", today_date_str)

            fig_ts = go.Figure()

            # ATM IV Spread Line
            fig_ts.add_trace(
                go.Scatter(
                    x=history_df["Time"],
                    y=history_df["ATM_IV_Spread"],
                    mode="lines+markers",
                    name=f"ATM ({atm_strike}) IV Spread",
                    line=dict(color="#29B6F6", width=2.5),
                )
            )

            # Target Strike IV Spread Line (if different from ATM)
            if selected_target_strike != atm_strike:
                fig_ts.add_trace(
                    go.Scatter(
                        x=history_df["Time"],
                        y=history_df["Target_IV_Spread"],
                        mode="lines+markers",
                        name=f"Target ({selected_target_strike}) IV Spread",
                        line=dict(color="#FFA726", width=2, dash="dot"),
                    )
                )

            fig_ts.add_hline(
                y=0, line_dash="dash", line_color="white", opacity=0.4
            )
            fig_ts.update_layout(
                template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                title=f"Intraday Volatility Spread Curve (Session: {recorded_date})",
                xaxis_title="Market Time (IST)",
                yaxis_title="IV Spread Points (%)",
                legend=dict(orientation="h", y=1.1),
            )
            st.plotly_chart(fig_ts, use_container_width=True)
        else:
            st.info(
                "⏳ **Accumulating Session Ticks:** The live intraday graph updates automatically over the market session."
            )

    # TAB 3: Term Structure & Forward Vol
    with tab3:
        st.subheader("Forward Volatility Term Structure & Vol Curve")

        df_vol_struct = fetch_multi_expiry_vol_structure(spot_price)

        if not df_vol_struct.empty and len(df_vol_struct) >= 2:
            v_left, v_right = st.columns(2)

            with v_left:
                st.markdown("#### FORWARD VOL TERM STRUCTURE")
                fig_fwd = go.Figure()
                fig_fwd.add_trace(
                    go.Scatter(
                        x=df_vol_struct["Expiry"],
                        y=df_vol_struct["Forward_Vol"],
                        mode="lines+markers",
                        name="Forward Vol (%)",
                        line=dict(color="#00E676", width=2.5),
                        marker=dict(size=8, color="#00E676"),
                    )
                )
                fig_fwd.update_layout(
                    template="plotly_dark",
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    xaxis_title="End Tenor Expiry",
                    yaxis_title="Forward Vol (%)",
                )
                st.plotly_chart(fig_fwd, use_container_width=True)

            with v_right:
                st.markdown("#### CUMULATIVE VOL CURVE")
                fig_vol_curve = go.Figure()
                fig_vol_curve.add_trace(
                    go.Scatter(
                        x=df_vol_struct["Expiry"],
                        y=df_vol_struct["Mean_IV"],
                        mode="lines+markers",
                        name="Cumulative Vol (%)",
                        line=dict(color="#AB47BC", width=2.5),
                        marker=dict(size=8, color="#AB47BC"),
                    )
                )
                fig_vol_curve.update_layout(
                    template="plotly_dark",
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    xaxis_title="Expiry Date",
                    yaxis_title="Cumulative Vol (%)",
                )
                st.plotly_chart(fig_vol_curve, use_container_width=True)
        else:
            st.warning(
                "⚠️ **Term Structure Data Building:** Additional expiries are loading or market feeds are paused outside trading hours."
            )

    # TAB 4: Net GEX
    with tab4:
        st.subheader("Net Gamma Exposure (GEX) Profile")
        fig_gex = go.Figure()
        colors_gex = [
            "#26A69A" if g >= 0 else "#EF5350" for g in df_filtered["Net_GEX"]
        ]
        fig_gex.add_trace(
            go.Bar(
                x=df_filtered["Strike_Label"],
                y=df_filtered["Net_GEX"],
                marker_color=colors_gex,
            )
        )
        fig_gex.update_xaxes(type="category", title="Strike Price")
        fig_gex.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            yaxis_title="Net GEX (₹ Lakhs / 1% Move)",
        )
        st.plotly_chart(fig_gex, use_container_width=True)

    # TAB 5: Higher-Order Exposures
    with tab5:
        st.subheader("Higher-Order Greek Exposures (Vanna & Charm)")
        v_col1, v_col2 = st.columns(2)

        with v_col1:
            st.markdown("**Vanna Exposure (VEX - IV Sensitivity)**")
            fig_vex = px.line(
                df_filtered,
                x="Strike_Label",
                y="Net_VEX",
                markers=True,
                template="plotly_dark",
            )
            fig_vex.update_traces(line_color="#FFA726", line_width=2)
            fig_vex.update_xaxes(type="category", title="Strike Price")
            fig_vex.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                yaxis_title="Net VEX",
            )
            st.plotly_chart(fig_vex, use_container_width=True)

        with v_col2:
            st.markdown("**Charm Exposure (CHEX - Time Decay Flow)**")
            fig_chex = px.line(
                df_filtered,
                x="Strike_Label",
                y="Net_CHEX",
                markers=True,
                template="plotly_dark",
            )
            fig_chex.update_traces(line_color="#AB47BC", line_width=2)
            fig_chex.update_xaxes(type="category", title="Strike Price")
            fig_chex.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                yaxis_title="Net CHEX",
            )
            st.plotly_chart(fig_chex, use_container_width=True)

    # TAB 6: Data Grid
    with tab6:
        st.subheader("Institutional Options Chain Data Grid")
        grid_df = df_filtered[
            [
                "Strike",
                "CE_LTP",
                "PE_LTP",
                "CE_OI",
                "PE_OI",
                "CE_Delta",
                "PE_Delta",
                "Net_Delta_OI",
                "Net_DEX",
                "Net_GEX",
                "Net_VEX",
                "Net_CHEX",
                "CE_IV",
                "PE_IV",
                "IV_Spread",
            ]
        ].copy()

        st.dataframe(
            grid_df.style.format(
                {
                    "Strike": "{:.0f}",
                    "CE_LTP": "₹{:.2f}",
                    "PE_LTP": "₹{:.2f}",
                    "CE_OI": "{:,.0f}",
                    "PE_OI": "{:,.0f}",
                    "CE_Delta": "{:.2f}",
                    "PE_Delta": "{:.2f}",
                    "Net_Delta_OI": "{:+,.0f}",
                    "Net_DEX": "{:+,.1f}L",
                    "Net_GEX": "{:+,.1f}L",
                    "Net_VEX": "{:+,.2f}",
                    "Net_CHEX": "{:+,.2f}",
                    "CE_IV": "{:.1f}%",
                    "PE_IV": "{:.1f}%",
                    "IV_Spread": "{:+.2f}%",
                }
            ),
            use_container_width=True,
            height=450,
        )
