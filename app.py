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
    page_title="Nifty GEX Desk | Dhan API",
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

st.title("⚡ NIFTY 50 Gamma Exposure (GEX) Monitor")

# API Secrets
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
# 2. PURE-MATH BLACK-SCHOLES GREEK ENGINE
# ---------------------------------------------------------
def calculate_bs_greeks(
    S, K, T, sigma, r=0.07
):
    """Fallback calculation for Gamma, Vanna, and Charm if API Greeks are zero."""
    if T <= 1e-5 or sigma <= 1e-4 or S <= 0 or K <= 0:
        return 0.0, 0.0, 0.0

    try:
        d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (
            sigma * math.sqrt(T)
        )
        d2 = d1 - sigma * math.sqrt(T)

        pdf_d1 = (1.0 / math.sqrt(2 * math.pi)) * math.exp(-0.5 * d1 * d1)

        # Gamma
        gamma = pdf_d1 / (S * sigma * math.sqrt(T))

        # Vanna = d(Vega)/dS = -pdf(d1) * d2 / sigma
        vanna = -pdf_d1 * d2 / sigma

        # Charm = d(Delta)/dt
        charm = -pdf_d1 * (
            2 * r * math.sqrt(T) - d2 * sigma
        ) / (2 * T * sigma)

        return gamma, vanna, charm
    except Exception:
        return 0.0, 0.0, 0.0


# ---------------------------------------------------------
# 3. DIRECT REST API DATA ENGINE WITH GEX CALCULATIONS
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

            # Calculate Time to Expiry in Years
            exp_date_obj = datetime.datetime.strptime(
                expiry_date, "%Y-%m-%d"
            ).date()
            days_to_exp = max((exp_date_obj - datetime.date.today()).days, 1)
            T_years = days_to_exp / 365.0

            records = []
            for strike_str, details in oc_raw.items():
                strike = float(strike_str)
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

                # Fallback to pure-math Black-Scholes if Gamma is 0
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

                # ---------------------------------------------------------
                # GEX, DEX, VEX, CHEX FORMULAS (in ₹ Lakhs)
                # ---------------------------------------------------------
                # Call GEX is positive (dealers long calls)
                call_gex = (
                    ce_oi
                    * ce_gamma
                    * (spot_price**2)
                    * 0.01
                    * NIFTY_LOT_SIZE
                    / 1e5
                )
                # Put GEX is negative (dealers short puts)
                put_gex = (
                    -pe_oi
                    * pe_gamma
                    * (spot_price**2)
                    * 0.01
                    * NIFTY_LOT_SIZE
                    / 1e5
                )
                net_gex = call_gex + put_gex

                # Delta Exposure (DEX)
                call_dex = ce_oi * ce_delta * spot_price * NIFTY_LOT_SIZE / 1e5
                put_dex = pe_oi * pe_delta * spot_price * NIFTY_LOT_SIZE / 1e5
                net_dex = call_dex + put_dex

                # Vanna Exposure (VEX) - Volatility sensitivity
                net_vex = (
                    (ce_oi * ce_vanna) - (pe_oi * pe_vanna)
                ) * NIFTY_LOT_SIZE / 1e3

                # Charm Exposure (CHEX) - Time decay flow
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
                        "Call_GEX": call_gex,
                        "Put_GEX": put_gex,
                        "Net_GEX": net_gex,
                        "Net_DEX": net_dex,
                        "Net_VEX": net_vex,
                        "Net_CHEX": net_chex,
                        "CE_IV": ce_iv * 100.0,
                        "PE_IV": pe_iv * 100.0,
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

if st.sidebar.button("🔄 Manual Refresh"):
    st.cache_data.clear()

# Fetch GEX Data
df_oc, spot_price, error_remark = fetch_gex_option_chain(selected_expiry)


# ---------------------------------------------------------
# 5. GEX ANALYTICS ENGINE & DASHBOARD RENDER
# ---------------------------------------------------------
if error_remark:
    st.error(f"⚠️ **Dhan Server Error:** {error_remark}")
