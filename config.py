"""
config.py
Professional configuration module for the NIFTY Options Dashboard.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Dict

import streamlit as st


# ==========================================================
# Helpers
# ==========================================================

def _secret(key: str, default: str = "") -> str:
    """
    Read configuration from Streamlit secrets first,
    then fall back to environment variables.
    """
    try:
        value = st.secrets.get(key)
        if value:
            return str(value)
    except Exception:
        pass

    return os.getenv(key, default)


# ==========================================================
# Application Configuration
# ==========================================================

@dataclass(slots=True)
class AppConfig:

    # ------------------------------------------------------
    # Metadata
    # ------------------------------------------------------

    APP_NAME: str = "Professional NIFTY Options Dashboard"
    VERSION: str = "2.0.0"

    # ------------------------------------------------------
    # API Credentials
    # ------------------------------------------------------

    CLIENT_ID: str = field(default_factory=lambda: _secret("DHAN_CLIENT_ID"))
    ACCESS_TOKEN: str = field(default_factory=lambda: _secret("DHAN_ACCESS_TOKEN"))

    TELEGRAM_BOT_TOKEN: str = field(default_factory=lambda: _secret("TELEGRAM_BOT_TOKEN"))
    TELEGRAM_CHAT_ID: str = field(default_factory=lambda: _secret("TELEGRAM_CHAT_ID"))

    # ------------------------------------------------------
    # Quant Settings
    # ------------------------------------------------------

    NIFTY_LOT_SIZE: int = 65

    RISK_FREE_RATE: float = 0.070

    DIVIDEND_YIELD: float = 0.012

    DAYS_IN_YEAR: int = 365

    MIN_IV: float = 0.01

    MAX_IV: float = 5.00

    # ------------------------------------------------------
    # Performance
    # ------------------------------------------------------

    CACHE_TTL: int = 15

    API_TIMEOUT: int = 10

    API_RETRIES: int = 3

    MAX_WORKERS: int = 6

    # ------------------------------------------------------
    # UI
    # ------------------------------------------------------

    PAGE_TITLE: str = "NIFTY Professional Dashboard"

    PAGE_ICON: str = "📈"

    LAYOUT: str = "wide"

    SIDEBAR_STATE: str = "expanded"

    PLOT_HEIGHT: int = 700

    # ------------------------------------------------------
    # Professional Trading Terminal Colors
    # ------------------------------------------------------

    COLORS: Dict[str, str] = field(
        default_factory=lambda: {

            "background": "#0B0F14",

            "panel": "#151A21",

            "panel_secondary": "#1C2128",

            "border": "#2D3748",

            "text": "#FFFFFF",

            "text_secondary": "#9AA5B1",

            "bull": "#00E676",

            "bear": "#FF5252",

            "warning": "#FFD54F",

            "info": "#29B6F6",

            "purple": "#7E57C2",

            "orange": "#FB8C00",

            "grid": "#30363D",

        }
    )

    # ------------------------------------------------------
    # Validation
    # ------------------------------------------------------

    def validate(self) -> None:

        missing = []

        if not self.CLIENT_ID:
            missing.append("DHAN_CLIENT_ID")

        if not self.ACCESS_TOKEN:
            missing.append("DHAN_ACCESS_TOKEN")

        if missing:
            raise RuntimeError(
                "Missing configuration values: "
                + ", ".join(missing)
            )


# ==========================================================
# Singleton
# ==========================================================

config = AppConfig()


# ==========================================================
# Logging
# ==========================================================

def get_logger(name: str) -> logging.Logger:

    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    handler = logging.StreamHandler()

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    handler.setFormatter(formatter)

    logger.addHandler(handler)

    logger.propagate = False

    return logger


logger = get_logger(__name__)
