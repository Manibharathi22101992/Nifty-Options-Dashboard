import datetime
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st
from streamlit_autorefresh import st_autorefresh

# ---------------------------------------------------------
# 1. PAGE SETUP & INSTITUTIONAL DARK THEME
# ---------------------------------------------------------
st.set_page_config(
    page_title="Nifty Quant Desk | Dhan API",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS Injection for Bloomberg/TradingView Terminal Look
st.markdown(
    """
    <style>
    /* Global Page Styling */
    .stApp {
        background-color: #0b0e14;
        color: #e0e6ed;
    }
    
    /* Sidebar Styling */
    section[data-testid="stSidebar"] {
        background-color: #121721 !important;
        border-right: 1px solid #1e2638;
    }
    
    /* Glassmorphism Metric Cards */
    .metric-card {
        background: #161c28;
        border: 1px solid #232d42;
        border-radius: 8px;
        padding: 14px 18px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
        margin-bottom: 10px;
    }
    .metric-title {
        color: #8b9bb4;
        font-size: 0.78rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .metric-value {
        color: #ffffff;
        font-size: 1.45rem;
        font-weight: 700;
        margin-top: 4px;
    }
    .metric-sub {
        font-size: 0.8rem;
        font-weight: 600;
        margin-top: 2px;
    }
    .sub-green { color: #00E676; }
    .sub-red { color: #FF5252; }
    .sub-amber { color: #FFD700; }

    /* Tab Headers */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: #121721;
        padding: 6px;
        border-radius: 8px;
        border: 1px solid #1e2638;
    }
    .stTabs [data-baseweb="tab"] {
        height: 40px;
        background-color: transparent;
        border-radius: 6px;
        color: #8b9bb4;
        font-weight: 600;
    }
    .stTabs [aria-selected="true"] {
        background-color: #232d42 !important;
        color: #ffffff !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("⚡ NIFTY 50 Quantitative Options Desk")

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


# ---------------------------------------------------------
# 2. REST API DATA ENGINE
# ---------------------------------------------------------
@st.cache_data(ttl=3)
def fetch_option_chain_direct(expiry_date):
    """Fetches full option chain directly from DhanHQ REST API v2."""
    url = "https://api.dhan.co/v2/optionchain"
    headers = {
        "client-id": CLIENT_ID,
        "access-token": ACCESS_TOKEN,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = {
        "UnderlyingScrip": 13,  # NIFTY 50
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

            records = []
            for strike, details in oc_raw.items():
                ce = details.get("ce", {})
                pe = details.get("pe", {})

                ce_oi = float(ce.get("oi", 0))
                pe_oi = float(pe.get("oi", 0))
                ce_prev_oi = float(ce.get("previous_close_oi", ce_oi))
                pe_prev_oi = float(pe.get("previous_close_oi", pe_oi))

                ce_delta = float(ce.get("greeks", {}).get("delta", 0))
                pe_delta = float(pe.get("greeks", {}).get("delta", 0))

                records.append(
                    {
                        "Strike": float(strike),
                        "CE_LTP": float(ce.get("last_price", 0)),
                        "CE_OI": ce_oi,
                        "CE_OI_Change": ce_oi - ce_prev_oi,
                        "CE_IV": float(ce.get("implied_volatility", 0)),
                        "CE_Delta": ce_delta,
                        "PE_LTP": float(pe.get("last_price", 0)),
                        "PE_OI": pe_oi,
                        "PE_OI_Change": pe_oi - pe_prev_oi,
                        "PE_IV": float(pe.get("implied_volatility", 0)),
                        "PE_Delta": pe_delta,
                        # Net Delta Exposure Calculation
                        "Net_Delta_Exposure": (ce_oi * ce_delta)
                        + (pe_oi * pe_delta),
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
# 3. SIDEBAR & LIVE AUTO-REFRESH CONTROLS
# ---------------------------------------------------------
st.sidebar.header("⚙️ Controls & Feeds")

# Auto-Refresh Toggle
auto_refresh = st.sidebar.checkbox("Enable Live Auto-Refresh (5s)", value=True)
if auto_refresh:
    st_autorefresh(interval=5000, key="datarefresh")

today = datetime.date.today()
days_until_thursday = (3 - today.weekday()) % 7
default_expiry = today + datetime.timedelta(days=days_until_thursday)

selected_expiry = st.sidebar.date_input(
    "Expiry Date", default_expiry
).strftime("%Y-%m-%d")

if st.sidebar.button("🔄 Manual Refresh"):
    st.cache_data.clear()

# Fetch Option Data
df_oc, spot_price, error_remark = fetch_option_chain_direct(selected_expiry)


# ---------------------------------------------------------
# 4. QUANTITATIVE DASHBOARD UI
# ---------------------------------------------------------
if error_remark:
    st.error(f"⚠️ **Dhan Server Error:** {error_remark}")
elif df_oc is not None and not df_oc.empty:
    atm_strike = round(spot_price / 50) * 50

    # Locate ATM Contract Details
    atm_row = df_oc[df_oc["Strike"] == atm_strike]
    if not atm_row.empty:
        ce_atm_ltp = atm_row["CE_LTP"].values[0]
        pe_atm_ltp = atm_row["PE_LTP"].values[0]
    else:
        ce_atm_ltp, pe_atm_ltp = 0.0, 0.0

    # 1. Synthetic Nifty & Put-Call Parity Engine
    # Synthetic Spot = Strike + Call Premium - Put Premium
    synthetic_spot = atm_strike + ce_atm_ltp - pe_atm_ltp
    parity_gap = synthetic_spot - spot_price

    # 2. ATM Straddle & Expected Range
    atm_straddle = ce_atm_ltp + pe_atm_ltp
    upper_range = spot_price + atm_straddle
    lower_range = spot_price - atm_straddle

    # 3. Overall PCR
    total_call_oi = df_oc["CE_OI"].sum()
    total_put_oi = df_oc["PE_OI"].sum()
    total_pcr = total_put_oi / total_call_oi if total_call_oi > 0 else 0.0

    # TOP METRICS BANNER (GLASS CARDS)
    m1, m2, m3, m4, m5 = st.columns(5)

    with m1:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-title">NIFTY SPOT</div>
                <div class="metric-value">₹{spot_price:,.2f}</div>
                <div class="metric-sub sub-amber">ATM: {atm_strike:.0f}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with m2:
        gap_class = "sub-green" if parity_gap >= 0 else "sub-red"
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-title">SYNTHETIC SPOT</div>
                <div class="metric-value">₹{synthetic_spot:,.2f}</div>
                <div class="metric-sub {gap_class}">Parity Gap: {parity_gap:+.2f}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with m3:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-title">ATM STRADDLE</div>
                <div class="metric-value">₹{atm_straddle:,.2f}</div>
                <div class="metric-sub sub-amber">CE: {ce_atm_ltp:.1f} | PE: {pe_atm_ltp:.1f}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with m4:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-title">EXPECTED RANGE</div>
                <div class="metric-value">±{atm_straddle:,.0f} Pts</div>
                <div class="metric-sub sub-green">{lower_range:,.0f} - {upper_range:,.0f}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with m5:
        pcr_class = "sub-green" if total_pcr >= 1.0 else "sub-red"
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-title">OVERALL PCR</div>
                <div class="metric-value">{total_pcr:.2f}</div>
                <div class="metric-sub {pcr_class}">{"BULLISH" if total_pcr >= 1.0 else "BEARISH"}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # Filter Strikes Near ATM (+/- 500 Points)
    df_filtered = df_oc[
        (df_oc["Strike"] >= atm_strike - 500)
        & (df_oc["Strike"] <= atm_strike + 500)
    ].copy()

    # ---------------------------------------------------------
    # TABBED QUANTITATIVE ANALYTICS
    # ---------------------------------------------------------
    tab1, tab2, tab3, tab4 = st.tabs(
        [
            "📊 Open Interest Concentration",
            "⚡ Synthetic & IV Skew",
            "🎯 Delta Exposure Profile",
            "📋 Institutional Data Grid",
        ]
    )

    # TAB 1: Total OI & Intraday OI Change
    with tab1:
        c1, c2 = st.columns(2)

        with c1:
            st.subheader("Total Open Interest Profile")
            fig_oi = go.Figure()
            fig_oi.add_trace(
                go.Bar(
                    x=df_filtered["Strike"],
                    y=df_filtered["CE_OI"],
                    name="Call OI (Resistance)",
                    marker_color="#EF5350",
                )
            )
            fig_oi.add_trace(
                go.Bar(
                    x=df_filtered["Strike"],
                    y=df_filtered["PE_OI"],
                    name="Put OI (Support)",
                    marker_color="#26A69A",
                )
            )
            fig_oi.add_vline(
                x=spot_price,
                line_dash="dash",
                line_color="#FFD700",
                annotation_text="Spot",
            )
            fig_oi.update_layout(
                barmode="group",
                template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                legend=dict(orientation="h", y=1.1),
            )
            st.plotly_chart(fig_oi, use_container_width=True)

        with c2:
            st.subheader("Intraday OI Change (Writing vs Unwinding)")
            fig_oic = go.Figure()
            fig_oic.add_trace(
                go.Bar(
                    x=df_filtered["Strike"],
                    y=df_filtered["CE_OI_Change"],
                    name="CE OI Change",
                    marker_color="#EF5350",
                )
            )
            fig_oic.add_trace(
                go.Bar(
                    x=df_filtered["Strike"],
                    y=df_filtered["PE_OI_Change"],
                    name="PE OI Change",
                    marker_color="#26A69A",
                )
            )
            fig_oic.add_vline(
                x=spot_price,
                line_dash="dash",
                line_color="#FFD700",
                annotation_text="Spot",
            )
            fig_oic.update_layout(
                barmode="group",
                template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                legend=dict(orientation="h", y=1.1),
            )
            st.plotly_chart(fig_oic, use_container_width=True)

    # TAB 2: IV Skew & Spread
    with tab2:
        st.subheader("Implied Volatility Curve & Skew (CE IV vs PE IV)")
        df_filtered["IV_Spread"] = df_filtered["CE_IV"] - df_filtered["PE_IV"]

        fig_iv = go.Figure()
        fig_iv.add_trace(
            go.Scatter(
                x=df_filtered["Strike"],
                y=df_filtered["CE_IV"],
                name="Call IV",
                line=dict(color="#EF5350", width=2),
            )
        )
        fig_iv.add_trace(
            go.Scatter(
                x=df_filtered["Strike"],
                y=df_filtered["PE_IV"],
                name="Put IV",
                line=dict(color="#26A69A", width=2),
            )
        )
        fig_iv.add_trace(
            go.Scatter(
                x=df_filtered["Strike"],
                y=df_filtered["IV_Spread"],
                name="IV Spread (CE-PE)",
                line=dict(color="#FFA726", width=2, dash="dot"),
            )
        )
        fig_iv.add_vline(
            x=spot_price,
            line_dash="dash",
            line_color="#FFD700",
            annotation_text="Spot",
        )
        fig_iv.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            xaxis_title="Strike Price",
            yaxis_title="Volatility (%)",
            legend=dict(orientation="h", y=1.1),
        )
        st.plotly_chart(fig_iv, use_container_width=True)

    # TAB 3: Net Delta Exposure Profile
    with tab3:
        st.subheader("Delta Exposure Concentration (OI × Delta)")
        fig_delta = go.Figure()
        colors = [
            "#26A69A" if val >= 0 else "#EF5350"
            for val in df_filtered["Net_Delta_Exposure"]
        ]

        fig_delta.add_trace(
            go.Bar(
                x=df_filtered["Strike"],
                y=df_filtered["Net_Delta_Exposure"],
                marker_color=colors,
                name="Net Delta Exposure",
            )
        )
        fig_delta.add_vline(
            x=spot_price,
            line_dash="dash",
            line_color="#FFD700",
            annotation_text="Spot",
        )
        fig_delta.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            xaxis_title="Strike Price",
            yaxis_title="Net Delta Contracts",
        )
        st.plotly_chart(fig_delta, use_container_width=True)

    # TAB 4: Institutional Grid
    with tab4:
        st.subheader("Live Market Depth & Greeks Table")

        # Format DataFrame columns nicely
        grid_df = df_filtered[
            [
                "CE_Delta",
                "CE_IV",
                "CE_LTP",
                "CE_OI",
                "CE_OI_Change",
                "Strike",
                "PE_OI_Change",
                "PE_OI",
                "PE_LTP",
                "PE_IV",
                "PE_Delta",
            ]
        ].copy()

        st.dataframe(
            grid_df.style.format(
                {
                    "CE_Delta": "{:.2f}",
                    "CE_IV": "{:.1f}%",
                    "CE_LTP": "₹{:.2f}",
                    "CE_OI": "{:,.0f}",
                    "CE_OI_Change": "{:+,.0f}",
                    "Strike": "{:.0f}",
                    "PE_OI_Change": "{:+,.0f}",
                    "PE_OI": "{:,.0f}",
                    "PE_LTP": "₹{:.2f}",
                    "PE_IV": "{:.1f}%",
                    "PE_Delta": "{:.2f}",
                }
            ),
            use_container_width=True,
            height=450,
        )
