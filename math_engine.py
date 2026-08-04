import numpy as np
import pandas as pd
from scipy.stats import norm
from config import config, get_logger

logger = get_logger("MathEngine")

def calculate_greeks_vectorized(S, K, T, iv_ce, iv_pe, r=config.RISK_FREE_RATE, q=config.NIFTY_DIVIDEND_YIELD):
    """Vectorized Black-Scholes Greeks including dividend yield and convexity metrics."""
    T = np.maximum(T, 1e-5)
    iv_ce = np.maximum(iv_ce, 1e-4)
    iv_pe = np.maximum(iv_pe, 1e-4)
    
    d1_ce = (np.log(S / K) + (r - q + 0.5 * iv_ce**2) * T) / (iv_ce * np.sqrt(T))
    d2_ce = d1_ce - iv_ce * np.sqrt(T)
    pdf_ce, cdf_ce = norm.pdf(d1_ce), norm.cdf(d1_ce)
    
    d1_pe = (np.log(S / K) + (r - q + 0.5 * iv_pe**2) * T) / (iv_pe * np.sqrt(T))
    d2_pe = d1_pe - iv_pe * np.sqrt(T)
    pdf_pe, cdf_pe = norm.pdf(d1_pe), norm.cdf(d1_pe)
    
    exp_qT = np.exp(-q * T)
    
    # Core Greeks
    ce_delta = exp_qT * cdf_ce
    pe_delta = exp_qT * (cdf_pe - 1.0)
    gamma = exp_qT * pdf_ce / (S * iv_ce * np.sqrt(T)) # Gamma is identical for CE/PE
    
    ce_vega = S * exp_qT * pdf_ce * np.sqrt(T) / 100.0
    pe_vega = S * exp_qT * pdf_pe * np.sqrt(T) / 100.0
    
    # Second-Order Greeks
    ce_vanna = -exp_qT * pdf_ce * d2_ce / iv_ce
    pe_vanna = -exp_qT * pdf_pe * d2_pe / iv_pe
    
    ce_charm = q * exp_qT * cdf_ce - exp_qT * pdf_ce * (2 * (r - q) * T - d2_ce * iv_ce * np.sqrt(T)) / (2 * T * iv_ce * np.sqrt(T))
    pe_charm = ce_charm - q * exp_qT
    
    # Third-Order Greeks (Corrected Speed formula)
    ce_speed = -exp_qT * pdf_ce / (S**2 * iv_ce * np.sqrt(T)) * (1.0 + d1_ce / (iv_ce * np.sqrt(T)))
    pe_speed = -exp_qT * pdf_pe / (S**2 * iv_pe * np.sqrt(T)) * (1.0 + d1_pe / (iv_pe * np.sqrt(T)))
    
    ce_vomma = ce_vega * d1_ce * d2_ce / iv_ce
    pe_vomma = pe_vega * d1_pe * d2_pe / iv_pe
    
    return ce_delta, pe_delta, gamma, ce_vega, pe_vega, ce_vanna, pe_vanna, ce_charm, pe_charm, ce_speed, pe_speed, ce_vomma, pe_vomma

def calculate_forward_price(S, df: pd.DataFrame, T):
    """Calculates true Synthetic Forward via Put-Call Parity: F = K + (C-P)*e^(rT)"""
    if df.empty: return S
    diffs = (df['Strike'] - S).abs()
    closest = df.loc[diffs.nsmallest(3).index]
    
    fwd_array = closest['Strike'] + (closest['CE_LTP'] - closest['PE_LTP']) * np.exp(config.RISK_FREE_RATE * T)
    weights = 1.0 / np.maximum(abs(closest['Strike'] - S), 1.0)
    return np.average(fwd_array, weights=weights)

def interpolate_gamma_flip(df: pd.DataFrame):
    """Accurate linear interpolation for Gamma zero-crossing."""
    df_s = df.sort_values("Strike")
    cum_gex = df_s["Net_GEX"].cumsum().values
    strikes = df_s["Strike"].values
    
    crossings = np.where(np.diff(np.sign(cum_gex)))[0]
    if len(crossings) > 0:
        idx = crossings[0]
        y1, y2 = cum_gex[idx], cum_gex[idx+1]
        x1, x2 = strikes[idx], strikes[idx+1]
        if y2 != y1: return x1 - y1 * (x2 - x1) / (y2 - y1)
        return (x1 + x2) / 2.0
    return strikes[len(strikes)//2] if len(strikes) > 0 else 0.0
