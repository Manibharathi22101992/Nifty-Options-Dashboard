import time
import datetime
import threading
import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from config import config
import api_client as api
import math_engine as mathx
import charts

# ---------------------------------------------------------
# 1. STATE & DAEMON MANAGEMENT
# ---------------------------------------------------------
if 'SHARED' not in st.session_state:
    st.session_state.SHARED = {"active_expiry": None, "api_latency": 0.0, "daemon_running": False}

def background_worker():
    while True:
        exp = st.session_state.SHARED.get("active_expiry")
        if exp:
            df, spot, lat, err = api.fetch_option_chain(exp)
            if not err and not df.empty:
                # Update persistent analytics here (CSV saving logic)
                pass 
        time.sleep(60)

if not st.session_state.SHARED["daemon_running"]:
    threading.Thread(target=background_worker, daemon=True).start()
    st.session_state.SHARED["daemon_running"] = True

# ---------------------------------------------------------
# 2. UI LAYOUT & DATA FETCHING
# ---------------------------------------------------------
now_ist = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
is_live = now_ist.weekday() < 5 and (datetime.time(9, 15) <= now_ist.time() <= datetime.time(15, 30))

st.sidebar.header("⚙️ Volatility Desk")
if st.sidebar.checkbox("Live Auto-Refresh (5s)", value=is_live): st_autorefresh(interval=5000, key="refresh")

# Initialize valid expiries (mocked list for demonstration, implement actual fetch here if needed)
valid_expiries = ["2026-08-04", "2026-08-11", "2026-08-18"] # Should be populated from API
selected_expiry = st.sidebar.selectbox("Primary Expiry", valid_expiries)
st.session_state.SHARED["active_expiry"] = selected_expiry

df_oc, spot_price, latency, err = api.fetch_option_chain(selected_expiry)
st.session_state.SHARED["api_latency"] = latency

# ---------------------------------------------------------
# 3. HEALTH STRIP & ERROR HANDLING
# ---------------------------------------------------------
st.markdown("### PRINCE PAX DASHBOARD")
health_html = f"""
<div class='health-strip'>
    <div>🔌 Status: <span style='color:{config.COLORS['green'] if is_live else config.COLORS['amber']};'>{"LIVE" if is_live else "CLOSED"}</span></div>
    <div>🎯 Expiry: <span style='color:var(--text-main);'>{selected_expiry}</span></div>
    <div>⚡ Latency: <span style='color:{config.COLORS['green'] if latency<500 else config.COLORS['amber']};'>{latency} ms</span></div>
    <div>🤖 Daemon: <span style='color:var(--green);'>ACTIVE</span></div>
</div>
"""
st.markdown(health_html, unsafe_allow_html=True)

if err or df_oc.empty:
    st.error(f"⚠️ API Pipeline Offline: {err}. Reconnecting on next tick...")
    st.stop()

# ---------------------------------------------------------
# 4. CALCULATION & UI RENDERING
# ---------------------------------------------------------
try: exp_date = pd.to_datetime(selected_expiry[:10]).date()
except: exp_date = datetime.date.today() + datetime.timedelta(days=1)
T_years = max((exp_date - datetime.date.today()).days, 1) / 365.0

synthetic_future = mathx.calculate_forward_price(spot_price, df_oc, T_years)
gamma_flip = mathx.interpolate_gamma_flip(df_oc)
atm_strike = int(round(synthetic_future / 50) * 50)

df_filtered = df_oc[(df_oc["Strike"] >= atm_strike - 550) & (df_oc["Strike"] <= atm_strike + 550)].copy()

# PREMIUM HERO BANNER
st.markdown(f'<div class="hero-banner"><div style="color:var(--text-muted); font-size:1.1rem; font-weight:800; letter-spacing:1px; margin-bottom:5px;">NIFTY SYNTHETIC FUTURE (TRUE FWD)</div><div style="color:var(--text-main); font-size:3.5rem; font-weight:900; letter-spacing:-1px; text-shadow: 0px 0px 10px rgba(255,255,255,0.1);">₹{synthetic_future:,.2f}</div><div style="color:var(--amber); font-size:1rem; font-weight:600; margin-top:5px;">Spot Market: ₹{spot_price:,.2f} &nbsp;&nbsp;|&nbsp;&nbsp; Interpolated Gamma Flip: {gamma_flip:.1f}</div></div>', unsafe_allow_html=True)

tab1, tab2, tab3 = st.tabs(["🛡️ Exposure Engine", "🔬 Market Internals", "📊 Data Grid"])

with tab1:
    col1, col2 = st.columns(2)
    with col1:
        st.markdown('<div class="chart-container"><div class="chart-title">Net Gamma Exposure (GEX)</div>', unsafe_allow_html=True)
        fig_gex = charts.plot_exposure_profile(df_filtered, "GEX", "Call_GEX", "Put_GEX", "Net_GEX", "ABS_GEX", spot_price, gamma_flip)
        st.plotly_chart(fig_gex, use_container_width=True, config=charts.PLOT_CONFIG)
        st.markdown('</div>', unsafe_allow_html=True)
    with col2:
        st.markdown('<div class="chart-container"><div class="chart-title">Net Delta Exposure (DEX)</div>', unsafe_allow_html=True)
        fig_dex = charts.plot_exposure_profile(df_filtered, "DEX", "CE_Delta", "PE_Delta", "Net_DEX", "ABS_DEX", spot_price, None)
        st.plotly_chart(fig_dex, use_container_width=True, config=charts.PLOT_CONFIG)
        st.markdown('</div>', unsafe_allow_html=True)

with tab3:
    st.markdown('<div class="chart-container"><div class="chart-title">Vectorized Options Chain Grid</div>', unsafe_allow_html=True)
    grid_df = df_filtered[["Strike", "CE_LTP", "PE_LTP", "CE_OI_Chg", "PE_OI_Chg", "CE_Delta", "PE_Delta", "Net_DEX", "Net_GEX", "CE_Vega", "PE_Vega", "CE_IV", "PE_IV"]].copy()
    
    # Styled Grid
    styled_df = grid_df.style.background_gradient(subset=['CE_OI_Chg', 'PE_OI_Chg'], cmap='RdYlGn') \
        .format({"Strike": "{:.0f}", "CE_LTP": "₹{:.1f}", "PE_LTP": "₹{:.1f}", "CE_IV": "{:.1f}%", "PE_IV": "{:.1f}%", "Net_DEX": "{:+.1f}L", "Net_GEX": "{:+.1f}L"})
    st.dataframe(styled_df, use_container_width=True, height=600)
    st.markdown('</div>', unsafe_allow_html=True)
