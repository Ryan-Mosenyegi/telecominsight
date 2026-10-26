"""Shared look and feel for both sites (provider site and admin site)."""
import streamlit as st

PURPLE, ROYAL_BLUE, LIGHT_PURPLE = "#7057D9", "#245DB8", "#F3F0FF"
INK, MUTED, BORDER, PAGE, CYAN = "#20283A", "#697386", "#E4E8F0", "#F8FAFD", "#16A6A1"
SCALE = ["#DCD5FF", PURPLE, ROYAL_BLUE]


def inject_css() -> None:
    st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@400;500;600;700;800&display=swap');
.stApp {{ background:{PAGE}; color:{INK}; font-family:'DM Sans',sans-serif; }}
[data-testid="stHeader"] {{ background:rgba(248,250,253,.94); }}
[data-testid="stSidebar"] {{ background:#fff; border-right:1px solid {BORDER}; }}
.block-container {{ padding-top:2rem; padding-bottom:3rem; max-width:1500px; }}
h1,h2,h3 {{ font-family:'Manrope','DM Sans',sans-serif; color:{INK}; letter-spacing:-.45px; }}
h1 {{ letter-spacing:-1.1px; font-weight:800; }}
.brand-lockup {{ display:flex; align-items:center; gap:12px; padding:8px 0 16px; }}
.brand-mark {{ display:flex; align-items:center; justify-content:center; width:44px; height:44px; border-radius:13px;
  background:linear-gradient(135deg,{PURPLE},{ROYAL_BLUE}); color:#fff; font-size:23px; }}
.brand-name {{ font-family:'Manrope',sans-serif; font-size:18px; font-weight:800; line-height:1.15; }}
.brand-subtitle {{ color:{MUTED}; font-size:10px; margin-top:4px; letter-spacing:1px; text-transform:uppercase; }}
.eyebrow {{ color:{PURPLE}; font-size:11px; letter-spacing:1.8px; font-weight:800; text-transform:uppercase; margin-bottom:8px; }}
.hero-subtitle {{ color:{MUTED}; font-size:15px; margin-top:-8px; margin-bottom:20px; }}
.section-label {{ color:{MUTED}; text-transform:uppercase; font-size:11px; letter-spacing:1.5px; font-weight:800; margin:12px 0 8px; }}
div[data-testid="stMetric"] {{ background:#fff; border:1px solid {BORDER}; border-radius:16px; padding:16px 18px;
  box-shadow:0 4px 14px rgba(31,45,75,.035); min-height:112px; }}
div[data-testid="stMetricLabel"] {{ color:{MUTED}; font-size:12px; font-weight:600; }}
div[data-testid="stMetricValue"] {{ font-family:'Manrope',sans-serif; font-weight:800; font-size:27px; }}
div[data-testid="stPlotlyChart"] {{ background:#fff; border:1px solid {BORDER}; border-radius:16px; padding:8px 8px 0; }}
.info-banner {{ background:{LIGHT_PURPLE}; border:1px solid #DED7FF; border-left:4px solid {PURPLE}; border-radius:10px;
  padding:12px 15px; color:#4E428B; font-size:12px; margin:14px 0 22px; }}
.footer-note {{ color:{MUTED}; font-size:11px; text-align:center; padding-top:28px; }}
.stButton button,.stDownloadButton button {{ border-radius:9px; border:1px solid {ROYAL_BLUE}; background:{ROYAL_BLUE}; color:#fff; font-weight:700; }}
.stButton button:hover,.stDownloadButton button:hover {{ border-color:{PURPLE}; background:{PURPLE}; color:#fff; }}
</style>""", unsafe_allow_html=True)


def brand_lockup(subtitle: str) -> str:
    """The logo block at the top of the sidebar."""
    return f"""<div class="brand-lockup"><div class="brand-mark">📡</div><div>
        <div class="brand-name">TelecomInsight BW</div><div class="brand-subtitle">{subtitle}</div>
        </div></div>"""