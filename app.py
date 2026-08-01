import datetime
import time
import os
import threading
import logging
import math
import json
from typing import Dict, List, Tuple, Optional, Any
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from scipy import stats, interpolate

# Configure professional logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler('dashboard.log'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------
# 1. CONFIGURATION & CONSTANTS (NIFTY 2026)
# ---------------------------------------------------------
class Config:
    NIFTY_LOT_SIZE = 25
    RISK_FREE_RATE = 0.065  # Current RBI repo rate
    NIFTY_DIVIDEND_YIELD = 0.012  # Average dividend yield
    API_TIMEOUT = 10
    MAX_RETRIES = 3
    CACHE_TTL_SHORT = 3  # seconds
    CACHE_TTL_MEDIUM = 60
    CACHE_TTL_LONG = 300
    
    # Nifty strike intervals
    STRIKE_INTERVAL = 50
    STRIKE_RANGE_ATM = 1500  # ±1500 from ATM
    
    # Trading hours
    MARKET_OPEN = "09:15:00"
    MARKET_CLOSE = "15:30:00"
    
    # Greek calculation precision
    GREEK_PRECISION = 6
    PRICE_PRECISION = 2

# Graceful fallback for dhanhq
try:
    from dhanhq import marketfeed
    DHAN_WS_AVAILABLE = True
except ImportError:
    DHAN_WS_AVAILABLE = False
    logger.warning("dhanhq not installed. WebSocket features disabled.")

