import datetime
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st

# ---------------------------------------------------------
# 1. PAGE SETUP & AUTHENTICATION
# ---------------------------------------------------------
st.set_page_config(
    page_title="Nifty Options Desk",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.title("⚡ Nifty Options Analytics Desk")

# Clean API credentials from Streamlit Secrets
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
# 2. DIRECT REST API DATA ENGINE
# ---------------------------------------------------------
@st.cache_data(ttl=5)
def fetch_option_chain_direct(expiry_date):
    """Fetches option chain directly from DhanHQ REST API v2."""
    url = "https://api.dhan.co/v2/optionchain"
    headers = {
        "client-id": CLIENT_ID,
        "access-token": ACCESS_TOKEN,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    # Dhan supports IDX_I for Index Option Chains
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

                records.append(
                    {
                        "Strike": float(strike),
                        "CE_LTP": float(ce.get("last_price", 0)),
                        "CE_OI": ce_oi,
                        "CE_OI_Change": ce_oi - ce_prev_oi,
                        "CE_IV": float(ce.get("implied_volatility", 0)),
                        "CE_Delta": float(ce.get("greeks", {}).get("delta", 0)),
                        "PE_LTP": float(pe.get("last_price", 0)),
                        "PE_OI": pe_oi,
                        "PE_OI_Change": pe_oi - pe_prev_oi,
                        "PE_IV": float(pe.get("implied_volatility", 0)),
                        "PE_Delta": float(pe.get("greeks", {}).get("delta", 0)),
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
                or f"HTTP {res.status_code}: {res.text}"
            )
            return None, 0.0, str(remark)

    except Exception as e:
        return None, 0.0, f"Connection Error: {str(e)}"


# ---------------------------------------------------------
# 3. SIDEBAR & DASHBOARD RENDER
# ---------------------------------------------------------
st.sidebar.header("Settings")

today = datetime.date.today()
days_until_thursday = (3 - today.weekday()) % 7
default_expiry = today + datetime.timedelta(days=days_until_thursday)

selected_expiry = st.sidebar.date_input(
    "Select Expiry Date", default_expiry
).strftime("%Y-%m-%d")

if st.sidebar.button("🔄 Refresh Data"):
    st.cache_data.clear()

df_oc, spot_price, error_remark = fetch_option_chain_direct(selected_expiry)

if error_remark:
    st.error(f"⚠️ **Dhan Server Response:** {error_remark}")
    st.info(
        "💡 **Fix Action Needed:** If Dhan returned 'Authentication failure' or 'Invalid Token', ensure 'Data APIs' is activated in your Dhan portal and your Client ID in Secrets is your 10-digit account ID."
    )
elif df_oc is not None and not df_oc.empty:
    atm_strike = round(spot_price / 50) * 50

    df_filtered = df_oc[
        (df_oc["Strike"] >= atm_strike - 500)
        & (df_oc["Strike"] <= atm_strike + 500)
    ].copy()

    total_call_oi = df_oc["CE_OI"].sum()
    total_put_oi = df_oc["PE_OI"].sum()
    total_pcr = total_put_oi / total_call_oi if total_call_oi > 0 else 0.0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Nifty Spot", f"₹{spot_price:,.2f}")
    col2.metric("ATM Strike", f"{atm_strike}")
    col3.metric("Overall OI PCR", f"{total_pcr:.2f}")
    col4.metric(
        "Market Sentiment", "Bullish" if total_pcr > 1.0 else "Bearish"
    )

    st.markdown("---")

    tab1, tab2, tab3, tab4 = st.tabs(
        [
            "📈 OI & OI Change",
            "⚡ IV Spread & Skew",
            "⏳ IV Term Structure",
            "📊 Strike PCR",
        ]
    )

    with tab1:
        st.subheader("Intraday Open Interest Change (Call vs Put)")
        fig_oi = go.Figure()
        fig_oi.add_trace(
            go.Bar(
                x=df_filtered["Strike"],
                y=df_filtered["CE_OI_Change"],
                name="Call OI Change",
                marker_color="#EF5350",
            )
        )
        fig_oi.add_trace(
            go.Bar(
                x=df_filtered["Strike"],
                y=df_filtered["PE_OI_Change"],
                name="Put OI Change",
                marker_color="#26A69A",
            )
        )
        fig_oi.update_layout(
            barmode="group",
            xaxis_title="Strike Price",
            yaxis_title="Change in Contracts",
            template="plotly_dark",
        )
        st.plotly_chart(fig_oi, use_container_width=True)

    with tab2:
        st.subheader("Implied Volatility Spread (Call IV - Put IV)")
        df_filtered["IV_Spread"] = df_filtered["CE_IV"] - df_filtered["PE_IV"]
        fig_iv = go.Figure()
        fig_iv.add_trace(
            go.Scatter(
                x=df_filtered["Strike"],
                y=df_filtered["IV_Spread"],
                mode="lines+markers",
                name="IV Spread",
                line=dict(color="#FFA726", width=2),
            )
        )
        fig_iv.add_hline(
            y=0, line_dash="dash", line_color="white", opacity=0.5
        )
        fig_iv.update_layout(
            xaxis_title="Strike Price",
            yaxis_title="IV Difference (%)",
            template="plotly_dark",
        )
        st.plotly_chart(fig_iv, use_container_width=True)

    with tab3:
        st.subheader("ATM Implied Volatility Curve")
        fig_term = go.Figure()
        fig_term.add_trace(
            go.Scatter(
                x=df_filtered["Strike"],
                y=df_filtered["CE_IV"],
                mode="lines+markers",
                name="CE IV",
                line=dict(color="#EF5350"),
            )
        )
        fig_term.add_trace(
            go.Scatter(
                x=df_filtered["Strike"],
                y=df_filtered["PE_IV"],
                mode="lines+markers",
                name="PE IV",
                line=dict(color="#26A69A"),
            )
        )
        fig_term.update_layout(
            xaxis_title="Strike Price",
            yaxis_title="Implied Volatility (%)",
            template="plotly_dark",
        )
        st.plotly_chart(fig_term, use_container_width=True)

    with tab4:
        st.subheader("Strike-Wise Put-Call Ratio")
        df_filtered["Strike_PCR"] = df_filtered.apply(
            lambda r: r["PE_OI"] / r["CE_OI"] if r["CE_OI"] > 0 else 0, axis=1
        )
        fig_pcr = px.bar(
            df_filtered,
            x="Strike",
            y="Strike_PCR",
            color="Strike_PCR",
            color_continuous_scale="RdYlGn",
            template="plotly_dark",
        )
        fig_pcr.add_hline(
            y=1.0,
            line_dash="dash",
            line_color="yellow",
            annotation_text="Neutral (1.0)",
        )
        fig_pcr.update_layout(
            xaxis_title="Strike Price", yaxis_title="PCR Ratio"
        )
        st.plotly_chart(fig_pcr, use_container_width=True)

    st.subheader("📋 Option Chain Table")
    st.dataframe(
        df_filtered[
            [
                "CE_Delta",
                "CE_IV",
                "CE_LTP",
                "CE_OI",
                "Strike",
                "PE_OI",
                "PE_LTP",
                "PE_IV",
                "PE_Delta",
            ]
        ],
        use_container_width=True,
    )
