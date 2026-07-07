from datetime import datetime
from zoneinfo import ZoneInfo


def market_is_open():

    now = datetime.now(
        ZoneInfo("America/Chicago")
    )

    # Saturday/Sunday
    if now.weekday() >= 5:
        return False

    current_minutes = (
        now.hour * 60
        + now.minute
    )

    open_minutes = 8 * 60 + 30   # 8:30 AM CT
    close_minutes = 15 * 60      # 3:00 PM CT

    return (
        open_minutes
        <= current_minutes
        <= close_minutes
    )