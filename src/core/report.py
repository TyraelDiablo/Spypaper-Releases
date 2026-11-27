"""Esplora raporu: sunucunun belli bir dönemdeki durumunun kısa özeti (performans, oyuncular, sicil, yedekler,
disk). Zamanlanmış görev olarak çalışır; <sunucu>/.spypaper/reports/ içine yazılır, açıksa Discord'a da gider.

Yapay zekâ kullanmaz: sayılar Spypaper'ın kendi kayıtlarından (performans geçmişi, log'lar, sicil) çıkar.
Metin `tr` ile panel diline çevrilir.
"""
import os
import re
from datetime import datetime, timedelta

from . import perfhist

KEEP = 60


def folder(server_path):
    return os.path.join(server_path, ".spypaper", "reports")


def _mb(n):
    return f"{n / 1048576:.0f} MB" if n < 1 << 30 else f"{n / (1 << 30):.1f} GB"


def _ram_mb(v):
    v = str(v or "").strip().upper()
    try:
        return int(float(v[:-1]) * 1024) if v.endswith("G") else int(float(v.rstrip("M")))
    except ValueError:
        return 0


def build(app, hours=24, now=None, tr=None):
    """(başlık, satırlar) döndürür."""
    tr = tr or (lambda s, **kw: s.format(**kw) if kw else s)
    now = now or datetime.now()
    since = now - timedelta(hours=hours)
    lines = []
    warn = []

    # performans
    samples = [s for s in app.perfhist.load(hours, now=now) if s[0] >= since]
    tps = perfhist.summary(samples, "tps")
    ram = perfhist.summary(samples, "ram")
    if tps:
        lines.append("[[trending-up]] " + tr("TPS: ortalama {avg}, en düşük {min}", avg=f"{tps[1]:.1f}", min=f"{tps[0]:.1f}"))
        if tps[1] < 18:
            warn.append(tr("Ortalama TPS düşük; sunucu zorlanıyor."))
        bad = [w for w in perfhist.worst_moments(samples, 3) if w[1] < 15]
        for tm, v, pl, _r in bad:
            lines.append("   • " + tr("{time}: TPS {tps} ({n} oyuncu)", time=f"{tm:%d.%m %H:%M}", tps=f"{v:.1f}",
                                       n=pl if pl is not None else "?"))
    else:
        lines.append("[[trending-up]] " + tr("Bu dönemde performans kaydı yok (sunucu kapalıydı)."))
    if ram:
        lines.append("[[cpu]] " + tr("RAM: ortalama {avg}, en yüksek {max}", avg=_mb(ram[1] * 1048576),
                                max=_mb(ram[2] * 1048576)))
        limit = _ram_mb(app.config.get("ram_max"))
        if limit and ram[2] > limit * 0.9:
            warn.append(tr("RAM sınıra yaklaştı; bellek artırmayı düşün."))

    # oyuncular
    evs = [e for e in app.logs.events if e.time >= since]
    for path, d in app.logs.archives():
        if d >= since.date() - timedelta(days=1):
            evs.extend(e for e in app.logs._archive_events(path) if e.time >= since)
    joins = [e for e in evs if e.kind == "join"]
    deaths = sum(1 for e in evs if e.kind == "death")
    players = {e.player for e in joins if not app.bots.is_bot(e.player)}
    peak = perfhist.summary(samples, "players")
    lines.append("[[users]] " + tr("{n} farklı oyuncu, {j} giriş, {d} ölüm", n=len(players), j=len(joins), d=deaths))
    if peak:
        lines.append("   • " + tr("En kalabalık an: {n} oyuncu", n=int(peak[2])))
    crashes = 0
    cdir = os.path.join(app.config.server_path, "crash-reports")
    if os.path.isdir(cdir):
        crashes = sum(1 for f in os.listdir(cdir)
                      if datetime.fromtimestamp(os.path.getmtime(os.path.join(cdir, f))) >= since)
    if crashes:
        warn.append(tr("{n} çökme raporu oluştu.", n=crashes))

    # sicil
    try:
        recs = [r for r in app.sanctions.entries() if r.get("at", "") >= since.isoformat()]
        if recs:
            lines.append("[[scale]] " + tr("Sicil: {n} yeni kayıt", n=len(recs)))
    except Exception:
        pass

    # yedekler + disk
    try:
        bks = app.backups.list()
        if bks:
            last = max(b[2] for b in bks)
            lines.append("[[save]] " + tr("Son yedek: {time}", time=f"{last:%d.%m %H:%M}"))
            if now - last > timedelta(days=2):
                warn.append(tr("İki günden uzun süredir yedek alınmadı."))
        else:
            warn.append(tr("Hiç dünya yedeği yok."))
    except Exception:
        pass
    try:
        import shutil
        free = shutil.disk_usage(app.config.server_path).free
        lines.append("[[hard-drive]] " + tr("Boş disk: {size}", size=_mb(free)))
        if free < 5 << 30:
            warn.append(tr("Diskte 5 GB'tan az yer kaldı."))
    except Exception:
        pass

    if warn:
        lines.append("")
        lines.append("[[triangle-alert]] " + tr("Dikkat:"))
        lines += ["   • " + w for w in warn]
    else:
        lines.append("")
        lines.append("[[circle-check]] " + tr("Her şey yolunda görünüyor."))
    title = tr("Esplora raporu · {name} · {start} – {end}", name=app.config.name,
               start=f"{since:%d.%m %H:%M}", end=f"{now:%d.%m %H:%M}")
    return title, lines


ICON = re.compile(r"\[\[([a-z0-9-]+)\]\] ")


def plain(lines):
    """Dosya ve Discord için: ikon işaretleri ([[ad]]) kaldırılır."""
    return [ICON.sub("", ln) for ln in lines]


def html(title, lines, img):
    """Panel için zengin metin: [[ad]] -> Lucide ikonu (img(ad) bir <img> etiketi döndürür)."""
    from html import escape
    out = [f"<b>{escape(title)}</b><br>"]
    for ln in lines:
        m = ICON.match(ln)
        body = escape(ICON.sub("", ln)).replace("   •", "&nbsp;&nbsp;&nbsp;•")
        out.append((img(m.group(1)) + "&nbsp;" if m else "") + body)
    return "<br>".join(out)


def save(server_path, title, lines, now=None):
    now = now or datetime.now()
    d = folder(server_path)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, f"{now:%Y%m%d_%H%M}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(title + "\n\n" + "\n".join(plain(lines)) + "\n")
    import json
    with open(path[:-4] + ".json", "w", encoding="utf-8") as f:      # panel ikonlu gösterim için
        json.dump({"title": title, "lines": lines}, f, ensure_ascii=False)
    files = sorted(x for x in os.listdir(d) if x.endswith(".txt"))
    for old in files[:-KEEP]:
        for ext in (".txt", ".json"):
            try:
                os.remove(os.path.join(d, old[:-4] + ext))
            except OSError:
                pass
    return path


def load(path):
    """(başlık, satırlar): yanındaki .json varsa ikon işaretleriyle, yoksa düz metinden."""
    import json
    try:
        with open(path[:-4] + ".json", encoding="utf-8") as f:
            d = json.load(f)
        return d["title"], d["lines"]
    except (OSError, ValueError, KeyError):
        with open(path, encoding="utf-8") as f:
            text = f.read().rstrip("\n").split("\n")
        return text[0], text[2:]


def latest(server_path):
    d = folder(server_path)
    if not os.path.isdir(d):
        return None
    files = sorted(x for x in os.listdir(d) if x.endswith(".txt"))
    return os.path.join(d, files[-1]) if files else None