elif df_oc is not None and not df_oc.empty:
    atm_strike = round(spot_price / 50) * 50

    # 1. Identify Key Levels
    call_wall_strike = df_oc.loc[df_oc["Call_GEX"].idxmax()]["Strike"]
    put_wall_strike = df_oc.loc[df_oc["Put_GEX"].idxmin()]["Strike"]
    max_pos_gex_strike = df_oc.loc[df_oc["Net_GEX"].idxmax()]["Strike"]
    max_neg_gex_strike = df_oc.loc[df_oc["Net_GEX"].idxmin()]["Strike"]
    highest_oi_strike = df_oc.loc[df_oc["Total_OI"].idxmax()]["Strike"]

    # 2. Calculate Gamma Flip Level (Interpolated zero crossing of cumulative Net GEX)
    df_sorted = df_oc.sort_values("Strike").copy()
    df_sorted["Cum_Net_GEX"] = df_sorted["Net_GEX"].cumsum()

    # Find where sign flips
    gamma_flip_strike = spot_price  # default
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
            gamma_flip_strike = (s1 + s2) / 2.0
            break

    # 3. Determine Dealer Gamma Regime
    total_net_gex = df_oc["Net_GEX"].sum()
    is_pos_gamma = spot_price >= gamma_flip_strike or total_net_gex > 0
    regime_text = (
        "POSITIVE GAMMA (PINNING / LOW VOL)"
        if is_pos_gamma
        else "NEGATIVE GAMMA (AMPLIFICATION / HIGH VOL)"
    )
    flip_distance_pct = (
        (spot_price - gamma_flip_strike) / gamma_flip_strike
    ) * 100.0

    # TOP METRICS CARDS
    c1, c2, c3, c4, c5 = st.columns(5)

    with c1:
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

    with c2:
        flip_class = "sub-green" if spot_price >= gamma_flip_strike else "sub-red"
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-title">GAMMA FLIP LEVEL</div>
                <div class="metric-value">₹{gamma_flip_strike:,.0f}</div>
                <div class="metric-sub {flip_class}">Dist: {flip_distance_pct:+.2f}%</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with c3:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-title">CALL WALL (RESISTANCE)</div>
                <div class="metric-value">₹{call_wall_strike:,.0f}</div>
                <div class="metric-sub sub-red">Max Call GEX</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with c4:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-title">PUT WALL (SUPPORT)</div>
                <div class="metric-value">₹{put_wall_strike:,.0f}</div>
                <div class="metric-sub sub-green">Max Put GEX</div>
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
                <div class="metric-sub {net_gex_class}">Across Strikes</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # DEALER REGIME STATUS BADGE
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

    # ---------------------------------------------------------
    # TABBED GEX & EXPOSURE PANELS
    # ---------------------------------------------------------
    tab1, tab2, tab3, tab4 = st.tabs(
        [
            "📊 Net GEX Profile",
            "🎯 Call vs Put GEX Stack",
            "⚡ Higher-Order Exposures (DEX/VEX/CHEX)",
            "📋 Levels Summary & Data Grid",
        ]
    )

    # TAB 1: Net GEX Bar Chart
    with tab1:
        st.subheader("Net Gamma Exposure (GEX) by Strike")
        fig_gex = go.Figure()

        colors = [
            "#26A69A" if g >= 0 else "#EF5350" for g in df_filtered["Net_GEX"]
        ]
        fig_gex.add_trace(
            go.Bar(
                x=df_filtered["Strike"],
                y=df_filtered["Net_GEX"],
                marker_color=colors,
                name="Net GEX (₹ Lakhs)",
            )
        )

        # Key Level Reference Lines
        fig_gex.add_vline(
            x=spot_price,
            line_dash="solid",
            line_color="#FFD700",
            annotation_text="Spot",
        )
        fig_gex.add_vline(
            x=gamma_flip_strike,
            line_dash="dash",
            line_color="#29B6F6",
            annotation_text="Flip",
        )
        fig_gex.add_vline(
            x=call_wall_strike,
            line_dash="dot",
            line_color="#EF5350",
            annotation_text="Call Wall",
        )
        fig_gex.add_vline(
            x=put_wall_strike,
            line_dash="dot",
            line_color="#26A69A",
            annotation_text="Put Wall",
        )

        fig_gex.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            xaxis_title="Strike Price",
            yaxis_title="Net GEX (₹ Lakhs / 1% Move)",
        )
        st.plotly_chart(fig_gex, use_container_width=True)

    # TAB 2: Call vs Put GEX Stack
    with tab2:
        st.subheader("Call GEX (Positive) vs Put GEX (Negative)")
        fig_stack = go.Figure()
        fig_stack.add_trace(
            go.Bar(
                x=df_filtered["Strike"],
                y=df_filtered["Call_GEX"],
                name="Call GEX (+)",
                marker_color="#EF5350",
            )
        )
        fig_stack.add_trace(
            go.Bar(
                x=df_filtered["Strike"],
                y=df_filtered["Put_GEX"],
                name="Put GEX (-)",
                marker_color="#26A69A",
            )
        )

        fig_stack.add_vline(
            x=spot_price,
            line_dash="solid",
            line_color="#FFD700",
            annotation_text="Spot",
        )
        fig_stack.update_layout(
            barmode="relative",
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            xaxis_title="Strike Price",
            yaxis_title="GEX Breakdown (₹ Lakhs)",
        )
        st.plotly_chart(fig_stack, use_container_width=True)

    # TAB 3: DEX, VEX, CHEX Stack
    with tab3:
        st.subheader("Higher-Order Greek Exposures")
        g1, g2, g3 = st.columns(3)

        with g1:
            st.markdown("**Delta Exposure (DEX)**")
            fig_dex = px.bar(
                df_filtered,
                x="Strike",
                y="Net_DEX",
                color="Net_DEX",
                color_continuous_scale="RdYlGn",
                template="plotly_dark",
            )
            fig_dex.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)"
            )
            st.plotly_chart(fig_dex, use_container_width=True)

        with g2:
            st.markdown("**Vanna Exposure (VEX - IV Sensitivity)**")
            fig_vex = px.line(
                df_filtered,
                x="Strike",
                y="Net_VEX",
                markers=True,
                template="plotly_dark",
            )
            fig_vex.update_traces(line_color="#FFA726")
            fig_vex.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)"
            )
            st.plotly_chart(fig_vex, use_container_width=True)

        with g3:
            st.markdown("**Charm Exposure (CHEX - Time Decay)**")
            fig_chex = px.line(
                df_filtered,
                x="Strike",
                y="Net_CHEX",
                markers=True,
                template="plotly_dark",
            )
            fig_chex.update_traces(line_color="#AB47BC")
            fig_chex.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)"
            )
            st.plotly_chart(fig_chex, use_container_width=True)

    # TAB 4: Summary Table & Grid
    with tab4:
        st.subheader("Key Levels Breakdown")

        summary_data = {
            "Key Level Metric": [
                "Gamma Flip Level",
                "Call Wall (Resistance)",
                "Put Wall (Support)",
                "Max Positive Gamma (Pin)",
                "Max Negative Gamma (Squeeze)",
                "Highest OI Strike (Magnet)",
            ],
            "Strike Price": [
                f"₹{gamma_flip_strike:,.0f}",
                f"₹{call_wall_strike:,.0f}",
                f"₹{put_wall_strike:,.0f}",
                f"₹{max_pos_gex_strike:,.0f}",
                f"₹{max_neg_gex_strike:,.0f}",
                f"₹{highest_oi_strike:,.0f}",
            ],
            "Market Role": [
                "Price threshold where dealer regime switches long/short gamma",
                "Heaviest Call GEX concentration; acts as strong resistance",
                "Heaviest Put GEX concentration; acts as strong support",
                "Strike where intraday price is most strongly pinned",
                "Strike where a breakdown accelerates volatility squeeze",
                "0DTE / Weekly expiry magnet strike attracting settlement",
            ],
        }
        st.table(pd.DataFrame(summary_data))

        st.subheader("GEX Options Data Table")
        grid_df = df_filtered[
            [
                "Strike",
                "CE_LTP",
                "PE_LTP",
                "CE_OI",
                "PE_OI",
                "Call_GEX",
                "Put_GEX",
                "Net_GEX",
                "Net_DEX",
                "CE_IV",
                "PE_IV",
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
                    "Call_GEX": "{:+,.1f}L",
                    "Put_GEX": "{:+,.1f}L",
                    "Net_GEX": "{:+,.1f}L",
                    "Net_DEX": "{:+,.1f}L",
                    "CE_IV": "{:.1f}%",
                    "PE_IV": "{:.1f}%",
                }
            ),
            use_container_width=True,
            height=400,
        )