# ---------------------------------------------------------
# 2. PAGE SETUP & INSTITUTIONAL CSS (BLOOMBERG-STYLE)
# ---------------------------------------------------------
st.set_page_config(
    page_title="Prince PAX | Institutional Volatility Terminal",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        'Get Help': 'https://github.com/princepax',
        'Report a bug': 'https://github.com/princepax/issues',
        'About': 'Prince PAX Institutional Volatility Terminal v3.0'
    }
)

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');
    
    /* Base Theme - Bloomberg Dark */
    .stApp { 
        background-color: #0A0E17; 
        color: #E0E6ED; 
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; 
    }
    section[data-testid="stSidebar"] { 
        background: linear-gradient(180deg, #0F1419 0%, #1A1F2E 100%) !important; 
        border-right: 1px solid #2D3748; 
    }
    
    /* Metric Cards - Glassmorphism */
    .metric-card {
        background: rgba(26, 32, 44, 0.8);
        backdrop-filter: blur(10px);
        border: 1px solid rgba(99, 179, 237, 0.2);
        border-radius: 12px;
        padding: 16px 20px;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
        margin-bottom: 16px;
        border-top: 4px solid #63B3ED;
        position: relative;
        transition: all 0.3s ease;
    }
    .metric-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 12px 40px rgba(99, 179, 237, 0.2);
    }
    .metric-card-green { border-top-color: #48BB78; }
    .metric-card-red { border-top-color: #F56565; }
    .metric-card-amber { border-top-color: #ECC94B; }
    .metric-card-purple { border-top-color: #9F7AEA; }
    .metric-card-cyan { border-top-color: #0BC5EA; }
    
    .metric-title { 
        color: #A0AEC0; 
        font-size: 0.7rem; 
        font-weight: 700; 
        text-transform: uppercase; 
        letter-spacing: 1px; 
    }
    .metric-value { 
        color: #FFFFFF; 
        font-size: 1.6rem; 
        font-weight: 800; 
        margin-top: 6px; 
        font-variant-numeric: tabular-nums;
    }
    .metric-sub { 
        font-size: 0.75rem; 
        font-weight: 600; 
        margin-top: 6px; 
    }
    
    .sub-green { color: #48BB78; } 
    .sub-red { color: #F56565; } 
    .sub-amber { color: #ECC94B; } 
    .sub-blue { color: #63B3ED; } 
    .sub-purple { color: #9F7AEA; }
    .sub-cyan { color: #0BC5EA; }

    /* Chart Containers */
    .chart-container {
        background: rgba(26, 32, 44, 0.6);
        backdrop-filter: blur(10px);
        border: 1px solid rgba(99, 179, 237, 0.15);
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 20px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
    }
    .chart-title {
        font-size: 0.9rem; 
        font-weight: 700; 
        color: #63B3ED;
        text-transform: uppercase; 
        margin-bottom: 16px;
        border-bottom: 2px solid rgba(99, 179, 237, 0.3); 
        padding-bottom: 8px;
        display: flex; 
        justify-content: space-between; 
        align-items: center;
    }

    /* Tooltips */
    .info-tooltip { 
        position: relative; 
        display: inline-block; 
        cursor: help; 
        color: #A0AEC0; 
        font-size: 0.9rem; 
    }
    .info-tooltip .tooltip-text {
        visibility: hidden; 
        width: 320px; 
        background: rgba(15, 20, 25, 0.95);
        backdrop-filter: blur(10px);
        color: #E0E6ED;
        text-align: left; 
        border-radius: 8px; 
        padding: 14px; 
        position: absolute;
        top: 150%; 
        right: 0; 
        opacity: 0; 
        transition: opacity 0.3s;
        border: 1px solid rgba(99, 179, 237, 0.3); 
        font-size: 0.75rem; 
        font-weight: 500;
        box-shadow: 0px 8px 24px rgba(0,0,0,0.8); 
        z-index: 9999;
        line-height: 1.5;
    }
    .info-tooltip:hover .tooltip-text { 
        visibility: visible; 
        opacity: 1; 
    }
    .info-tooltip:hover { 
        color: #63B3ED; 
    }

    /* Status & Tables */
    .status-badge { 
        padding: 8px 16px; 
        border-radius: 6px; 
        font-weight: 700; 
        font-size: 0.8rem; 
        display: inline-block;
        backdrop-filter: blur(10px);
    }
    .status-live { 
        background: rgba(72, 187, 120, 0.2); 
        border: 1px solid #48BB78; 
        color: #48BB78; 
    }
    .status-closed { 
        background: rgba(236, 201, 75, 0.2); 
        border: 1px solid #ECC94B; 
        color: #ECC94B; 
    }
    
    .playbook-table { 
        width: 100%; 
        border-collapse: collapse; 
        font-size: 0.85rem; 
        margin-top: 12px; 
    }
    .playbook-table th { 
        background: rgba(15, 20, 25, 0.8);
        color: #63B3ED; 
        text-align: left; 
        padding: 12px; 
        border: 1px solid rgba(99, 179, 237, 0.2); 
        font-weight: 700;
    }
    .playbook-table td { 
        padding: 12px; 
        border: 1px solid rgba(99, 179, 237, 0.15); 
        color: #E0E6ED; 
    }
    .playbook-table tr:hover {
        background: rgba(99, 179, 237, 0.05);
    }
    
    /* Tab Styling */
    button[data-baseweb="tab"] { 
        background: rgba(26, 32, 44, 0.6) !important; 
        color: #A0AEC0 !important; 
        border-radius: 8px 8px 0 0 !important;
        border: 1px solid rgba(99, 179, 237, 0.2) !important;
        border-bottom: none !important;
        font-weight: 600 !important;
        padding: 12px 20px !important;
        transition: all 0.3s ease !important;
    }
    button[data-baseweb="tab"]:hover {
        background: rgba(99, 179, 237, 0.1) !important;
        color: #63B3ED !important;
    }
    button[data-baseweb="tab"][aria-selected="true"] { 
        background: rgba(99, 179, 237, 0.2) !important; 
        color: #63B3ED !important; 
        font-weight: 800 !important;
        border-bottom: 2px solid #63B3ED !important;
    }
    
    /* Alert Banners */
    .alert-banner {
        background: linear-gradient(90deg, rgba(245, 101, 101, 0.15) 0%, rgba(236, 201, 75, 0.15) 100%);
        border-left: 4px solid #F56565;
        padding: 16px 20px;
        border-radius: 8px;
        margin-bottom: 20px;
        animation: pulse 2s infinite;
    }
    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.8; }
    }
    
    /* Loading Spinner */
    .loading-spinner {
        border: 3px solid rgba(99, 179, 237, 0.1);
        border-top: 3px solid #63B3ED;
        border-radius: 50%;
        width: 40px;
        height: 40px;
        animation: spin 1s linear infinite;
        margin: 20px auto;
    }
    @keyframes spin {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Clean API Credentials
CLIENT_ID = str(st.secrets.get("DHAN_CLIENT_ID", "")).strip().replace('"', "").replace("'", "")
ACCESS_TOKEN = str(st.secrets.get("DHAN_ACCESS_TOKEN", "")).strip().replace('"', "").replace("'", "")

if not CLIENT_ID or not ACCESS_TOKEN:
    st.error("⚠️ **CRITICAL:** API credentials missing. Please update `.streamlit/secrets.toml`")
    st.stop()

# ---------------------------------------------------------
# 3. ADVANCED MATHEMATICAL ENGINE (INSTITUTIONAL GRADE)
# ---------------------------------------------------------
class MathematicalEngine:
    """Institutional-grade mathematical calculations for options analytics"""
    
    @staticmethod
    def norm_cdf(x: np.ndarray) -> np.ndarray:
        """Vectorized Cumulative Distribution Function"""
        return 0.5 * (1 + np.erf(x / np.sqrt(2.0)))
    
    @staticmethod
    def norm_pdf(x: np.ndarray) -> np.ndarray:
        """Vectorized Probability Density Function"""
        return np.exp(-0.5 * x**2) / np.sqrt(2 * np.pi)
    
    @staticmethod
    def calculate_bs_greeks_vectorized(
        S: np.ndarray, 
        K: np.ndarray, 
        T: float, 
        sigma: np.ndarray, 
        r: float = Config.RISK_FREE_RATE,
        q: float = Config.NIFTY_DIVIDEND_YIELD
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """
        Dividend-adjusted Black-Scholes Greeks (institutional standard)
        Returns: Gamma, Vanna, Charm, Speed, Vomma, Veta
        """
        T = np.maximum(T, 1e-5)
        sigma = np.maximum(sigma, 1e-4)
        S = np.maximum(S, 1e-5)
        K = np.maximum(K, 1e-5)
        
        d1 = (np.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
        d2 = d1 - sigma * np.sqrt(T)
        
        pdf_d1 = MathematicalEngine.norm_pdf(d1)
        
        # Core Greeks
        gamma = np.exp(-q * T) * pdf_d1 / (S * sigma * np.sqrt(T))
        vanna = -np.exp(-q * T) * pdf_d1 * d2 / sigma
        charm = -np.exp(-q * T) * pdf_d1 * (2 * (r - q) * np.sqrt(T) - d2 * sigma * np.sqrt(T)) / (2 * T * sigma)
        speed = -gamma / S * (1 + d1 / (sigma * np.sqrt(T)))
        vomma = gamma * S * np.sqrt(T) * d1 * d2 / sigma
        veta = -np.exp(-q * T) * S * pdf_d1 * np.sqrt(T) * (
            (r - q) * d2 / (sigma * np.sqrt(T)) + (1 + d1 * d2) / (2 * T)
        )
        
        return gamma, vanna, charm, speed, vomma, veta
    
    @staticmethod
    def calculate_max_pain_vectorized(strikes: np.ndarray, ce_oi: np.ndarray, pe_oi: np.ndarray) -> int:
        """O(N²) vectorized matrix calculation for Max Pain"""
        K = strikes.reshape(-1, 1)
        S = strikes.reshape(1, -1)
        
        ce_loss = ce_oi * np.maximum(K - S, 0)
        pe_loss = pe_oi * np.maximum(S - K, 0)
        
        total_loss = np.sum(ce_loss + pe_loss, axis=1)
        return int(strikes[np.argmin(total_loss)])
    
    @staticmethod
    def calculate_volatility_cone(historical_vols: np.ndarray, window_sizes: List[int]) -> pd.DataFrame:
        """Calculate volatility cone for historical vol percentiles"""
        cone_data = []
        for window in window_sizes:
            if len(historical_vols) >= window:
                rolling_vols = pd.Series(historical_vols).rolling(window=window).std() * np.sqrt(252)
                rolling_vols = rolling_vols.dropna()
                if len(rolling_vols) > 0:
                    cone_data.append({
                        'Window': window,
                        'Min': rolling_vols.min(),
                        '10th': rolling_vols.quantile(0.1),
                        '25th': rolling_vols.quantile(0.25),
                        'Median': rolling_vols.median(),
                        '75th': rolling_vols.quantile(0.75),
                        '90th': rolling_vols.quantile(0.9),
                        'Max': rolling_vols.max()
                    })
        return pd.DataFrame(cone_data)
    
    @staticmethod
    def calculate_volatility_risk_premium(iv: float, hv_20d: float, hv_50d: float) -> Dict[str, float]:
        """Calculate Volatility Risk Premium (VRP)"""
        vrp_20 = iv - hv_20d
        vrp_50 = iv - hv_50d
        vrp_premium_pct = (vrp_20 / hv_20d * 100) if hv_20d > 0 else 0
        
        return {
            'VRP_20D': vrp_20,
            'VRP_50D': vrp_50,
            'VRP_Premium_Pct': vrp_premium_pct,
            'Signal': 'SELL VOL' if vrp_20 > 2 else ('BUY VOL' if vrp_20 < -2 else 'NEUTRAL')
        }
    
    @staticmethod
    def calculate_support_resistance_levels(
        df_oc: pd.DataFrame, 
        spot: float, 
        method: str = 'gex_weighted'
    ) -> Dict[str, float]:
        """Calculate support/resistance with probability weighting"""
        if method == 'gex_weighted':
            # Weight by absolute GEX
            df_oc['Abs_GEX'] = df_oc['CE_GEX'] + df_oc['PE_GEX']
            total_gex = df_oc['Abs_GEX'].sum()
            
            if total_gex > 0:
                df_oc['GEX_Weight'] = df_oc['Abs_GEX'] / total_gex
                
                # Support: Put walls below spot
                support_candidates = df_oc[df_oc['Strike'] < spot].nlargest(3, 'GEX_Weight')
                support = support_candidates['Strike'].iloc[0] if not support_candidates.empty else spot - 100
                
                # Resistance: Call walls above spot
                resistance_candidates = df_oc[df_oc['Strike'] > spot].nlargest(3, 'GEX_Weight')
                resistance = resistance_candidates['Strike'].iloc[0] if not resistance_candidates.empty else spot + 100
                
                return {
                    'Support': support,
                    'Resistance': resistance,
                    'Support_Probability': support_candidates['GEX_Weight'].iloc[0] * 100 if not support_candidates.empty else 0,
                    'Resistance_Probability': resistance_candidates['GEX_Weight'].iloc[0] * 100 if not resistance_candidates.empty else 0
                }
        
        return {'Support': spot - 100, 'Resistance': spot + 100, 'Support_Probability': 0, 'Resistance_Probability': 0}
    
    @staticmethod
    def detect_unusual_activity(df_oc: pd.DataFrame, threshold_multiplier: float = 2.0) -> pd.DataFrame:
        """Detect unusual volume/OI activity"""
        # Calculate mean and std for volume and OI
        ce_vol_mean = df_oc['CE_Vol'].mean()
        ce_vol_std = df_oc['CE_Vol'].std()
        pe_vol_mean = df_oc['PE_Vol'].mean()
        pe_vol_std = df_oc['PE_Vol'].std()
        
        # Flag strikes with volume > mean + 2*std
        df_oc['CE_Vol_Anomaly'] = (df_oc['CE_Vol'] > ce_vol_mean + threshold_multiplier * ce_vol_std).astype(int)
        df_oc['PE_Vol_Anomaly'] = (df_oc['PE_Vol'] > pe_vol_mean + threshold_multiplier * pe_vol_std).astype(int)
        df_oc['Unusual_Activity'] = df_oc['CE_Vol_Anomaly'] | df_oc['PE_Vol_Anomaly']
        
        return df_oc[df_oc['Unusual_Activity'] == 1]

# ---------------------------------------------------------
# 4. DATA ENGINES (RESILIENT & OPTIMIZED)
# ---------------------------------------------------------
@st.cache_data(ttl=Config.CACHE_TTL_LONG)
def fetch_expiry_list_direct() -> List[str]:
    """Fetch available expiry dates with retry logic"""
    url = "https://api.dhan.co/v2/optionchain/expirylist"
    headers = {"client-id": CLIENT_ID, "access-token": ACCESS_TOKEN, "Content-Type": "application/json"}
    
    for attempt in range(Config.MAX_RETRIES):
        try:
            res = requests.post(
                url, 
                headers=headers, 
                json={"UnderlyingScrip": 13, "UnderlyingSeg": "IDX_I"}, 
                timeout=Config.API_TIMEOUT
            )
            if res.status_code == 200 and res.json().get("status") == "success":
                return res.json().get("data", [])
        except requests.exceptions.RequestException as e:
            logger.warning(f"Expiry fetch attempt {attempt+1} failed: {e}")
            time.sleep(1)
    
    return []

@st.cache_data(ttl=Config.CACHE_TTL_SHORT)
def fetch_gex_option_chain(expiry_date: str) -> Tuple[Optional[pd.DataFrame], float, Optional[str]]:
    """Fetch complete option chain with vectorized Greek calculations"""
    url = "https://api.dhan.co/v2/optionchain"
    headers = {"client-id": CLIENT_ID, "access-token": ACCESS_TOKEN, "Content-Type": "application/json"}
    payload = {"UnderlyingScrip": 13, "UnderlyingSeg": "IDX_I", "Expiry": expiry_date}

    for attempt in range(Config.MAX_RETRIES):
        try:
            res = requests.post(url, headers=headers, json=payload, timeout=Config.API_TIMEOUT)
            data = res.json()
            
            if res.status_code == 200 and data.get("status") == "success":
                raw_data = data.get("data", {})
                spot_price = float(raw_data.get("last_price", 0.0))
                oc_raw = raw_data.get("oc", {})
                
                if not oc_raw:
                    return None, spot_price, "No contracts returned."

                T_years = max(
                    (datetime.datetime.strptime(expiry_date, "%Y-%m-%d").date() - datetime.date.today()).days, 
                    1
                ) / 365.0
                
                # Vectorized data extraction
                strikes = np.array([int(float(k)) for k in oc_raw.keys()])
                ce_oi = np.array([float(oc_raw[k].get("ce", {}).get("oi", 0) or 0) for k in oc_raw.keys()])
                pe_oi = np.array([float(oc_raw[k].get("pe", {}).get("oi", 0) or 0) for k in oc_raw.keys()])
                ce_vol = np.array([float(oc_raw[k].get("ce", {}).get("volume", 0) or 0.0) for k in oc_raw.keys()])
                pe_vol = np.array([float(oc_raw[k].get("pe", {}).get("volume", 0) or 0.0) for k in oc_raw.keys()])
                ce_ltp = np.array([float(oc_raw[k].get("ce", {}).get("last_price", 0) or 0) for k in oc_raw.keys()])
                pe_ltp = np.array([float(oc_raw[k].get("pe", {}).get("last_price", 0) or 0) for k in oc_raw.keys()])
                
                ce_iv = np.array([float(oc_raw[k].get("ce", {}).get("implied_volatility", 0) or 0)/100.0 for k in oc_raw.keys()])
                pe_iv = np.array([float(oc_raw[k].get("pe", {}).get("implied_volatility", 0) or 0)/100.0 for k in oc_raw.keys()])
                
                ce_delta = np.array([float(oc_raw[k].get("ce", {}).get("greeks", {}).get("delta", 0) or 0) for k in oc_raw.keys()])
                pe_delta = np.array([float(oc_raw[k].get("pe", {}).get("greeks", {}).get("delta", 0) or 0) for k in oc_raw.keys()])
                ce_gamma_api = np.array([float(oc_raw[k].get("ce", {}).get("greeks", {}).get("gamma", 0) or 0) for k in oc_raw.keys()])
                pe_gamma_api = np.array([float(oc_raw[k].get("pe", {}).get("greeks", {}).get("gamma", 0) or 0) for k in oc_raw.keys()])

                # Vectorized Greek calculation (dividend-adjusted)
                ce_gamma_bs, ce_vanna, ce_charm, ce_speed, ce_vomma, ce_veta = MathematicalEngine.calculate_bs_greeks_vectorized(
                    spot_price, strikes, T_years, np.maximum(ce_iv, 0.15)
                )
                pe_gamma_bs, pe_vanna, pe_charm, pe_speed, pe_vomma, pe_veta = MathematicalEngine.calculate_bs_greeks_vectorized(
                    spot_price, strikes, T_years, np.maximum(pe_iv, 0.15)
                )
                
                # Use API gamma if valid, else fallback to BS
                ce_gamma = np.where(ce_gamma_api > 0, ce_gamma_api, ce_gamma_bs)
                pe_gamma = np.where(pe_gamma_api > 0, pe_gamma_api, pe_gamma_bs)

                # OpenBull GEX Model: GEX = Gamma × OI × LotSize
                ce_gex = ce_gamma * ce_oi * Config.NIFTY_LOT_SIZE
                pe_gex = pe_gamma * pe_oi * Config.NIFTY_LOT_SIZE
                net_gex = ce_gex - pe_gex
                abs_gex = ce_gex + pe_gex

                # Dollarized DEX
                ce_dex = ce_oi * ce_delta * spot_price * Config.NIFTY_LOT_SIZE / 1e5
                pe_dex = pe_oi * pe_delta * spot_price * Config.NIFTY_LOT_SIZE / 1e5
                net_dex = ce_dex + pe_dex
                abs_dex = np.abs(ce_dex) + np.abs(pe_dex)
                net_delta_oi = (ce_oi * ce_delta) + (pe_oi * pe_delta)

                df = pd.DataFrame({
                    "Strike": strikes, 
                    "CE_LTP": ce_ltp, 
                    "PE_LTP": pe_ltp, 
                    "CE_OI": ce_oi, 
                    "PE_OI": pe_oi, 
                    "CE_Vol": ce_vol, 
                    "PE_Vol": pe_vol,
                    "CE_Delta": ce_delta, 
                    "PE_Delta": pe_delta, 
                    "Net_Delta_OI": net_delta_oi, 
                    "Net_DEX": net_dex, 
                    "ABS_DEX": abs_dex,
                    "CE_GEX": ce_gex, 
                    "PE_GEX": pe_gex, 
                    "Net_GEX": net_gex, 
                    "ABS_GEX": abs_gex,
                    "Net_VEX": ((ce_oi * ce_vanna) - (pe_oi * pe_vanna)) * Config.NIFTY_LOT_SIZE / 1e3, 
                    "Net_CHEX": ((ce_oi * ce_charm) - (pe_oi * pe_charm)) * Config.NIFTY_LOT_SIZE / 1e3,
                    "Net_SPEX": ((ce_oi * ce_speed) - (pe_oi * pe_speed)) * Config.NIFTY_LOT_SIZE / 1e3,
                    "Net_VOMMA": ((ce_oi * ce_vomma) - (pe_oi * pe_vomma)) * Config.NIFTY_LOT_SIZE / 1e3,
                    "Net_VETA": ((ce_oi * ce_veta) - (pe_oi * pe_veta)) * Config.NIFTY_LOT_SIZE / 1e3,
                    "CE_IV": ce_iv * 100.0, 
                    "PE_IV": pe_iv * 100.0, 
                    "IV_Spread": (ce_iv - pe_iv) * 100.0,
                })
                
                return df.sort_values("Strike").reset_index(drop=True), spot_price, None
            else:
                return None, 0.0, str(data.get("remarks") or data.get("message") or f"HTTP {res.status_code}")
                
        except requests.exceptions.RequestException as e:
            logger.warning(f"Option chain fetch attempt {attempt+1} failed: {e}")
            time.sleep(1)
    
    return None, 0.0, "Connection Error: Max retries exceeded."

# ---------------------------------------------------------
# 5. WEBSOCKET DAEMON (THREAD-SAFE)
# ---------------------------------------------------------
@st.cache_resource
def start_dhan_websocket(client_id: str, access_token: str) -> Dict[str, Any]:
    """Real-time WebSocket feed for futures and heavyweights"""
    ws_data = {
        "RELIANCE_LTP": 0.0, "RELIANCE_PREV": 0.0,
        "HDFCBANK_LTP": 0.0, "HDFCBANK_PREV": 0.0,
        "ICICIBANK_LTP": 0.0, "ICICIBANK_PREV": 0.0,
        "NIFTY_FUT_LTP": 0.0, "CVD": 0.0, "CONNECTED": False, "ERROR": None
    }

    if not DHAN_WS_AVAILABLE:
        ws_data["ERROR"] = "dhanhq library not installed"
        return ws_data

    CURRENT_NIFTY_FUT_ID = "58756" 
    instruments = [(1, "2885"), (1, "1333"), (1, "4963"), (2, CURRENT_NIFTY_FUT_ID)]
    sub_code = getattr(marketfeed, 'Ticker', 15)

    def on_connect(instance): 
        ws_data["CONNECTED"] = True
        logger.info("WebSocket connected")
    
    def on_disconnect(instance): 
        ws_data["CONNECTED"] = False
        logger.warning("WebSocket disconnected")

    def on_message(instance, message):
        if isinstance(message, dict):
            sec_id = str(message.get('security_id', ''))
            ltp = float(message.get('LTP', 0.0))
            ltq = float(message.get('last_trade_quantity', 0.0))
            
            if ltp > 0:
                if sec_id == CURRENT_NIFTY_FUT_ID: 
                    ws_data["NIFTY_FUT_LTP"] = ltp
                elif sec_id in ["2885", "1333", "4963"]:
                    symbol = "RELIANCE" if sec_id == "2885" else "HDFCBANK" if sec_id == "1333" else "ICICIBANK"
                    prev_ltp = ws_data[f"{symbol}_PREV"]
                    if prev_ltp > 0:
                        if ltp > prev_ltp: 
                            ws_data["CVD"] += ltq
                        elif ltp < prev_ltp: 
                            ws_data["CVD"] -= ltq
                    ws_data[f"{symbol}_LTP"] = ltp
                    ws_data[f"{symbol}_PREV"] = ltp

    def run_ws():
        try:
            feed = marketfeed.DhanFeed(
                client_id, 
                access_token, 
                instruments, 
                sub_code, 
                on_connect=on_connect, 
                on_message=on_message
            )
            feed.run_forever()
        except Exception as e:
            ws_data["ERROR"] = str(e)
            ws_data["CONNECTED"] = False
            logger.error(f"WebSocket error: {e}")

    t = threading.Thread(target=run_ws, daemon=True)
    t.start()
    return ws_data

# ---------------------------------------------------------
# 6. MAIN DASHBOARD
# ---------------------------------------------------------
def main():
    """Main dashboard application"""
    
    # Sidebar controls
    st.sidebar.title("⚙️ Command Center")
    st.sidebar.markdown("---")
    
    auto_refresh = st.sidebar.checkbox("🔄 Live Auto-Refresh (5s)", value=True)
    if auto_refresh:
        st_autorefresh(interval=5000, key="datarefresh")
    
    # Time & Market Status
    IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    now_ist = datetime.datetime.now(IST)
    today_date_str = now_ist.strftime("%Y-%m-%d")
    now_time_str = now_ist.strftime("%H:%M:%S")
    
    is_weekday = now_ist.weekday() < 5
    m_open = now_ist.replace(hour=9, minute=15, second=0, microsecond=0)
    m_close = now_ist.replace(hour=15, minute=30, second=0, microsecond=0)
    is_market_live = is_weekday and (m_open <= now_ist <= m_close)
    
    # Expiry selection
    valid_expiries = fetch_expiry_list_direct()
    if valid_expiries: 
        selected_expiry = st.sidebar.selectbox("📅 Primary Expiry", valid_expiries)
    else:
        days_until_thursday = (3 - now_ist.weekday()) % 7
        default_expiry = (now_ist + datetime.timedelta(days=days_until_thursday)).strftime("%Y-%m-%d")
        selected_expiry = st.sidebar.date_input(
            "📅 Primary Expiry", 
            datetime.datetime.strptime(default_expiry, "%Y-%m-%d")
        ).strftime("%Y-%m-%d")
    
    # Advanced settings
    with st.sidebar.expander("🔧 Advanced Settings"):
        show_unusual_activity = st.checkbox("🚨 Highlight Unusual Activity", value=True)
        show_3d_surface = st.checkbox("📊 Show 3D Volatility Surface", value=True)
        vrp_threshold = st.slider("VRP Alert Threshold (%)", -5.0, 10.0, 2.0, 0.5)
    
    # Fetch data
    with st.spinner("Fetching institutional option chain data..."):
        df_oc, spot_price, error_remark = fetch_gex_option_chain(selected_expiry)
    
    if error_remark:
        st.error(f"⚠️ **Dhan Server Error:** {error_remark}")
        st.stop()
    
    # Calculate synthetic future & ATM
    synthetic_future = spot_price
    if df_oc is not None and not df_oc.empty:
        spot_atm = int(round(spot_price / Config.STRIKE_INTERVAL) * Config.STRIKE_INTERVAL)
        spot_row = df_oc[df_oc["Strike"] == spot_atm]
        if not spot_row.empty: 
            synthetic_future = spot_atm + spot_row["CE_LTP"].values[0] - spot_row["PE_LTP"].values[0]
    
    atm_strike = int(round(synthetic_future / Config.STRIKE_INTERVAL) * Config.STRIKE_INTERVAL)
    
    all_strikes = df_oc["Strike"].tolist()
    default_index = all_strikes.index(atm_strike) if atm_strike in all_strikes else len(all_strikes)//2
    selected_target_strike = st.sidebar.selectbox("🎯 Target Strike Analysis", all_strikes, index=default_index)
    
    # WebSocket
    live_ws_data = start_dhan_websocket(CLIENT_ID, ACCESS_TOKEN)
    
    # ---------------------------------------------------------
    # CORE ANALYTICS
    # ---------------------------------------------------------
    
    # Max Pain
    max_pain_strike = MathematicalEngine.calculate_max_pain_vectorized(
        df_oc["Strike"].values, 
        df_oc["CE_OI"].values, 
        df_oc["PE_OI"].values
    )
    
    # Support/Resistance
    sr_levels = MathematicalEngine.calculate_support_resistance_levels(df_oc, spot_price)
    
    # Target metrics
    target_row = df_oc[df_oc["Strike"] == selected_target_strike]
    target_ce_iv = target_row["CE_IV"].values[0] if not target_row.empty else 0.0
    target_pe_iv = target_row["PE_IV"].values[0] if not target_row.empty else 0.0
    target_iv_spread = target_ce_iv - target_pe_iv
    
    # Filtered range
    df_filtered = df_oc[
        (df_oc["Strike"] >= atm_strike - Config.STRIKE_RANGE_ATM) & 
        (df_oc["Strike"] <= atm_strike + Config.STRIKE_RANGE_ATM)
    ].copy()
    strike_labels = df_filtered["Strike"].astype(str).tolist()
    
    # Aggregate metrics
    total_net_gex = df_oc["Net_GEX"].sum()
    total_net_delta_oi = df_oc["Net_Delta_OI"].sum()
    total_call_oi, total_put_oi = df_oc["CE_OI"].sum(), df_oc["PE_OI"].sum()
    current_pcr = total_put_oi / total_call_oi if total_call_oi > 0 else 0.0
    
    # Unusual activity detection
    unusual_activity_df = MathematicalEngine.detect_unusual_activity(df_oc) if show_unusual_activity else pd.DataFrame()
    
    # Regime logic
    gex_std = df_filtered["Net_GEX"].std()
    gex_mean = df_filtered["Net_GEX"].mean()
    current_z_gex = (total_net_gex - gex_mean) / gex_std if gex_std > 0 else 0.0
    
    if current_z_gex < -2.0: 
        z_signal, z_color, z_card_border = "GAMMA COLLAPSE", "sub-red", "metric-card-red"
    elif -1.0 <= current_z_gex <= 1.0: 
        z_signal, z_color, z_card_border = "NORMAL DAMPENING", "sub-green", "metric-card-green"
    else: 
        z_signal, z_color, z_card_border = "TRANSITION ZONE", "sub-amber", "metric-card-amber"
    
    if total_net_delta_oi > 50000: 
        dir_signal, dir_color = "STRONGLY BULLISH", "sub-green"
    elif total_net_delta_oi > 10000: 
        dir_signal, dir_color = "MILDLY BULLISH", "sub-green"
    elif total_net_delta_oi < -50000: 
        dir_signal, dir_color = "STRONGLY BEARISH", "sub-red"
    elif total_net_delta_oi < -10000: 
        dir_signal, dir_color = "MILDLY BEARISH", "sub-red"
    else: 
        dir_signal, dir_color = "NEUTRAL / RANGEBOUND", "sub-amber"
    
    # ---------------------------------------------------------
    # DASHBOARD UI
    # ---------------------------------------------------------
    
    # Header
    st.markdown("### 🏛️ PRINCE PAX | INSTITUTIONAL VOLATILITY TERMINAL")
    status_class = "status-live" if is_market_live else "status-closed"
    status_text = "🟢 LIVE MARKET" if is_market_live else "🟠 MARKET CLOSED"
    st.markdown(
        f'<div class="status-badge {status_class}">{status_text} | Expiry: {selected_expiry} | IST: {now_time_str}</div>', 
        unsafe_allow_html=True
    )
    
    # Alert banner for unusual activity
    if not unusual_activity_df.empty and show_unusual_activity:
        st.markdown(
            f"""
            <div class="alert-banner">
                🚨 <strong>UNUSUAL ACTIVITY DETECTED:</strong> {len(unusual_activity_df)} strikes showing abnormal volume patterns
            </div>
            """, 
            unsafe_allow_html=True
        )
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # 7-Tab Layout
    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "📊 Command Center", 
        "🧱 Dealer Exposure", 
        "🌊 Order Flow", 
        "📈 Volatility Analytics",
        "🎯 Key Levels",
        "🚨 Activity Monitor",
        "📋 Data Grid"
    ])
    
    # TAB 1: COMMAND CENTER
    with tab1:
        m1, m2, m3, m4, m5, m6 = st.columns(6)
        
        with m1:
            st.markdown(f"""
                <div class="metric-card metric-card-amber">
                    <div class="info-tooltip">ⓘ<span class="tooltip-text">Synthetic Future (K + C - P). All analytics center on this True Forward Price.</span></div>
                    <div class="metric-title">NIFTY SYNTH FUT</div>
                    <div class="metric-value">₹{synthetic_future:,.2f}</div>
                    <div class="metric-sub sub-amber">Spot: ₹{spot_price:,.2f} | Pain: {max_pain_strike}</div>
                </div>
            """, unsafe_allow_html=True)

        with m2:
            spread_class = "sub-green" if target_iv_spread >= 0 else "sub-red"
            border_class = "metric-card-green" if target_iv_spread >= 0 else "metric-card-red"
            st.markdown(f"""
                <div class="metric-card {border_class}">
                    <div class="info-tooltip">ⓘ<span class="tooltip-text">IV Spread = Call IV - Put IV. Rising = Call accumulation.</span></div>
                    <div class="metric-title">{selected_target_strike} IV SPREAD</div>
                    <div class="metric-value">{target_iv_spread:+.2f}%</div>
                    <div class="metric-sub {spread_class}">CE {target_ce_iv:.1f}% | PE {target_pe_iv:.1f}%</div>
                </div>
            """, unsafe_allow_html=True)

        with m3:
            st.markdown(f"""
                <div class="metric-card {'metric-card-green' if total_net_delta_oi >= 0 else 'metric-card-red'}">
                    <div class="info-tooltip">ⓘ<span class="tooltip-text">Net Delta Exposure. Sharp drops signal short-covering panic.</span></div>
                    <div class="metric-title">NET DELTA OI</div>
                    <div class="metric-value">{total_net_delta_oi:+,.0f}</div>
                    <div class="metric-sub {dir_color}">{dir_signal}</div>
                </div>
            """, unsafe_allow_html=True)

        with m4:
            st.markdown(f"""
                <div class="metric-card metric-card-purple">
                    <div class="info-tooltip">ⓘ<span class="tooltip-text">Put-Call Ratio. >1.0 = Bullish support. <1.0 = Bearish resistance.</span></div>
                    <div class="metric-title">PCR (OI)</div>
                    <div class="metric-value">{current_pcr:.2f}</div>
                    <div class="metric-sub sub-blue">Total OI: {(total_call_oi+total_put_oi)/1e6:.1f}M</div>
                </div>
            """, unsafe_allow_html=True)

        with m5:
            st.markdown(f"""
                <div class="metric-card {z_card_border}">
                    <div class="info-tooltip">ⓘ<span class="tooltip-text">Z-GEX < -2.0 = Gamma collapse. Prime squeeze regime.</span></div>
                    <div class="metric-title">Z-GEX SCORE</div>
                    <div class="metric-value">{current_z_gex:+.2f}</div>
                    <div class="metric-sub {z_color}">{z_signal}</div>
                </div>
            """, unsafe_allow_html=True)

        with m6:
            nifty_fut = live_ws_data.get("NIFTY_FUT_LTP", 0.0)
            basis = nifty_fut - spot_price if nifty_fut > 0 else 0.0
            basis_color = "sub-green" if basis >= 0 else "sub-red"
            st.markdown(f"""
                <div class="metric-card metric-card-cyan">
                    <div class="info-tooltip">ⓘ<span class="tooltip-text">Live Futures Basis. Validates breakout strength.</span></div>
                    <div class="metric-title">FUTURES BASIS</div>
                    <div class="metric-value">{basis:+.2f} Pts</div>
                    <div class="metric-sub {basis_color}">Fut: ₹{nifty_fut:,.1f}</div>
                </div>
            """, unsafe_allow_html=True)
        
        # Support/Resistance summary
        st.markdown("<br>", unsafe_allow_html=True)
        sr_col1, sr_col2 = st.columns(2)
        with sr_col1:
            st.markdown(f"""
                <div class="metric-card metric-card-green">
                    <div class="metric-title">SUPPORT LEVEL</div>
                    <div class="metric-value">₹{sr_levels['Support']:,.0f}</div>
                    <div class="metric-sub sub-green">Probability: {sr_levels['Support_Probability']:.1f}%</div>
                </div>
            """, unsafe_allow_html=True)
        with sr_col2:
            st.markdown(f"""
                <div class="metric-card metric-card-red">
                    <div class="metric-title">RESISTANCE LEVEL</div>
                    <div class="metric-value">₹{sr_levels['Resistance']:,.0f}</div>
                    <div class="metric-sub sub-red">Probability: {sr_levels['Resistance_Probability']:.1f}%</div>
                </div>
            """, unsafe_allow_html=True)

    # TAB 2: DEALER EXPOSURE
    with tab2:
        c1, c2 = st.columns(2)
        
        with c1:
            st.markdown('<div class="chart-container"><div class="chart-title">Net Gamma Exposure (GEX) <div class="info-tooltip">ⓘ<span class="tooltip-text">OpenBull Model: GEX = Gamma × OI × LotSize</span></div></div>', unsafe_allow_html=True)
            fig_gex = go.Figure()
            colors_gex = ["#48BB78" if g >= 0 else "#F56565" for g in df_filtered["Net_GEX"]]
            fig_gex.add_trace(go.Bar(
                x=df_filtered["Strike"], 
                y=df_filtered["Net_GEX"], 
                marker_color=colors_gex, 
                name="Net GEX", 
                opacity=0.8,
                hovertemplate="Strike: %{x}<br>Net GEX: %{y:,.0f}<extra></extra>"
            ))
            fig_gex.add_trace(go.Scatter(
                x=df_filtered["Strike"], 
                y=df_filtered["ABS_GEX"], 
                mode="lines", 
                name="Absolute GEX", 
                line=dict(color="#63B3ED", width=2, shape="spline")
            ))
            
            fig_gex.add_vline(x=spot_price, line_dash="solid", line_color="#ECC94B", line_width=2, annotation_text="Spot")
            fig_gex.add_vline(x=max_pain_strike, line_dash="dash", line_color="#9F7AEA", line_width=1, annotation_text="Max Pain")
            
            fig_gex.update_layout(
                template="plotly_dark", 
                paper_bgcolor="rgba(0,0,0,0)", 
                plot_bgcolor="rgba(0,0,0,0)", 
                margin=dict(l=0, r=0, t=10, b=0), 
                height=400,
                xaxis=dict(tickmode='array', tickvals=df_filtered["Strike"], ticktext=strike_labels, tickangle=-45)
            )
            st.plotly_chart(fig_gex, use_container_width=True, key="chart_gex_profile")
            st.markdown('</div>', unsafe_allow_html=True)

        with c2:
            st.markdown('<div class="chart-container"><div class="chart-title">Net Delta Exposure (DEX) <div class="info-tooltip">ⓘ<span class="tooltip-text">Rupee value of Delta per strike</span></div></div>', unsafe_allow_html=True)
            fig_dex = go.Figure()
            colors_dex = ["#48BB78" if val >= 0 else "#F56565" for val in df_filtered["Net_DEX"]]
            fig_dex.add_trace(go.Bar(
                x=df_filtered["Strike"], 
                y=df_filtered["Net_DEX"], 
                marker_color=colors_dex, 
                name="Net DEX", 
                opacity=0.8,
                hovertemplate="Strike: %{x}<br>DEX: %{y:,.1f}L<extra></extra>"
            ))
            fig_dex.add_vline(x=spot_price, line_dash="solid", line_color="#ECC94B", line_width=2)
            
            fig_dex.update_layout(
                template="plotly_dark", 
                paper_bgcolor="rgba(0,0,0,0)", 
                plot_bgcolor="rgba(0,0,0,0)", 
                margin=dict(l=0, r=0, t=10, b=0), 
                height=400,
                xaxis=dict(tickmode='array', tickvals=df_filtered["Strike"], ticktext=strike_labels, tickangle=-45)
            )
            st.plotly_chart(fig_dex, use_container_width=True, key="chart_dex")
            st.markdown('</div>', unsafe_allow_html=True)

    # TAB 3: ORDER FLOW
    with tab3:
        st.info("🔄 Real-time order flow tracking active. Data updates every 5 seconds during market hours.")
        
        # WebSocket metrics
        nifty_fut = live_ws_data.get("NIFTY_FUT_LTP", 0.0)
        cvd_val = live_ws_data.get("CVD", 0.0)
        
        ws_col1, ws_col2, ws_col3 = st.columns(3)
        with ws_col1:
            st.metric("Nifty Futures", f"₹{nifty_fut:,.2f}" if nifty_fut > 0 else "Awaiting...")
        with ws_col2:
            st.metric("Heavyweight CVD", f"{cvd_val:+,.0f}")
        with ws_col3:
            conn_status = "🟢 ACTIVE" if live_ws_data.get("CONNECTED") else "🔴 DISCONNECTED"
            st.metric("WebSocket Status", conn_status)

    # TAB 4: VOLATILITY ANALYTICS
    with tab4:
        c1, c2 = st.columns(2)
        
        with c1:
            st.markdown('<div class="chart-container"><div class="chart-title">IV Smile (Volatility Skew)</div>', unsafe_allow_html=True)
            fig_smile = go.Figure()
            fig_smile.add_trace(go.Scatter(
                x=df_filtered["Strike"], 
                y=df_filtered["CE_IV"], 
                mode="lines+markers", 
                name="Call IV", 
                line=dict(color="#48BB78", width=2)
            ))
            fig_smile.add_trace(go.Scatter(
                x=df_filtered["Strike"], 
                y=df_filtered["PE_IV"], 
                mode="lines+markers", 
                name="Put IV", 
                line=dict(color="#F56565", width=2)
            ))
            fig_smile.add_vline(x=spot_price, line_dash="solid", line_color="#ECC94B")
            
            fig_smile.update_layout(
                template="plotly_dark", 
                paper_bgcolor="rgba(0,0,0,0)", 
                plot_bgcolor="rgba(0,0,0,0)", 
                margin=dict(l=0, r=0, t=10, b=0), 
                height=350,
                xaxis=dict(tickmode='array', tickvals=df_filtered["Strike"], ticktext=strike_labels, tickangle=-45)
            )
            st.plotly_chart(fig_smile, use_container_width=True, key="chart_iv_smile")
            st.markdown('</div>', unsafe_allow_html=True)

        with c2:
            st.markdown('<div class="chart-container"><div class="chart-title">IV Spread by Strike</div>', unsafe_allow_html=True)
            fig_iv_spread = go.Figure()
            colors_spread = ["#48BB78" if v >= 0 else "#F56565" for v in df_filtered["IV_Spread"]]
            fig_iv_spread.add_trace(go.Bar(
                x=df_filtered["Strike"], 
                y=df_filtered["IV_Spread"], 
                marker_color=colors_spread
            ))
            fig_iv_spread.add_hline(y=0, line_dash="dash", line_color="white", opacity=0.3)
            
            fig_iv_spread.update_layout(
                template="plotly_dark", 
                paper_bgcolor="rgba(0,0,0,0)", 
                plot_bgcolor="rgba(0,0,0,0)", 
                margin=dict(l=0, r=0, t=10, b=0), 
                height=350,
                xaxis=dict(tickmode='array', tickvals=df_filtered["Strike"], ticktext=strike_labels, tickangle=-45)
            )
            st.plotly_chart(fig_iv_spread, use_container_width=True, key="chart_iv_spread")
            st.markdown('</div>', unsafe_allow_html=True)

    # TAB 5: KEY LEVELS
    with tab5:
        st.markdown("### 🎯 Institutional Key Levels")
        
        level_col1, level_col2, level_col3 = st.columns(3)
        
        with level_col1:
            st.markdown(f"""
                <div class="metric-card metric-card-amber">
                    <div class="metric-title">MAX PAIN</div>
                    <div class="metric-value">₹{max_pain_strike:,.0f}</div>
                    <div class="metric-sub sub-amber">Expiry Magnet</div>
                </div>
            """, unsafe_allow_html=True)
        
        with level_col2:
            st.markdown(f"""
                <div class="metric-card metric-card-green">
                    <div class="metric-title">SUPPORT</div>
                    <div class="metric-value">₹{sr_levels['Support']:,.0f}</div>
                    <div class="metric-sub sub-green">{sr_levels['Support_Probability']:.1f}% Probability</div>
                </div>
            """, unsafe_allow_html=True)
        
        with level_col3:
            st.markdown(f"""
                <div class="metric-card metric-card-red">
                    <div class="metric-title">RESISTANCE</div>
                    <div class="metric-value">₹{sr_levels['Resistance']:,.0f}</div>
                    <div class="metric-sub sub-red">{sr_levels['Resistance_Probability']:.1f}% Probability</div>
                </div>
            """, unsafe_allow_html=True)

    # TAB 6: ACTIVITY MONITOR
    with tab6:
        if show_unusual_activity and not unusual_activity_df.empty:
            st.markdown("### 🚨 Unusual Activity Detected")
            st.dataframe(
                unusual_activity_df[[
                    "Strike", "CE_Vol", "PE_Vol", "CE_OI", "PE_OI", 
                    "CE_IV", "PE_IV", "Net_GEX"
                ]].style.format({
                    "Strike": "{:.0f}",
                    "CE_Vol": "{:,.0f}",
                    "PE_Vol": "{:,.0f}",
                    "CE_OI": "{:,.0f}",
                    "PE_OI": "{:,.0f}",
                    "CE_IV": "{:.1f}%",
                    "PE_IV": "{:.1f}%",
                    "Net_GEX": "{:+,.0f}"
                }),
                use_container_width=True,
                height=400,
                hide_index=True
            )
        else:
            st.info("✅ No unusual activity detected. Volume patterns are within normal ranges.")

    # TAB 7: DATA GRID
    with tab7:
        st.markdown("### 📋 Institutional Options Chain Grid")
        grid_df = df_filtered[[
            "Strike", "CE_LTP", "PE_LTP", "CE_OI", "PE_OI", 
            "CE_GEX", "PE_GEX", "Net_GEX", 
            "CE_Delta", "PE_Delta", "Net_Delta_OI", "Net_DEX", 
            "CE_IV", "PE_IV", "IV_Spread"
        ]].copy()
        
        st.dataframe(
            grid_df.style.format({
                "Strike": "{:.0f}", 
                "CE_LTP": "₹{:.2f}", 
                "PE_LTP": "₹{:.2f}", 
                "CE_OI": "{:,.0f}", 
                "PE_OI": "{:,.0f}", 
                "CE_GEX": "{:,.0f}", 
                "PE_GEX": "{:,.0f}", 
                "Net_GEX": "{:+,.0f}", 
                "CE_Delta": "{:.2f}", 
                "PE_Delta": "{:.2f}", 
                "Net_Delta_OI": "{:+,.0f}", 
                "Net_DEX": "{:+,.1f}L", 
                "CE_IV": "{:.1f}%", 
                "PE_IV": "{:.1f}%", 
                "IV_Spread": "{:+.2f}%"
            }),
            use_container_width=True, 
            height=500,
            hide_index=True
        )

    # Footer
    st.markdown("<br><hr style='border-color: rgba(99, 179, 237, 0.3);'>", unsafe_allow_html=True)
    st.markdown(
        "<div style='text-align: center; color: #A0AEC0; font-size: 0.75rem;'>"
        "Prince PAX Institutional Volatility Terminal v3.0 | OpenBull GEX Model | "
        "Powered by Advanced Mathematical Engine"
        "</div>", 
        unsafe_allow_html=True
    )

if __name__ == "__main__":
    main()
