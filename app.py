import datetime
import math
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st
from streamlit_autorefresh import st_autorefresh

# ---------------------------------------------------------
# 1. PAGE SETUP & INSTITUTIONAL STYLING
# ---------------------------------------------------------
st.set_page_config(
    page_title="Nifty Quant & GEX Desk | Dhan API",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .stApp { background-color: #0b0e14; color: #e0e6ed; }
    section[data-testid="stSidebar"] { background-color: #121721 !important; border-right: 1px solid #1e2638; }
    
    /* Glassmorphism Metric Cards */
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

    /* Regime Badges */
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

st.title("⚡ NIFTY 50 Quantitative & GEX Desk")

# API Credentials
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

NIFTY_LOT_SIZE = 25  # Standard Nifty contract lot size


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
                strike = int(float(strike_str))  # Ensure strict integer strike
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

                # GEX Calculations (₹ Lakhs)
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

                # Delta-Weighted OI Calculations
                # Note: PE Delta is negative from options API
                ce_delta_oi = ce_oi * ce_delta
                pe_delta_oi = pe_oi * pe_delta
                net_delta_oi = ce_delta_oi + pe_delta_oi

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
                        "CE_Delta_OI": ce_delta_oi,
                        "PE_Delta_OI": pe_delta_oi,
                        "Net_Delta_OI": net_delta_oi,
                        "Call_GEX": call_gex,
                        "Put_GEX": put_gex,
                        "Net_GEX": net_gex,
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
# 4. CONTROLS & AUTO-REFRESH
# ---------------------------------------------------------
st.sidebar.header("⚙️ Controls & Feeds")

auto_refresh = st.sidebar.checkbox("Enable Live Auto-Refresh (5s)", value=True)
if auto_refresh:
    st_autorefresh(interval=5000, key="datarefresh")

today = datetime.date.today()
days_until_thursday = (3 - today.weekday()) % 7
default_expiry = today + datetime.timedelta(days=days_until_thursday)

selected_expiry = st.sidebar.date_input(
    "Expiry Date", default_expiry
).strftime("%Y-%m-%d")

# Fetch GEX Data first to populate strike list in sidebar
df_oc, spot_price, error_remark = fetch_gex_option_chain(selected_expiry)

# Target Strike Selector for ATM / Selected IV Spread Tool
selected_target_strike = None
if df_oc is not None and not df_oc.empty:
    atm_strike_val = int(round(spot_price / 50) * 50)
    all_strikes = df_oc["Strike"].tolist()

    default_index = (
        all_strikes.index(atm_strike_val) if atm_strike_val in all_strikes else 0
    )
    selected_target_strike = st.sidebar.selectbox(
        "Target Strike (IV Spread)", all_strikes, index=default_index
    )

if st.sidebar.button("🔄 Manual Refresh"):
    st.cache_data.clear()


# ---------------------------------------------------------
# 5. DASHBOARD RENDER & TOOLS
# ---------------------------------------------------------
if error_remark:
    st.error(f"⚠️ **Dhan Server Error:** {error_remark}")
elif df_oc is not None and not df_oc.empty:
    atm_strike = int(round(spot_price / 50) * 50)

    # 1. Key Levels Identification
    call_wall_strike = int(df_oc.loc[df_oc["Call_GEX"].idxmax()]["Strike"])
    put_wall_strike = int(df_oc.loc[df_oc["Put_GEX"].idxmin()]["Strike"])

    # 2. Gamma Flip Calculation
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

    # 3. Selected Target / ATM IV Spread Tool Metrics
    target_row = df_oc[df_oc["Strike"] == selected_target_strike]
    if not target_row.empty:
        target_ce_iv = target_row["CE_IV"].values[0]
        target_pe_iv = target_row["PE_IV"].values[0]
        target_iv_spread = target_ce_iv - target_pe_iv
    else:
        target_ce_iv, target_pe_iv, target_iv_spread = 0.0, 0.0, 0.0

    # 4. Total Net Delta-Weighted Open Interest
    total_net_delta_oi = df_oc["Net_Delta_OI"].sum()

    total_net_gex = df_oc["Net_GEX"].sum()
    is_pos_gamma = spot_price >= gamma_flip_strike or total_net_gex > 0
    regime_text = (
        "POSITIVE GAMMA (PINNING / LOW VOL)"
        if is_pos_gamma
        else "NEGATIVE GAMMA (AMPLIFICATION / HIGH VOL)"
    )

    # TOP METRICS BANNER
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
        spread_class = "sub-green" if target_iv_spread >= 0 else "sub-red"
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-title">{selected_target_strike} IV SPREAD</div>
                <div class="metric-value">{target_iv_spread:+.2f}%</div>
                <div class="metric-sub {spread_class}">CE: {target_ce_iv:.1f}% | PE: {target_pe_iv:.1f}%</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with c3:
        delta_oi_class = "sub-green" if total_net_delta_oi >= 0 else "sub-red"
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-title">NET DELTA-WEIGHTED OI</div>
                <div class="metric-value">{total_net_delta_oi:+,.0f}</div>
                <div class="metric-sub {delta_oi_class}">{"BULLISH BIAS" if total_net_delta_oi >= 0 else "BEARISH BIAS"}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with c4:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-title">GAMMA FLIP LEVEL</div>
                <div class="metric-value">₹{gamma_flip_strike:,}</div>
                <div class="metric-sub sub-blue">CW: {call_wall_strike} | PW: {put_wall_strike}</div>
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
                <div class="metric-sub {net_gex_class}">Across Chain</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    badge_style = "regime-badge-pos" if is_pos_gamma else "regime-badge-neg"
    st.markdown(
        f'<div class="{badge_style}">DEALER REGIME: {regime_text}</div><br>',
        unsafe_allow_html=True,
    )

    # Filter Strikes Near ATM (+/- 500 Points)
    df_filtered = df_oc[
        (df_oc["Strike"] >= atm_strike - 500)
        & (df_oc["Strike"] <= atm_strike + 500)
    ].copy()

    # Convert strikes to string type to strictly force full integer labels (24300) without SI conversion (24.3k)
    df_filtered["Strike_Label"] = df_filtered["Strike"].astype(str)

    # ---------------------------------------------------------
    # TABBED ANALYTICS DASHBOARD
    # ---------------------------------------------------------
    tab1, tab2, tab3, tab4 = st.tabs(
        [
            "🎯 Net Delta-Weighted OI",
            "⚡ Strike IV Spread Skew",
            "📊 Net GEX Profile",
            "📋 Options Data Grid",
        ]
    )

    # TAB 1: Net Delta-Weighted Open Interest Tool
    with tab1:
        st.subheader("Net Delta-Weighted Open Interest Across Strikes")
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
                name="Net Delta-Weighted OI",
            )
        )

        fig_delta_oi.update_xaxes(type="category", title="Strike Price")
        fig_delta_oi.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            yaxis_title="Delta-Weighted Contracts",
        )
        st.plotly_chart(fig_delta_oi, use_container_width=True)

    # TAB 2: ATM / Strike IV Spread Tool
    with tab2:
        st.subheader("Implied Volatility Curve & IV Spread (Call IV - Put IV)")
        fig_iv = go.Figure()

        fig_iv.add_trace(
            go.Scatter(
                x=df_filtered["Strike_Label"],
                y=df_filtered["CE_IV"],
                name="Call IV (%)",
                line=dict(color="#EF5350", width=2),
            )
        )
        fig_iv.add_trace(
            go.Scatter(
                x=df_filtered["Strike_Label"],
                y=df_filtered["PE_IV"],
                name="Put IV (%)",
                line=dict(color="#26A69A", width=2),
            )
        )
        fig_iv.add_trace(
            go.Scatter(
                x=df_filtered["Strike_Label"],
                y=df_filtered["IV_Spread"],
                name="IV Spread (CE - PE)",
                line=dict(color="#FFA726", width=2, dash="dot"),
            )
        )

        fig_iv.add_hline(
            y=0, line_dash="dash", line_color="white", opacity=0.4
        )
        fig_iv.update_xaxes(type="category", title="Strike Price")
        fig_iv.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            yaxis_title="Volatility (%) / Spread Points",
            legend=dict(orientation="h", y=1.1),
        )
        st.plotly_chart(fig_iv, use_container_width=True)

    # TAB 3: Net GEX Profile
    with tab3:
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
                name="Net GEX (₹ Lakhs)",
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

    # TAB 4: Clean Data Grid
    with tab4:
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
                "Net_GEX",
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
                    "Net_GEX": "{:+,.1f}L",
                    "CE_IV": "{:.1f}%",
                    "PE_IV": "{:.1f}%",
                    "IV_Spread": "{:+.2f}%",
                }
            ),
            use_container_width=True,
            height=450,
        )
