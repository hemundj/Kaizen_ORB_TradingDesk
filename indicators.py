import numpy as np
import pandas as pd

import numpy as np

def calc_atr(df, period=10):
    """
    Average True Range (simplified version for intraday ORB use)
    """

    if len(df) < period:
        return 0

    high = df["h"]
    low = df["l"]
    close = df["c"]

    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = tr.rolling(period).mean().iloc[-1]

    return float(atr) if not np.isnan(atr) else 0

def calc_vwap(df):
    tp = (df["h"] + df["l"] + df["c"]) / 3

    return np.cumsum(tp * df["v"]) / np.cumsum(df["v"])


def orb_levels(df, orb_bars=3):
    first = df.head(orb_bars)

    return (
        first["h"].max(),
        first["l"].min()
    )


def volume_spike(df):

    if len(df) < 10:
        return False

    avg = df["v"].iloc[:-1].mean()

    return df["v"].iloc[-1] > avg * 2

def calculate_volume_ratio(df, lookback=5):

    if len(df) < lookback + 1:
        return 0

    current_vol = df["v"].iloc[-1]
    avg_vol = df["v"].iloc[-lookback:-1].mean()

    if avg_vol <= 0:
        return 0

    return current_vol / avg_vol

def calculate_intraday_rvol(
        current_session_volume,
        average_daily_volume,
        elapsed_market_fraction
):

    if average_daily_volume is None:
        return 0

    if average_daily_volume <= 0:
        return 0

    if elapsed_market_fraction <= 0:
        return 0

    expected_volume_so_far = (
        average_daily_volume
        * elapsed_market_fraction
    )

    if expected_volume_so_far <= 0:
        return 0

    return (
        current_session_volume
        / expected_volume_so_far
    )

def rvol_score(rvol):


    if rvol >= 5:
        return 30

    elif rvol >= 3:
        return 20

    elif rvol >= 2:
        return 10

    elif rvol >= 1.5:
        return 5

    return 0


def near_hod(price, hod):


    if hod <= 0:
        return False

    return ((hod - price) / hod) * 100 <= 2

