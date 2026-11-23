"""Ölçü birimleri: metrik (m, km) ya da imparatorluk (ft, mi). Minecraft'ta 1 blok = 1 metre."""
SYSTEM = {"value": "metric"}
FT = 3.28084
MI = 1609.344


def set_system(v):
    SYSTEM["value"] = "imperial" if v == "imperial" else "metric"


def imperial():
    return SYSTEM["value"] == "imperial"


def _num(v, nd):
    s = f"{v:,.{nd}f}"
    return s.rstrip("0").rstrip(".") if "." in s else s


def distance(meters):
    """Uzun mesafe (yürünen yol): 1,2 km / 0,7 mi; kısa ise m / ft."""
    if imperial():
        return f"{_num(meters / MI, 1)} mi" if meters >= MI / 10 else f"{_num(meters * FT, 0)} ft"
    return f"{_num(meters / 1000, 1)} km" if meters >= 1000 else f"{_num(meters, 0)} m"


def length(blocks):
    """Blok sayısının gerçek uzunluğu: 300 blok -> '300 m' / '984 ft' (1 blok = 1 m)."""
    if imperial():
        return f"{_num(blocks * FT, 0)} ft"
    return f"{_num(blocks, 0)} m" if blocks < 1000 else f"{_num(blocks / 1000, 2)} km"
