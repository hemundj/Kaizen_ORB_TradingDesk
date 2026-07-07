def score_stock(
    rvol,
    gain,
    vwap_ok,
    orb_break,
    hod_break,
    spike,
    vwap_distance=0,
    atr=0,
    price=1
):

    score = 0

    # =========================
    # 1. MOMENTUM (GAIN)
    # =========================
    momentum_score = min(max(gain, -10), 10) * 2
    score += momentum_score

    # =========================
    # 2. RVOL QUALITY (CURVE)
    # =========================
    if rvol >= 3:
        score += 25
    elif rvol >= 2:
        score += 18
    elif rvol >= 1.5:
        score += 12
    elif rvol >= 1:
        score += 6
    else:
        score += 0

    # =========================
    # 3. VWAP STRENGTH (NOT BINARY)
    # =========================
    if vwap_ok:
        if vwap_distance > 5:
            score += 20
        elif vwap_distance > 2:
            score += 15
        else:
            score += 8
    else:
        score -= 10

    # =========================
    # 4. ORB QUALITY
    # =========================
    if orb_break:
        score += 15

    # =========================
    # 5. HOD CONFIRMATION
    # =========================
    if hod_break:
        score += 10

    # =========================
    # 6. SPIKE QUALITY
    # =========================
    if spike:
        score += 10

    # =========================
    # 7. VOLATILITY NORMALIZATION
    # =========================
    if atr > 0 and price > 0:
        vol_factor = min((atr / price) * 100, 5)
        score += vol_factor * 2

    # =========================
    # FINAL CLAMP
    # =========================
    return round(max(0, min(score, 100)), 2)