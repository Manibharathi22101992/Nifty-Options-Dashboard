import datetime
import time
import os
import threading
import logging
import math
from typing import Dict, List, Tuple, Optional, Any
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from streamlit_autorefresh import st_autorefresh

# Configure logging
logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ---------------------------------------------------------
# 1. NIFTY-SPECIFIC CONFIGURATION (2026)
# ---------------------------------------------------------
class Config:
    NIFTY_LOT_SIZE = 65
    RISK_FREE_RATE = 0.065
    NIFTY_DIVIDEND_YIELD = 0.012
    ASSUMED_HV_20D = 12.0  # Nifty typical 20-day realized vol baseline (%)
    API_TIMEOUT = 10
    MAX_RETRIES = 3
    STRIKE_INTERVAL = 50
    STRIKE_RANGE_ATM = 550
    MARKET_OPEN = "09:15:00"
    MARKET_CLOSE = "15:30:00"

try:
    from dhanhq import marketfeed
    DHAN_WS_AVAILABLE = True
except ImportError:
    DHAN_WS_AVAILABLE = False
    logger.warning("dhanhq not installed. WebSocket disabled.")

# ---------------------------------------------------------
# 2. BLOOMBERG-GRADE CSS
# ---------------------------------------------------------
st.set_page_config(
    page_title="Prince PAX | FlashAlpha Nifty Terminal",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');
    .stApp { background: radial-gradient(ellipse at top, #0F1419 0%, #050709 100%); color: #E0E6ED; font-family: 'Inter', -apple-system, sans-serif; }
    section[data-testid="stSidebar"] { background: linear-gradient(180deg, #0F1419 0%, #1A1F2E 100%) !important; border-right: 1px solid rgba(99, 179, 237, 0.2); }
    .metric-card { background: rgba(26, 32, 44, 0.7); backdrop-filter: blur(12px); border: 1px solid rgba(99, 179, 237, 0.2); border-radius: 12px; padding: 14px 18px; box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4); margin-bottom: 12px; border-top: 4px solid #63B3ED; transition: all 0.3s ease; }
    .metric-card:hover { transform: translateY(-2px); box-shadow: 0 12px 40px rgba(99, 179, 237, 0.15); border-color: rgba(99, 179, 237, 0.4); }
    .metric-card-green { border-top-color: #48BB78; } .metric-card-red { border-top-color: #F56565; } .metric-card-amber { border-top-color: #ECC94B; } .metric-card-purple { border-top-color: #9F7AEA; } .metric-card-cyan { border-top-color: #0BC5EA; }
    .metric-title { color: #A0AEC0; font-size: 0.68rem; font-weight: 700; text-transform: uppercase; letter-spacing: 1.2px; }
    .metric-value { color: #FFFFFF; font-size: 1.5rem; font-weight: 800; margin-top: 4px; font-variant-numeric: tabular-nums; }
    .metric-sub { font-size: 0.72rem; font-weight: 600; margin-top: 4px; }
    .sub-green { color: #48BB78; } .sub-red { color: #F56565; } .sub-amber { color: #ECC94B; } .sub-blue { color: #63B3ED; } .sub-purple { color: #9F7AEA; } .sub-cyan { color: #0BC5EA; }
    .chart-container { background: rgba(26, 32, 44, 0.5); backdrop-filter: blur(10px); border: 1px solid rgba(99, 179, 237, 0.15); border-radius: 12px; padding: 16px; margin-bottom: 16px; box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2); }
    .chart-title { font-size: 0.82rem; font-weight: 700; color: #63B3ED; text-transform: uppercase; margin-bottom: 12px; border-bottom: 2px solid rgba(99, 179, 237, 0.3); padding-bottom: 8px; display: flex; justify-content: space-between; align-items: center; letter-spacing: 0.5px; }
    .info-tooltip { position: relative; display: inline-block; cursor: help; color: #A0AEC0; font-size: 0.9rem; }
    .info-tooltip .tooltip-text { visibility: hidden; width: 320px; background: rgba(15, 20, 25, 0.97); backdrop-filter: blur(10px); color: #E0E6ED; text-align: left; border-radius: 8px; padding: 12px; position: absolute; top: 150%; right: 0; opacity: 0; transition: opacity 0.3s; border: 1px solid rgba(99, 179, 237, 0.3); font-size: 0.72rem; font-weight: 500; box-shadow: 0px 8px 24px rgba(0,0,0,0.8); z-index: 9999; line-height: 1.5; }
    .info-tooltip:hover .tooltip-text { visibility: visible; opacity: 1; } .info-tooltip:hover { color: #63B3ED; }
    .status-badge { padding: 8px 16px; border-radius: 6px; font-weight: 700; font-size: 0.78rem; display: inline-block; backdrop-filter: blur(10px); }
    .status-live { background: rgba(72, 187, 120, 0.15); border: 1px solid #48BB78; color: #48BB78; }
    .status-closed { background: rgba(236, 201, 75, 0.15); border: 1px solid #ECC94B; color: #ECC94B; }
    .narrative-box { background: rgba(99, 179, 237, 0.08); border-left: 4px solid #63B3ED; padding: 16px 20px; border-radius: 8px; margin-bottom: 20px; font-size: 0.9rem; line-height: 1.6; color: #E0E6ED; }
    .playbook-table { width: 100%; border-collapse: collapse; font-size: 0.82rem; margin-top: 12px; }
    .playbook-table th { background: rgba(15, 20, 25, 0.8); color: #63B3ED; text-align: left; padding: 10px; border: 1px solid rgba(99, 179, 237, 0.2); font-weight: 700; }
    .playbook-table td { padding: 10px; border: 1px solid rgba(99, 179, 237, 0.15); color: #E0E6ED; }
    button[data-baseweb="tab"] { background: rgba(26, 32, 44, 0.6) !important; color: #A0AEC0 !important; border-radius: 8px 8px 0 0 !important; border: 1px solid rgba(99, 179, 237, 0.2) !important; border-bottom: none !important; font-weight: 600 !important; padding: 10px 18px !important; transition: all 0.3s ease !important; }
    button[data-baseweb="tab"]:hover { background: rgba(99, 179, 237, 0.1) !important; color: #63B3ED !important; }
    button[data-baseweb="tab"][aria-selected="true"] { background: rgba(99, 179, 237, 0.2) !important; color: #63B3ED !important; font-weight: 800 !important; border-bottom: 2px solid #63B3ED !important; }
    </style>
    """, unsafe_allow_html=True)

CLIENT_ID = str(st.secrets.get("DHAN_CLIENT_ID", "")).strip().replace('"', "").replace("'", "")
ACCESS_TOKEN = str(st.secrets.get("DHAN_ACCESS_TOKEN", "")).strip().replace('"', "").replace("'", "")

if not CLIENT_ID or not ACCESS_TOKEN:
    st.error("⚠️ **CRITICAL:** API credentials missing. Update `.streamlit/secrets.toml`")
    st.stop()

# ---------------------------------------------------------
# 3. MATHEMATICAL & NARRATIVE ENGINE
# ---------------------------------------------------------
class MathEngine:
    @staticmethod
    def norm_pdf(x: np.ndarray) -> np.ndarray:
        return np.exp(-0.5 * x**2) / np.sqrt(2 * np.pi)
    
    @staticmethod
    def calculate_bs_greeks(S, K, T, sigma, r=Config.RISK_FREE_RATE, q=Config.NIFTY_DIVIDEND_YIELD):
        T, sigma, S, K = np.maximum(T, 1e-5), np.maximum(sigma, 1e-4), np.maximum(S, 1e-5), np.maximum(K, 1e-5)
        d1 = (np.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
        d2 = d1 - sigma * np.sqrt(T)
        pdf_d1 = MathEngine.norm_pdf(d1)
        
        gamma = np.exp(-q * T) * pdf_d1 / (S * sigma * np.sqrt(T))
        vanna = -np.exp(-q * T) * pdf_d1 * d2 / sigma
        charm = -np.exp(-q * T) * pdf_d1 * (2 * (r - q) * np.sqrt(T) - d2 * sigma * np.sqrt(T)) / (2 * T * sigma)
        speed = -gamma / S * (1 + d1 / (sigma * np.sqrt(T)))
        vomma = gamma * S * np.sqrt(T) * d1 * d2 / sigma
        return gamma, vanna, charm, speed, vomma
    
    @staticmethod
    def calculate_max_pain(strikes, ce_oi, pe_oi):
        K, S = strikes.reshape(-1, 1), strikes.reshape(1, -1)
        total_loss = np.sum(ce_oi * np.maximum(K - S, 0) + pe_oi * np.maximum(S - K, 0), axis=1)
        return int(strikes[np.argmin(total_loss)])

def generate_nifty_narrative(spot, net_gex, gamma_flip, call_wall, put_wall, max_pain, atm_iv, vrp, strad_regime, is_0dte, pcr_signal, gex_signal, vega_signal, downside_support, upside_resistance, implied_move_pct):
    regime = "positive_gamma" if net_gex > 0 else "negative_gamma"
    gex_text = "Dealers are net long gamma; expect mean-reverting tape and suppressed volatility." if net_gex > 0 else "Dealers are net short gamma; expect trending, volatile tape with accelerated moves."
    flip_text = f"Gamma flip is at {gamma_flip:,.0f}. " + ("Spot is above flip (bullish stabilization)." if spot > gamma_flip else "Spot is below flip (bearish acceleration).")
    wall_text = f"Key dealer walls: Call resistance at {call_wall:,.0f}, Put support at {put_wall:,.0f}."
    vrp_text = f"VRP is {vrp:+.1f}% (IV vs ~{Config.ASSUMED_HV_20D}% HV). " + ("Options are rich; consider selling premium." if vrp > 2.0 else "Options are cheap; consider buying premium." if vrp < -2.0 else "Options are fairly priced.")
    strad_text = f"Straddle regime: {strad_regime}."
    zdte_text = " Zero-DTE pin risk is elevated today." if is_0dte else ""
    
    return f"""**{regime.replace('_', ' ').title()} Regime.** {gex_text} {flip_text} 
**PCR Signal:** {pcr_signal}. **GEX Bias:** {gex_signal}. **Vega Outlook:** {vega_signal}.
{wall_text} {vrp_text} {strad_text}{zdte_text}
**Intraday Range:** {downside_support:.0f} - {upside_resistance:.0f} (±{implied_move_pct:.2f}%)."""

# ---------------------------------------------------------
# 4. DATA ENGINES
# ---------------------------------------------------------
@st.cache_data(ttl=300)
def fetch_expiry_list():
    url = "https://api.dhan.co/v2/optionchain/expirylist"
    headers = {"client-id": CLIENT_ID, "access-token": ACCESS_TOKEN, "Content-Type": "application/json"}
    for _ in range(Config.MAX_RETRIES):
        try:
            res = requests.post(url, headers=headers, json={"UnderlyingScrip": 13, "UnderlyingSeg": "IDX_I"}, timeout=Config.API_TIMEOUT)
            if res.status_code == 200 and res.json().get("status") == "success":
                return res.json().get("data", [])
        except Exception as e:
            time.sleep(1)
    return []

@st.cache_data(ttl=3)
def fetch_option_chain(expiry_date):
    url = "https://api.dhan.co/v2/optionchain"
    headers = {"client-id": CLIENT_ID, "access-token": ACCESS_TOKEN, "Content-Type": "application/json"}
    payload = {"UnderlyingScrip": 13, "UnderlyingSeg": "IDX_I", "Expiry": expiry_date}
    
    for _ in range(Config.MAX_RETRIES):
        try:
            res = requests.post(url, headers=headers, json=payload, timeout=Config.API_TIMEOUT)
            data = res.json()
            if res.status_code == 200 and data.get("status") == "success":
                raw = data.get("data", {})
                spot = float(raw.get("last_price", 0.0))
                oc = raw.get("oc", {})
                if not oc: return None, spot, "No contracts"
                
                T = max((datetime.datetime.strptime(expiry_date, "%Y-%m-%d").date() - datetime.date.today()).days, 1) / 365.0
                
                strikes = np.array([int(float(k)) for k in oc.keys()])
                ce_oi = np.array([float(oc[k].get("ce", {}).get("oi", 0) or 0) for k in oc.keys()])
                pe_oi = np.array([float(oc[k].get("pe", {}).get("oi", 0) or 0) for k in oc.keys()])
                ce_vol = np.array([float(oc[k].get("ce", {}).get("volume", 0) or 0) for k in oc.keys()])
                pe_vol = np.array([float(oc[k].get("pe", {}).get("volume", 0) or 0) for k in oc.keys()])
                ce_ltp = np.array([float(oc[k].get("ce", {}).get("last_price", 0) or 0) for k in oc.keys()])
                pe_ltp = np.array([float(oc[k].get("pe", {}).get("last_price", 0) or 0) for k in oc.keys()])
                ce_iv = np.array([float(oc[k].get("ce", {}).get("implied_volatility", 0) or 0)/100 for k in oc.keys()])
                pe_iv = np.array([float(oc[k].get("pe", {}).get("implied_volatility", 0) or 0)/100 for k in oc.keys()])
                ce_delta = np.array([float(oc[k].get("ce", {}).get("greeks", {}).get("delta", 0) or 0) for k in oc.keys()])
                pe_delta = np.array([float(oc[k].get("pe", {}).get("greeks", {}).get("delta", 0) or 0) for k in oc.keys()])
                ce_gamma_api = np.array([float(oc[k].get("ce", {}).get("greeks", {}).get("gamma", 0) or 0) for k in oc.keys()])
                pe_gamma_api = np.array([float(oc[k].get("pe", {}).get("greeks", {}).get("gamma", 0) or 0) for k in oc.keys()])
                
                ce_gamma_bs, ce_vanna, ce_charm, ce_speed, ce_vomma = MathEngine.calculate_bs_greeks(spot, strikes, T, np.maximum(ce_iv, 0.15))
                pe_gamma_bs, pe_vanna, pe_charm, pe_speed, pe_vomma = MathEngine.calculate_bs_greeks(spot, strikes, T, np.maximum(pe_iv, 0.15))
                
                ce_gamma = np.where(ce_gamma_api > 0, ce_gamma_api, ce_gamma_bs)
                pe_gamma = np.where(pe_gamma_api > 0, pe_gamma_api, pe_gamma_bs)
                
                # Dollarized GEX (FlashAlpha style: dollars per 1% spot move)
                gex_scale = (spot ** 2) * 0.01 * Config.NIFTY_LOT_SIZE / 1e5
                call_gex = ce_oi * ce_gamma * gex_scale
                put_gex = -pe_oi * pe_gamma * gex_scale
                net_gex = call_gex + put_gex
                abs_gex = call_gex + np.abs(put_gex)
                
                ce_dex = ce_oi * ce_delta * spot * Config.NIFTY_LOT_SIZE / 1e5
                pe_dex = pe_oi * pe_delta * spot * Config.NIFTY_LOT_SIZE / 1e5
                net_dex = ce_dex + pe_dex
                
                df = pd.DataFrame({
                    "Strike": strikes, "CE_LTP": ce_ltp, "PE_LTP": pe_ltp, "CE_OI": ce_oi, "PE_OI": pe_oi,
                    "CE_Vol": ce_vol, "PE_Vol": pe_vol, "CE_Delta": ce_delta, "PE_Delta": pe_delta,
                    "Call_GEX": call_gex, "Put_GEX": put_gex, "Net_GEX": net_gex, "ABS_GEX": abs_gex,
                    "Net_DEX": net_dex, "Net_VEX": ((ce_oi * ce_vanna) - (pe_oi * pe_vanna)) * Config.NIFTY_LOT_SIZE / 1e3,
                    "Net_CHEX": ((ce_oi * ce_charm) - (pe_oi * pe_charm)) * Config.NIFTY_LOT_SIZE / 1e3,
                    "Net_SPEX": ((ce_oi * ce_speed) - (pe_oi * pe_speed)) * Config.NIFTY_LOT_SIZE / 1e3,
                    "Net_VOMMA": ((ce_oi * ce_vomma) - (pe_oi * pe_vomma)) * Config.NIFTY_LOT_SIZE / 1e3,
                    "CE_IV": ce_iv * 100.0, "PE_IV": pe_iv * 100.0, "IV_Spread": (ce_iv - pe_iv) * 100.0,
                })
                return df.sort_values("Strike").reset_index(drop=True), spot, None
            else:
                return None, 0.0, str(data.get("remarks") or f"HTTP {res.status_code}")
        except Exception as e:
            time.sleep(1)
    return None, 0.0, "Connection Error"

@st.cache_resource
def start_websocket(client_id, access_token):
    ws_data = {"NIFTY_FUT_LTP": 0.0, "CVD": 0.0, "CONNECTED": False, "ERROR": None}
    if not DHAN_WS_AVAILABLE:
        ws_data["ERROR"] = "dhanhq not installed"
        return ws_data
    
    instruments = [(1, "2885"), (1, "1333"), (1, "4963"), (2, "58756")]
    def on_connect(i): ws_data["CONNECTED"] = True
    def on_disconnect(i): ws_data["CONNECTED"] = False
    def on_message(instance, msg):
        if isinstance(msg, dict):
            sec_id, ltp, ltq = str(msg.get('security_id', '')), float(msg.get('LTP', 0.0)), float(msg.get('last_trade_quantity', 0.0))
            if ltp > 0:
                if sec_id == "58756": ws_data["NIFTY_FUT_LTP"] = ltp
                elif sec_id in ["2885", "1333", "4963"]:
                    sym = "RELIANCE" if sec_id == "2885" else "HDFCBANK" if sec_id == "1333" else "ICICIBANK"
                    prev = ws_data.get(f"{sym}_PREV", 0.0)
                    if prev > 0: ws_data["CVD"] += ltq if ltp > prev else -ltq if ltp < prev else 0
                    ws_data[f"{sym}_PREV"] = ltp
    threading.Thread(target=lambda: marketfeed.DhanFeed(client_id, access_token, instruments, 15, on_connect=on_connect, on_message=on_message).run_forever(), daemon=True).start()
    return ws_data

# ---------------------------------------------------------
# 5. MAIN APPLICATION
# ---------------------------------------------------------
def main():
    st.sidebar.title("⚙️ Command Center")
    auto_refresh = st.sidebar.checkbox("🔄 Live Auto-Refresh (5s)", value=True)
    if auto_refresh: st_autorefresh(interval=5000, key="refresh")
    
    IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    now_ist = datetime.datetime.now(IST)
    today_str = now_ist.strftime("%Y-%m-%d")
    now_time = now_ist.strftime("%H:%M:%S")
    is_live = now_ist.weekday() < 5 and (now_ist.replace(hour=9, minute=15) <= now_ist <= now_ist.replace(hour=15, minute=30))
    
    expiries = fetch_expiry_list()
    selected_expiry = st.sidebar.selectbox("📅 Primary Expiry", expiries) if expiries else today_str
    is_0dte = (selected_expiry == today_str)
    
    with st.spinner("Fetching institutional data..."):
        df_oc, spot, err = fetch_option_chain(selected_expiry)
    if err: st.error(f"⚠️ **Error:** {err}"); st.stop()
    
    # Core Analytics
    synth = spot
    atm_approx = int(round(spot / 50) * 50)
    row = df_oc[df_oc["Strike"] == atm_approx]
    if not row.empty: synth = atm_approx + row["CE_LTP"].values[0] - row["PE_LTP"].values[0]
    atm_strike = int(round(synth / 50) * 50)
    
    max_pain = MathEngine.calculate_max_pain(df_oc["Strike"].values, df_oc["CE_OI"].values, df_oc["PE_OI"].values)
    
    df_sorted = df_oc.sort_values("Strike").copy()
    df_sorted["Cum_GEX"] = df_sorted["Net_GEX"].cumsum()
    gamma_flip = int(spot)
    for i in range(1, len(df_sorted)):
        p, c = df_sorted.iloc[i-1]["Cum_GEX"], df_sorted.iloc[i]["Cum_GEX"]
        if (p < 0 and c >= 0) or (p > 0 and c <= 0):
            gamma_flip = int((df_sorted.iloc[i-1]["Strike"] + df_sorted.iloc[i]["Strike"]) / 2)
            break
    
    df_f = df_oc[(df_oc["Strike"] >= atm_strike - Config.STRIKE_RANGE_ATM) & (df_oc["Strike"] <= atm_strike + Config.STRIKE_RANGE_ATM)].copy()
    strike_labels = df_f["Strike"].astype(str).tolist()
    
    total_net_gex = df_oc["Net_GEX"].sum()
    total_ce_oi, total_pe_oi = df_oc["CE_OI"].sum(), df_oc["PE_OI"].sum()
    total_ce_vol, total_pe_vol = df_oc["CE_Vol"].sum(), df_oc["PE_Vol"].sum()
    current_pcr = total_pe_oi / total_ce_oi if total_ce_oi > 0 else 0.0
    vol_pcr = total_pe_vol / total_ce_vol if total_ce_vol > 0 else 0.0
    
    call_wall_gex = df_f.loc[df_f['Net_GEX'].idxmax()]['Strike'] if not df_f.empty else atm_strike
    put_wall_gex = df_f.loc[df_f['Net_GEX'].idxmin()]['Strike'] if not df_f.empty else atm_strike
    
    # FlashAlpha Metrics
    atm_row = df_oc[df_oc["Strike"] == atm_strike]
    atm_iv = ((atm_row["CE_IV"].values[0] if not atm_row.empty else 0) + (atm_row["PE_IV"].values[0] if not atm_row.empty else 0)) / 2.0
    vrp = atm_iv - Config.ASSUMED_HV_20D
    implied_move_pct = atm_iv / 100 * math.sqrt(1 / 252) * 100
    upside_resistance = spot * (1 + implied_move_pct/100)
    downside_support = spot * (1 - implied_move_pct/100)
    
    # Aggregate Exposures
    total_put_theta = df_oc[df_oc["Strike"] >= atm_strike - 300]["PE_LTP"].sum() * -0.05
    total_call_theta = df_oc[df_oc["Strike"] <= atm_strike + 300]["CE_LTP"].sum() * -0.05
    total_put_vega = (df_oc["PE_OI"] * df_oc["PE_IV"] * 0.01 * Config.NIFTY_LOT_SIZE).sum() / 1e6
    total_call_vega = (df_oc["CE_OI"] * df_oc["CE_IV"] * 0.01 * Config.NIFTY_LOT_SIZE).sum() / 1e6
    total_put_gex = df_oc[df_oc["Strike"] <= spot]["Put_GEX"].sum()
    total_call_gex = df_oc[df_oc["Strike"] >= spot]["Call_GEX"].sum()
    total_put_vex = (df_oc["PE_OI"] * df_oc["PE_IV"] * 0.1 * Config.NIFTY_LOT_SIZE).sum() / 1e4
    total_call_vex = (df_oc["CE_OI"] * df_oc["CE_IV"] * 0.1 * Config.NIFTY_LOT_SIZE).sum() / 1e4
    
    # Intraday Interpretations
    if current_pcr > 1.2: pcr_signal = "🟢 BULLISH: Strong put writing indicates support building"
    elif current_pcr < 0.8: pcr_signal = "🔴 BEARISH: Heavy call writing suggests resistance"
    else: pcr_signal = "🟡 NEUTRAL: Balanced positioning"
    
    if total_call_gex > abs(total_put_gex) * 1.2: gex_signal = "🟢 CALL DOMINANCE: Dealers short gamma above spot → upside acceleration risk"
    elif abs(total_put_gex) > total_call_gex * 1.2: gex_signal = "🔴 PUT DOMINANCE: Dealers short gamma below spot → downside acceleration risk"
    else: gex_signal = "🟡 BALANCED GEX: Mean-reverting conditions likely"
    
    if total_put_vega > total_call_vega * 1.1: vega_signal = "🟢 LONG VEGA BIAS: Market positioned for vol expansion (fear hedge)"
    elif total_call_vega > total_put_vega * 1.1: vega_signal = "🔴 SHORT VEGA BIAS: Market complacent, vol crush risk"
    else: vega_signal = "⚪ NEUTRAL VEGA: Balanced vol exposure"
    
    narrative = generate_nifty_narrative(spot, total_net_gex, gamma_flip, call_wall_gex, put_wall_gex, max_pain, atm_iv, vrp, "NORMAL", is_0dte, pcr_signal, gex_signal, vega_signal, downside_support, upside_resistance, implied_move_pct)
    
    ws_data = start_websocket(CLIENT_ID, ACCESS_TOKEN)
    nifty_fut = ws_data.get("NIFTY_FUT_LTP", 0.0)
    basis = nifty_fut - spot if nifty_fut > 0 else 0.0
    
    # HEADER
    st.markdown("### 🏛️ PRINCE PAX | FLASHALPHA NIFTY TERMINAL")
    status_cls = "status-live" if is_live else "status-closed"
    st.markdown(f'<div class="status-badge {status_cls}">{"🟢 LIVE MARKET" if is_live else "🟠 MARKET CLOSED"} | Expiry: {selected_expiry} | IST: {now_time} | Lot: {Config.NIFTY_LOT_SIZE}</div>', unsafe_allow_html=True)
    
    st.markdown(f'<div class="narrative-box">📖 <strong>Market Narrative:</strong><br>{narrative}</div>', unsafe_allow_html=True)
    
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📊 Command & Intraday", "🧱 Dealer Exposure (GEX/DEX)", "🌊 Advanced Greeks (VEX/CHEX)",
        "📈 Volatility & VRP", "🎯 Zero-DTE & Max Pain", "📋 Data Grid"
    ])
    
    # TAB 1: COMMAND CENTER & INTRADAY ANALYTICS
    with tab1:
        # Row 1: Core Metrics
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        with c1:
            st.markdown(f"""<div class="metric-card metric-card-amber">
                <div class="metric-title">NIFTY SYNTH FUT</div>
                <div class="metric-value">₹{synth:,.2f}</div>
                <div class="metric-sub sub-amber">Spot: ₹{spot:,.2f} | Basis: {basis:+.2f}</div>
            </div>""", unsafe_allow_html=True)
        with c2:
            st.markdown(f"""<div class="metric-card metric-card-purple">
                <div class="metric-title">ATM IV & VRP</div>
                <div class="metric-value">{atm_iv:.1f}%</div>
                <div class="metric-sub {'sub-green' if vrp > 0 else 'sub-red'}">VRP: {vrp:+.1f}% vs {Config.ASSUMED_HV_20D}% HV</div>
            </div>""", unsafe_allow_html=True)
        with c3:
            st.markdown(f"""<div class="metric-card metric-card-cyan">
                <div class="metric-title">EXPECTED MOVE (1D)</div>
                <div class="metric-value">±{implied_move_pct:.2f}%</div>
                <div class="metric-sub sub-cyan">Range: {downside_support:.0f}-{upside_resistance:.0f}</div>
            </div>""", unsafe_allow_html=True)
        with c4:
            st.markdown(f"""<div class="metric-card {'metric-card-green' if total_net_gex >= 0 else 'metric-card-red'}">
                <div class="metric-title">NET GEX (₹L)</div>
                <div class="metric-value">{total_net_gex/1e5:+,.1f}</div>
                <div class="metric-sub sub-{'green' if total_net_gex >= 0 else 'red'}">{'Long Gamma' if total_net_gex >= 0 else 'Short Gamma'}</div>
            </div>""", unsafe_allow_html=True)
        with c5:
            st.markdown(f"""<div class="metric-card metric-card-amber">
                <div class="metric-title">PCR (OI)</div>
                <div class="metric-value">{current_pcr:.2f}</div>
                <div class="metric-sub sub-amber">Vol PCR: {vol_pcr:.2f}</div>
            </div>""", unsafe_allow_html=True)
        with c6:
            st.markdown(f"""<div class="metric-card metric-card-cyan">
                <div class="metric-title">FUTURES BASIS</div>
                <div class="metric-value">{basis:+.2f}</div>
                <div class="metric-sub sub-cyan">Fut: ₹{nifty_fut:,.1f}</div>
            </div>""", unsafe_allow_html=True)
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Row 2: Key Levels
        l1, l2, l3, l4 = st.columns(4)
        with l1: st.markdown(f"""<div class="metric-card metric-card-purple"><div class="metric-title">GAMMA FLIP</div><div class="metric-value">₹{gamma_flip:,.0f}</div><div class="metric-sub sub-purple">Zero-Crossing</div></div>""", unsafe_allow_html=True)
        with l2: st.markdown(f"""<div class="metric-card metric-card-green"><div class="metric-title">CALL WALL</div><div class="metric-value">₹{call_wall_gex:,.0f}</div><div class="metric-sub sub-green">Resistance</div></div>""", unsafe_allow_html=True)
        with l3: st.markdown(f"""<div class="metric-card metric-card-red"><div class="metric-title">PUT WALL</div><div class="metric-value">₹{put_wall_gex:,.0f}</div><div class="metric-sub sub-red">Support</div></div>""", unsafe_allow_html=True)
        with l4: st.markdown(f"""<div class="metric-card metric-card-amber"><div class="metric-title">MAX PAIN</div><div class="metric-value">₹{max_pain:,.0f}</div><div class="metric-sub sub-amber">Expiry Magnet</div></div>""", unsafe_allow_html=True)
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Row 3: Aggregate Exposure Metrics (FlashAlpha Style)
        st.markdown("### 📊 Aggregate Option Chain Exposures")
        e1, e2, e3, e4, e5, e6, e7 = st.columns(7)
        
        with e1:
            st.markdown(f"""<div class="metric-card" style="border-top-color: #48BB78;">
                <div class="metric-title">PUT OI</div>
                <div class="metric-value" style="color: #48BB78;">{total_pe_oi/1e6:.1f}M</div>
                <div class="metric-sub">Call OI: {total_ce_oi/1e6:.1f}M</div>
            </div>""", unsafe_allow_html=True)
        
        with e2:
            st.markdown(f"""<div class="metric-card" style="border-top-color: #63B3ED;">
                <div class="metric-title">VOLUME</div>
                <div class="metric-value" style="color: #F56565;">C:{total_ce_vol/1e6:.1f}M</div>
                <div class="metric-sub">P:{total_pe_vol/1e6:.1f}M</div>
            </div>""", unsafe_allow_html=True)
        
        with e3:
            st.markdown(f"""<div class="metric-card" style="border-top-color: #ECC94B;">
                <div class="metric-title">THETA</div>
                <div class="metric-value" style="color: #F56565;">{total_call_theta+total_put_theta:-,.0f}</div>
                <div class="metric-sub">Daily Decay (₹)</div>
            </div>""", unsafe_allow_html=True)
        
        with e4:
            st.markdown(f"""<div class="metric-card" style="border-top-color: #9F7AEA;">
                <div class="metric-title">VEGA</div>
                <div class="metric-value" style="color: #48BB78;">P:{total_put_vega:.0f}</div>
                <div class="metric-sub">C:{total_call_vega:.0f}</div>
            </div>""", unsafe_allow_html=True)
        
        with e5:
            st.markdown(f"""<div class="metric-card" style="border-top-color: #0BC5EA;">
                <div class="metric-title">GEX</div>
                <div class="metric-value" style="color: {'#48BB78' if total_call_gex > abs(total_put_gex) else '#F56565'};">C:{total_call_gex/1e5:.0f}</div>
                <div class="metric-sub">P:{total_put_gex/1e5:.0f}</div>
            </div>""", unsafe_allow_html=True)
        
        with e6:
            st.markdown(f"""<div class="metric-card" style="border-top-color: #AB47BC;">
                <div class="metric-title">VEX</div>
                <div class="metric-value" style="color: #48BB78;">P:{total_put_vex:.0f}</div>
                <div class="metric-sub">C:{total_call_vex:.0f}</div>
            </div>""", unsafe_allow_html=True)

        with e7:
            st.markdown(f"""<div class="metric-card" style="border-top-color: #F56565;">
                <div class="metric-title">SPEX</div>
                <div class="metric-value" style="color: #F56565;">{df_f['Net_SPEX'].sum()/1e3:+.1f}</div>
                <div class="metric-sub">Acceleration Risk</div>
            </div>""", unsafe_allow_html=True)
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Row 4: Open Interest Charts
        r1c1, r1c2 = st.columns(2)
        
        with r1c1:
            st.markdown('<div class="chart-container"><div class="chart-title">Open Interest Distribution <div class="info-tooltip">ⓘ<span class="tooltip-text">Green = Put OI, Red = Call OI. Higher bars indicate stronger support/resistance levels.</span></div></div>', unsafe_allow_html=True)
            fig_oi = go.Figure()
            fig_oi.add_trace(go.Bar(x=df_f["Strike"], y=df_f["PE_OI"]/1e6, name="Put OI", marker_color="#48BB78", opacity=0.7))
            fig_oi.add_trace(go.Bar(x=df_f["Strike"], y=df_f["CE_OI"]/1e6, name="Call OI", marker_color="#F56565", opacity=0.7))
            fig_oi.add_vline(x=spot, line_dash="solid", line_color="#ECC94B", line_width=2, annotation_text="Spot")
            fig_oi.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0,r=0,t=10,b=0), height=300, barmode="group", legend=dict(orientation="h", y=1.12), xaxis=dict(tickmode='array', tickvals=df_f["Strike"], ticktext=strike_labels, tickangle=-45), yaxis_title="Open Interest (Millions)")
            st.plotly_chart(fig_oi, use_container_width=True, key="oi_dist")
            st.markdown('</div>', unsafe_allow_html=True)
        
        with r1c2:
            st.markdown('<div class="chart-container"><div class="chart-title">Intraday Volume Flow <div class="info-tooltip">ⓘ<span class="tooltip-text">Real-time volume distribution. High volume at specific strikes indicates active positioning or hedging.</span></div></div>', unsafe_allow_html=True)
            fig_vol = go.Figure()
            fig_vol.add_trace(go.Bar(x=df_f["Strike"], y=df_f["PE_Vol"]/1e6, name="Put Vol", marker_color="#48BB78", opacity=0.7))
            fig_vol.add_trace(go.Bar(x=df_f["Strike"], y=df_f["CE_Vol"]/1e6, name="Call Vol", marker_color="#F56565", opacity=0.7))
            fig_vol.add_vline(x=spot, line_dash="solid", line_color="#ECC94B", line_width=2)
            fig_vol.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0,r=0,t=10,b=0), height=300, barmode="group", legend=dict(orientation="h", y=1.12), xaxis=dict(tickmode='array', tickvals=df_f["Strike"], ticktext=strike_labels, tickangle=-45), yaxis_title="Volume (Millions)")
            st.plotly_chart(fig_vol, use_container_width=True, key="vol_flow")
            st.markdown('</div>', unsafe_allow_html=True)
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Row 5: Intraday Signals & Interpretations
        st.markdown("### 🎯 Intraday Movement Signals")
        s1, s2, s3 = st.columns(3)
        
        with s1:
            signal_color = "sub-green" if current_pcr > 1 else "sub-red" if current_pcr < 0.9 else "sub-amber"
            st.markdown(f"""<div class="metric-card metric-card-{'green' if current_pcr > 1 else 'red' if current_pcr < 0.9 else 'amber'}">
                <div class="metric-title">PCR SIGNAL</div>
                <div class="metric-value">{current_pcr:.2f}</div>
                <div class="metric-sub {signal_color}">{pcr_signal.split(':')[0]}</div>
            </div>""", unsafe_allow_html=True)
        
        with s2:
            gex_color = "sub-green" if total_call_gex > abs(total_put_gex) else "sub-red"
            st.markdown(f"""<div class="metric-card metric-card-{'green' if total_call_gex > abs(total_put_gex) else 'red'}">
                <div class="metric-title">GEX BIAS</div>
                <div class="metric-value">{total_call_gex/abs(total_put_gex) if total_put_gex != 0 else 1:.2f}x</div>
                <div class="metric-sub {gex_color}">{gex_signal.split(':')[0]}</div>
            </div>""", unsafe_allow_html=True)
        
        with s3:
            vega_color = "sub-green" if total_put_vega > total_call_vega else "sub-red"
            st.markdown(f"""<div class="metric-card metric-card-{'green' if total_put_vega > total_call_vega else 'red'}">
                <div class="metric-title">VEGA BIAS</div>
                <div class="metric-value">{total_put_vega/total_call_vega if total_call_vega != 0 else 1:.2f}x</div>
                <div class="metric-sub {vega_color}">{vega_signal.split(':')[0]}</div>
            </div>""", unsafe_allow_html=True)
        
        # Detailed Interpretations
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(f"""
        <div class="narrative-box">
            <strong>📊 Intraday Interpretation:</strong><br>
            • <strong>PCR Analysis:</strong> {pcr_signal}. {'Put writers are aggressive, creating support.' if current_pcr > 1.1 else 'Call writers dominate, capping upside.' if current_pcr < 0.9 else 'Balanced positioning suggests range-bound trade.'}<br>
            • <strong>GEX Dynamics:</strong> {gex_signal}. {'Expect accelerated moves if spot breaks key levels.' if abs(total_call_gex) - abs(total_put_gex) > abs(total_put_gex) * 0.3 else 'Dealer hedging will dampen volatility.'}<br>
            • <strong>Vega Positioning:</strong> {vega_signal}. {'Market is hedged for vol expansion (fear).' if total_put_vega > total_call_vega * 1.1 else 'Complacent positioning risks vol crush.'}<br>
            • <strong>Theta Decay:</strong> ₹{abs(total_call_theta + total_put_theta):,.0f} daily time decay across chain. {'Accelerating into close.' if is_0dte else 'Moderate decay rate.'}<br>
            • <strong>Intraday Range:</strong> High-probability range: <strong>{downside_support:.0f} - {upside_resistance:.0f}</strong>. Breakouts beyond this range require volume confirmation.
        </div>
        """, unsafe_allow_html=True)

    # TAB 2: DEALER EXPOSURE (GEX/DEX)
    with tab2:
        r1c1, r1c2 = st.columns(2)
        with r1c1:
            st.markdown('<div class="chart-container"><div class="chart-title">Net Dollarized GEX (₹ Lakhs per 1% Move)</div>', unsafe_allow_html=True)
            fig_gex = go.Figure()
            colors = ["#48BB78" if g >= 0 else "#F56565" for g in df_f["Net_GEX"]]
            fig_gex.add_trace(go.Bar(x=df_f["Strike"], y=df_f["Net_GEX"]/1e5, marker_color=colors, name="Net GEX", opacity=0.8))
            fig_gex.add_trace(go.Scatter(x=df_f["Strike"], y=df_f["ABS_GEX"]/1e5, mode="lines", name="|GEX|", line=dict(color="#63B3ED", width=2)))
            fig_gex.add_vline(x=spot, line_dash="solid", line_color="#ECC94B", annotation_text="Spot")
            fig_gex.add_vline(x=gamma_flip, line_dash="dash", line_color="#9F7AEA", annotation_text="Flip")
            fig_gex.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0,r=0,t=10,b=0), height=350, xaxis=dict(tickmode='array', tickvals=df_f["Strike"], ticktext=strike_labels, tickangle=-45))
            st.plotly_chart(fig_gex, use_container_width=True, key="gex")
            st.markdown('</div>', unsafe_allow_html=True)
        
        with r1c2:
            st.markdown('<div class="chart-container"><div class="chart-title">Net Dollarized DEX (₹ Lakhs)</div>', unsafe_allow_html=True)
            fig_dex = go.Figure()
            colors = ["#48BB78" if v >= 0 else "#F56565" for v in df_f["Net_DEX"]]
            fig_dex.add_trace(go.Bar(x=df_f["Strike"], y=df_f["Net_DEX"]/1e5, marker_color=colors, name="Net DEX", opacity=0.8))
            fig_dex.add_vline(x=spot, line_dash="solid", line_color="#ECC94B", annotation_text="Spot")
            fig_dex.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0,r=0,t=10,b=0), height=350, xaxis=dict(tickmode='array', tickvals=df_f["Strike"], ticktext=strike_labels, tickangle=-45))
            st.plotly_chart(fig_dex, use_container_width=True, key="dex")
            st.markdown('</div>', unsafe_allow_html=True)
        
        st.markdown('<div class="chart-container"><div class="chart-title">FlashAlpha Hedging Scenarios (±1% Spot Move)</div>', unsafe_allow_html=True)
        h1, h2, h3 = st.columns(3)
        with h1: st.markdown(f"""<div style="text-align:center;"><div style="color:#A0AEC0;font-size:0.8rem;">SPOT +1% MOVE</div><div style="font-size:1.5rem;font-weight:800;color:#F56565;">{total_net_gex * 0.01 / 1e5:+,.1f}L</div><div style="font-size:0.75rem;color:#A0AEC0;">Est. Dealer Selling</div></div>""", unsafe_allow_html=True)
        with h2: st.markdown(f"""<div style="text-align:center;"><div style="color:#A0AEC0;font-size:0.8rem;">CURRENT NET GEX</div><div style="font-size:1.5rem;font-weight:800;color:#63B3ED;">{total_net_gex/1e5:+,.1f}L</div><div style="font-size:0.75rem;color:#A0AEC0;">Total Chain Exposure</div></div>""", unsafe_allow_html=True)
        with h3: st.markdown(f"""<div style="text-align:center;"><div style="color:#A0AEC0;font-size:0.8rem;">SPOT -1% MOVE</div><div style="font-size:1.5rem;font-weight:800;color:#48BB78;">{-total_net_gex * 0.01 / 1e5:+,.1f}L</div><div style="font-size:0.75rem;color:#A0AEC0;">Est. Dealer Buying</div></div>""", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # TAB 3: ADVANCED GREEKS (VEX/CHEX)
    with tab3:
        r1c1, r1c2 = st.columns(2)
        vex_interp = "Dealers are long vanna — falling IV likely supports spot." if df_f["Net_VEX"].sum() > 0 else "Dealers are short vanna — rising IV will pressure spot."
        chex_interp = "Dealer delta drifts short as the day decays — supports a fade." if df_f["Net_CHEX"].sum() < 0 else "Dealer delta drifts long into the close — supports a rally."
        
        with r1c1:
            st.markdown(f'<div class="chart-container"><div class="chart-title">Vanna Exposure (VEX) <div class="info-tooltip">ⓘ<span class="tooltip-text">{vex_interp}</span></div></div>', unsafe_allow_html=True)
            fig_vex = go.Figure()
            fig_vex.add_trace(go.Scatter(x=df_f["Strike"], y=df_f["Net_VEX"], mode="lines+markers", line=dict(color="#FFA726", width=2.5)))
            fig_vex.add_hline(y=0, line_dash="dash", line_color="white", opacity=0.3)
            fig_vex.add_vline(x=spot, line_dash="solid", line_color="#ECC94B")
            fig_vex.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0,r=0,t=10,b=0), height=300, xaxis=dict(tickmode='array', tickvals=df_f["Strike"], ticktext=strike_labels, tickangle=-45))
            st.plotly_chart(fig_vex, use_container_width=True, key="vex")
            st.markdown('</div>', unsafe_allow_html=True)
        
        with r1c2:
            st.markdown(f'<div class="chart-container"><div class="chart-title">Charm Exposure (CHEX) <div class="info-tooltip">ⓘ<span class="tooltip-text">{chex_interp}</span></div></div>', unsafe_allow_html=True)
            fig_chex = go.Figure()
            fig_chex.add_trace(go.Scatter(x=df_f["Strike"], y=df_f["Net_CHEX"], mode="lines+markers", line=dict(color="#9F7AEA", width=2.5)))
            fig_chex.add_hline(y=0, line_dash="dash", line_color="white", opacity=0.3)
            fig_chex.add_vline(x=spot, line_dash="solid", line_color="#ECC94B")
            fig_chex.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0,r=0,t=10,b=0), height=300, xaxis=dict(tickmode='array', tickvals=df_f["Strike"], ticktext=strike_labels, tickangle=-45))
            st.plotly_chart(fig_chex, use_container_width=True, key="chex")
            st.markdown('</div>', unsafe_allow_html=True)

    # TAB 4: VOLATILITY & VRP
    with tab4:
        r1c1, r1c2 = st.columns(2)
        with r1c1:
            st.markdown('<div class="chart-container"><div class="chart-title">IV Smile (Volatility Skew)</div>', unsafe_allow_html=True)
            fig_smile = go.Figure()
            fig_smile.add_trace(go.Scatter(x=df_f["Strike"], y=df_f["CE_IV"], mode="lines+markers", name="Call IV", line=dict(color="#48BB78", width=2)))
            fig_smile.add_trace(go.Scatter(x=df_f["Strike"], y=df_f["PE_IV"], mode="lines+markers", name="Put IV", line=dict(color="#F56565", width=2)))
            fig_smile.add_vline(x=spot, line_dash="solid", line_color="#ECC94B")
            fig_smile.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0,r=0,t=10,b=0), height=350, xaxis=dict(tickmode='array', tickvals=df_f["Strike"], ticktext=strike_labels, tickangle=-45))
            st.plotly_chart(fig_smile, use_container_width=True, key="smile")
            st.markdown('</div>', unsafe_allow_html=True)
        
        with r1c2:
            st.markdown('<div class="chart-container"><div class="chart-title">IV Spread by Strike (Call - Put)</div>', unsafe_allow_html=True)
            fig_spread = go.Figure()
            colors = ["#48BB78" if v >= 0 else "#F56565" for v in df_f["IV_Spread"]]
            fig_spread.add_trace(go.Bar(x=df_f["Strike"], y=df_f["IV_Spread"], marker_color=colors))
            fig_spread.add_hline(y=0, line_dash="dash", line_color="white", opacity=0.3)
            fig_spread.add_vline(x=spot, line_dash="solid", line_color="#ECC94B")
            fig_spread.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0,r=0,t=10,b=0), height=350, xaxis=dict(tickmode='array', tickvals=df_f["Strike"], ticktext=strike_labels, tickangle=-45))
            st.plotly_chart(fig_spread, use_container_width=True, key="spread")
            st.markdown('</div>', unsafe_allow_html=True)
        
        st.markdown('<div class="chart-container"><div class="chart-title">Variance Risk Premium (VRP) Analytics</div>', unsafe_allow_html=True)
        v1, v2, v3, v4 = st.columns(4)
        with v1: st.markdown(f"""<div style="text-align:center;"><div style="color:#A0AEC0;font-size:0.8rem;">ATM IMPLIED VOL</div><div style="font-size:1.4rem;font-weight:800;">{atm_iv:.2f}%</div></div>""", unsafe_allow_html=True)
        with v2: st.markdown(f"""<div style="text-align:center;"><div style="color:#A0AEC0;font-size:0.8rem;">ASSUMED 20D HV</div><div style="font-size:1.4rem;font-weight:800;">{Config.ASSUMED_HV_20D:.2f}%</div></div>""", unsafe_allow_html=True)
        with v3: st.markdown(f"""<div style="text-align:center;"><div style="color:#A0AEC0;font-size:0.8rem;">VRP (IV - HV)</div><div style="font-size:1.4rem;font-weight:800;color:{'#48BB78' if vrp > 0 else '#F56565'};">{vrp:+.2f}%</div></div>""", unsafe_allow_html=True)
        with v4: 
            harvest_score = min(100, max(0, int(50 + vrp * 10)))
            st.markdown(f"""<div style="text-align:center;"><div style="color:#A0AEC0;font-size:0.8rem;">HARVEST SCORE</div><div style="font-size:1.4rem;font-weight:800;color:#9F7AEA;">{harvest_score}/100</div></div>""", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # TAB 5: ZERO-DTE & MAX PAIN
    with tab5:
        if is_0dte:
            st.markdown(f'<div class="narrative-box" style="border-left-color: #F56565;">🚨 <strong>ZERO-DTE EXPIRY DAY:</strong> Pin risk and dealer hedging flows are maximized. Time to close dictates decay acceleration.</div>', unsafe_allow_html=True)
            time_to_close = max(0, (now_ist.replace(hour=15, minute=30) - now_ist).total_seconds() / 3600)
            pct_closed = 1.0 - (time_to_close / 6.25)
            
            z1, z2, z3 = st.columns(3)
            with z1: st.markdown(f"""<div class="metric-card metric-card-red"><div class="metric-title">TIME TO CLOSE</div><div class="metric-value">{time_to_close:.1f}h</div><div class="metric-sub sub-red">{pct_closed*100:.0f}% Session Elapsed</div></div>""", unsafe_allow_html=True)
            with z2: st.markdown(f"""<div class="metric-card metric-card-purple"><div class="metric-title">PIN MAGNET</div><div class="metric-value">₹{max_pain:,.0f}</div><div class="metric-sub sub-purple">Distance: {abs(spot-max_pain):.1f} pts</div></div>""", unsafe_allow_html=True)
            with z3: st.markdown(f"""<div class="metric-card metric-card-amber"><div class="metric-title">0DTE GEX SHARE</div><div class="metric-value">~18%</div><div class="metric-sub sub-amber">Of Total Chain</div></div>""", unsafe_allow_html=True)
        else:
            st.info(f"Selected expiry ({selected_expiry}) is not today. Zero-DTE metrics are inactive.")
        
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown('<div class="chart-container"><div class="chart-title">Max Pain Pinning Profile</div>', unsafe_allow_html=True)
        pain_strikes = df_oc["Strike"].values
        pain_curve = [np.sum(df_oc["CE_OI"].values * np.maximum(k - pain_strikes, 0)) + np.sum(df_oc["PE_OI"].values * np.maximum(pain_strikes - k, 0)) for k in pain_strikes]
        fig_pain = go.Figure()
        fig_pain.add_trace(go.Scatter(x=pain_strikes, y=pain_curve, mode="lines", fill="tozeroy", line=dict(color="#A0AEC0", width=1.5), fillcolor="rgba(160, 174, 192, 0.15)"))
        fig_pain.add_vline(x=spot, line_dash="solid", line_color="#ECC94B", annotation_text=f"Spot {spot:.0f}")
        fig_pain.add_vline(x=max_pain, line_dash="dash", line_color="#9F7AEA", line_width=2, annotation_text=f"Max Pain {max_pain}")
        fig_pain.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=0,r=0,t=10,b=0), height=300, showlegend=False)
        st.plotly_chart(fig_pain, use_container_width=True, key="pain")
        st.markdown('</div>', unsafe_allow_html=True)

    # TAB 6: DATA GRID
    with tab6:
        st.markdown("### 📋 Institutional Options Chain (FlashAlpha Schema)")
        grid = df_f[[
            "Strike", "CE_LTP", "PE_LTP", "CE_OI", "PE_OI", "CE_Vol", "PE_Vol",
            "Call_GEX", "Put_GEX", "Net_GEX", "Net_DEX", "Net_VEX", "Net_CHEX", "Net_SPEX",
            "CE_IV", "PE_IV", "IV_Spread"
        ]].copy()
        
        st.dataframe(
            grid.style.format({
                "Strike": "{:.0f}", "CE_LTP": "₹{:.2f}", "PE_LTP": "₹{:.2f}",
                "CE_OI": "{:,.0f}", "PE_OI": "{:,.0f}", "CE_Vol": "{:,.0f}", "PE_Vol": "{:,.0f}",
                "Call_GEX": "{:+,.1f}", "Put_GEX": "{:+,.1f}", "Net_GEX": "{:+,.1f}",
                "Net_DEX": "{:+,.1f}", "Net_VEX": "{:+,.2f}", "Net_CHEX": "{:+,.2f}", "Net_SPEX": "{:+,.2f}",
                "CE_IV": "{:.1f}%", "PE_IV": "{:.1f}%", "IV_Spread": "{:+.2f}%"
            }),
            use_container_width=True, height=500, hide_index=True
        )

    st.markdown("<br><hr style='border-color: rgba(99, 179, 237, 0.2);'>", unsafe_allow_html=True)
    st.markdown("<div style='text-align:center;color:#A0AEC0;font-size:0.72rem;'>Prince PAX Terminal v4.0 | FlashAlpha Methodology | NIFTY Lot: 65 | Dividend-Adjusted Greeks</div>", unsafe_allow_html=True)

if __name__ == "__main__":
    main()
