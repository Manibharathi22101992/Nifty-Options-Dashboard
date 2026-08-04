import os
import logging
from dataclasses import dataclass
import streamlit as st

@dataclass
class AppConfig:
    CLIENT_ID: str = st.secrets.get("DHAN_CLIENT_ID", "")
    ACCESS_TOKEN: str = st.secrets.get("DHAN_ACCESS_TOKEN", "")
    TELEGRAM_BOT_TOKEN: str = st.secrets.get("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID: str = st.secrets.get("TELEGRAM_CHAT_ID", "")
    
    NIFTY_LOT_SIZE: int = 65
    NIFTY_DIVIDEND_YIELD: float = 0.012  # 1.2% Nifty Yield
    RISK_FREE_RATE: float = 0.07         # 7.0% Risk Free Rate
    
    # Standardized Terminal Colors
    COLORS = {
        "bg": "#0A0A0A", "panel": "#14151A", "border": "#2A2E39",
        "green": "#00E676", "red": "#FF5252", "amber": "#FFD700", 
        "blue": "#29B6F6", "text_main": "#FFFFFF", "text_muted": "#8A93A6"
    }

config = AppConfig()

def get_logger(name: str):
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - [%(levelname)s] - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger
