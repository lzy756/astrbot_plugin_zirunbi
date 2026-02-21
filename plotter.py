import mplfinance as mpf
import pandas as pd
import io
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
import os

try:
    from astrbot.api import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PLUGIN_FONT = os.path.join("fonts", "SourceHanSansSC-Regular.otf")
FALLBACK_FONT_FAMILIES = [
    "SimHei",
    "Arial Unicode MS",
    "Microsoft YaHei",
    "WenQuanYi Micro Hei",
    "sans-serif",
]

try:
    from mplfonts.bin.cli import init
    init()
    from mplfonts import use_font
    use_font('Noto Sans CJK SC')
except Exception as e:
    logger.warning(f"mplfonts init failed: {e}. Chinese characters might not display correctly.")
    # Fallback: Try common Chinese fonts
    plt.rcParams['font.sans-serif'] = FALLBACK_FONT_FAMILIES
    plt.rcParams['axes.unicode_minus'] = False

# Global font prop
_custom_font_prop = None

def init_font(font_path=None):
    global _custom_font_prop

    candidate_paths = []
    clean_path = (font_path or "").strip()

    if clean_path:
        candidate_paths.append(clean_path)
        if not os.path.isabs(clean_path):
            candidate_paths.append(os.path.join(PLUGIN_DIR, clean_path))
    else:
        candidate_paths.append(os.path.join(PLUGIN_DIR, DEFAULT_PLUGIN_FONT))

    resolved_path = None
    for path in candidate_paths:
        if path and os.path.isfile(path):
            resolved_path = path
            break

    if not resolved_path:
        logger.warning(
            f"Font file not found for path='{clean_path}'. "
            "Using mplfonts/system fallback."
        )
        plt.rcParams['font.sans-serif'] = FALLBACK_FONT_FAMILIES
        plt.rcParams['axes.unicode_minus'] = False
        return

    try:
        fm.fontManager.addfont(resolved_path)
        _custom_font_prop = fm.FontProperties(fname=resolved_path)
        custom_font_name = _custom_font_prop.get_name()
        plt.rcParams['font.family'] = 'sans-serif'
        plt.rcParams['font.sans-serif'] = [custom_font_name] + FALLBACK_FONT_FAMILIES
        plt.rcParams['axes.unicode_minus'] = False
        logger.info(f"Loaded custom font: {custom_font_name} ({resolved_path})")
    except Exception as e:
        logger.error(f"Failed to load custom font '{resolved_path}': {e}")
        plt.rcParams['font.sans-serif'] = FALLBACK_FONT_FAMILIES
        plt.rcParams['axes.unicode_minus'] = False

def plot_kline(history_data, title="K-Line"):
    if not history_data:
        return None
        
    data = []
    for h in history_data:
        # Ensure timestamp is formatted correctly
        ts = h.timestamp.strftime('%Y-%m-%d %H:%M')
        data.append({
            'Date': ts,
            'Open': h.open,
            'High': h.high,
            'Low': h.low,
            'Close': h.close,
            'Volume': h.volume
        })
    
    df = pd.DataFrame(data)
    # Convert 'Date' to datetime index
    df.index = pd.DatetimeIndex(df['Date'])
    
    buf = io.BytesIO()
    # Use non-interactive backend
    plt.switch_backend('Agg')
    
    # Custom Style: Red for Up, Green for Down (China Standard)
    mc = mpf.make_marketcolors(up='r', down='g', edge='i', wick='i', volume='in', inherit=True)
    s = mpf.make_mpf_style(marketcolors=mc, gridstyle='--', y_on_right=True)
    
    try:
        # Use returnfig=True to allow adding text
        # datetime_format ensures X-axis is readable
        fig, axlist = mpf.plot(df, type='candle', style=s, title=title, volume=True, 
                               datetime_format='%m-%d %H:%M', returnfig=True)
        
        # Add Legend/Explanation in Chinese
        ax = axlist[0]
        legend_text = "图例说明:\n🟥 红色: 涨 (Up)\n🟩 绿色: 跌 (Down)\nO:开盘 H:最高\nL:最低 C:收盘"
        
        # Add text box at top left
        ax.text(0.02, 0.98, legend_text, transform=ax.transAxes, fontsize=9, 
                verticalalignment='top', bbox=dict(boxstyle='round', facecolor='white', alpha=0.9))
        
        fig.savefig(buf, format='png', bbox_inches='tight')
        buf.seek(0)
        plt.close(fig)
        return buf
    except Exception as e:
        logger.error(f"Plot error: {e}")
        return None

def plot_holdings_multi(balance, holdings_data, title="User Holdings"):
    """
    holdings_data: dict {symbol: value}
    """
    labels = ['Cash']
    sizes = [balance]
    
    for sym, val in holdings_data.items():
        labels.append(sym)
        sizes.append(val)
    
    # Avoid empty pie if all are 0
    if sum(sizes) < 0.001:
        sizes = [1]
        labels = ['Empty']

    plt.switch_backend('Agg')
    fig, ax = plt.subplots()
    ax.pie(sizes, labels=labels, autopct='%1.1f%%', shadow=True, startangle=90)
    ax.axis('equal')
    
    plt.title(title)
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close(fig)
    return buf
