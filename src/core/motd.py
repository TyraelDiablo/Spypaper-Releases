"""MOTD yaş etiketi: sunucu listesinde açıklamanın başına "[13+]" gibi renkli bir etiket koyar.

server.properties'te § işareti "\\u00A7" kaçışıyla yazılır (vanilla da böyle yazar; dosya kodlaması ne olursa olsun
doğru okunur). Etiket dilden bağımsızdır (rakam + "+"), oyuncu hangi dilde oynarsa oynasın aynı görünür.
"""
import re

AGES = ["3+", "7+", "12+", "13+", "16+", "18+"]
_COLOR = {"3+": "a", "7+": "a", "12+": "e", "13+": "e", "16+": "6", "18+": "c"}
_S = r"(?:§|\\u00[aA]7)"
TAG_RE = re.compile(rf"^{_S}[0-9a-fA-Fk-oK-OrR]\[(\d{{1,2}}\+)\]{_S}[rR] ?")


def split(raw):
    """'\\u00A7e[13+]\\u00A7r Sunucum' -> ('13+', 'Sunucum'). Etiket yoksa ('', raw)."""
    raw = raw or ""
    m = TAG_RE.match(raw)
    if m and m.group(1) in AGES:
        return m.group(1), raw[m.end():]
    return "", raw


def compose(age, rest):
    rest = split(rest)[1]                       # iki kez etiket eklenmesin
    if age not in AGES:
        return rest
    return f"\\u00A7{_COLOR[age]}[{age}]\\u00A7r " + rest


_MC = {"0": "#000000", "1": "#0000AA", "2": "#00AA00", "3": "#00AAAA", "4": "#AA0000", "5": "#AA00AA",
       "6": "#FFAA00", "7": "#AAAAAA", "8": "#555555", "9": "#5555FF", "a": "#55FF55", "b": "#55FFFF",
       "c": "#FF5555", "d": "#FF55FF", "e": "#FFFF55", "f": "#FFFFFF"}


def to_html(raw, default="#AAAAAA"):
    """Sunucu listesindeki görünümü taklit eden HTML (renk, kalın, italik, altı/üstü çizili; \\n satır sonu)."""
    import html
    s = re.sub(r"\\u00[aA]7", "§", raw or "").replace("\\n", "\n")
    out, buf, col, fmt = [], [], default, set()

    def flush():
        if buf:
            text = html.escape("".join(buf)).replace("\n", "<br>")
            style = [f"color:{col}"]
            if "l" in fmt: style.append("font-weight:bold")
            if "o" in fmt: style.append("font-style:italic")
            deco = [d for k, d in (("n", "underline"), ("m", "line-through")) if k in fmt]
            if deco: style.append("text-decoration:" + " ".join(deco))
            out.append(f'<span style="{";".join(style)}">{text}</span>')
            buf.clear()
    i = 0
    while i < len(s):
        if s[i] == "§" and i + 1 < len(s):
            c = s[i + 1].lower()
            flush()
            if c in _MC:
                col, fmt = _MC[c], set()
            elif c == "r":
                col, fmt = default, set()
            elif c in "lomnk":
                fmt.add(c)
            i += 2
            continue
        buf.append(s[i])
        i += 1
    flush()
    return "".join(out)
