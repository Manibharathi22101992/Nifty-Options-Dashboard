import plotly.graph_objects as go
from plotly.subplots import make_subplots
from config import config

PLOT_CONFIG = {'displayModeBar': True, 'scrollZoom': False}

def apply_terminal_layout(fig, df=None, spot=None):
    fig.update_layout(
        template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=20, b=10), legend=dict(orientation="h", y=1.1, x=0, font=dict(size=10))
    )
    if df is not None and spot is not None:
        fig.update_xaxes(tickmode='array', tickvals=df["Strike"], ticktext=df["Strike"].astype(str), tickangle=-45)
        fig.add_vline(x=spot, line_dash="solid", line_color=config.COLORS['amber'], opacity=0.8)
    fig.update_xaxes(gridcolor=config.COLORS['border'], zerolinecolor=config.COLORS['border'])
    fig.update_yaxes(gridcolor=config.COLORS['border'], zerolinecolor=config.COLORS['border'])
    return fig

def plot_exposure_profile(df, title, ce_col, pe_col, net_col, abs_col=None, spot=None, flip=None):
    fig = go.Figure()
    fig.add_trace(go.Bar(x=df["Strike"], y=df[pe_col], name="Put", marker_color=config.COLORS['red'], opacity=0.8))
    fig.add_trace(go.Bar(x=df["Strike"], y=df[ce_col], name="Call", marker_color=config.COLORS['green'], opacity=0.8))
    if net_col:
        fig.add_trace(go.Scatter(x=df["Strike"], y=df[net_col], mode="lines", name="Net Exposure", line=dict(color=config.COLORS['text_main'], width=2)))
    if abs_col:
        fig.add_trace(go.Scatter(x=df["Strike"], y=df[abs_col], mode="lines", name="Abs Exposure", line=dict(color=config.COLORS['blue'], width=2, dash='dot')))
    
    fig = apply_terminal_layout(fig, df, spot)
    if flip is not None: fig.add_vline(x=flip, line_dash="dash", line_color=config.COLORS['blue'], annotation_text=f"Flip: {flip:.0f}")
    return fig
