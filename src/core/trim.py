"""Dünya temizliği: oyuncuların neredeyse hiç kalmadığı chunk'ları siler; dünya küçülür, o bölgeler yeniden üretilir.

Her chunk'ta oyunun tuttuğu InhabitedTime (oyuncuların orada geçirdiği toplam tick) okunur. Eşikten az olanlar ve
korunan alanın (doğma noktası çevresi) dışında kalanlar silinir. Bölge dosyaları (.mca) yeniden yazılır, tamamen
boşalanlar silinir. Aynı chunk'ın entities/poi kayıtları da temizlenir. Sunucu kapalıyken çalışır.
"""
import os
import struct
import zlib

from .config import N_

SECTOR = 4096
TAG = b"\x04\x00\x0dInhabitedTime"
TICKS_PER_MIN = 20 * 60


class TrimError(Exception):
    def __init__(self, template, **kw):
        super().__init__(template.format(**kw) if kw else template)
        self.template, self.kw = template, kw


def _inhabited(raw):
    """Sıkıştırılmış chunk verisinden InhabitedTime (tick). Okunamazsa None (silinmez)."""
    if len(raw) < 5:
        return None
    length = struct.unpack(">I", raw[:4])[0]
    kind = raw[4]
    data = raw[5:4 + length]
    try:
        if kind == 2:
            data = zlib.decompress(data)
        elif kind == 1:
            import gzip
            data = gzip.decompress(data)
        elif kind == 3:
            pass
        else:                                   # LZ4 ya da dış dosya (.mcc): dokunma
            return None
    except Exception:
        return None
    i = data.find(TAG)
    if i < 0:
        return None
    return struct.unpack(">q", data[i + len(TAG):i + len(TAG) + 8])[0]


def _read(path):
    with open(path, "rb") as f:
        buf = f.read()
    if len(buf) < 2 * SECTOR:
        return None, buf
    chunks = {}
    for i in range(1024):
        off, cnt = struct.unpack(">I", b"\0" + buf[i * 4:i * 4 + 3])[0], buf[i * 4 + 3]
        if off and cnt:
            chunks[i] = (buf[off * SECTOR:(off + cnt) * SECTOR], buf[SECTOR + i * 4:SECTOR + i * 4 + 4])
    return chunks, buf


def _write(path, chunks):
    """chunks: {indeks: (ham_sektörler, zaman_damgası)} — boşsa dosya silinir. Yazılan bayt sayısını döndürür."""
    if not chunks:
        os.remove(path)
        return 0
    loc, ts = bytearray(SECTOR), bytearray(SECTOR)
    body, sector = bytearray(), 2
    for i in sorted(chunks):
        raw, stamp = chunks[i]
        n = (len(raw) + SECTOR - 1) // SECTOR
        raw = raw + b"\0" * (n * SECTOR - len(raw))
        loc[i * 4:i * 4 + 4] = struct.pack(">I", sector)[1:] + bytes([n])
        ts[i * 4:i * 4 + 4] = stamp
        body += raw
        sector += n
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(loc + ts + body)
    os.replace(tmp, path)
    return 2 * SECTOR + len(body)


def _region_dirs(level_dir):
    for root, dirs, _files in os.walk(level_dir):
        dirs[:] = [d for d in dirs if d not in ("playerdata", "stats", "advancements", "datapacks", "data", "players")]
        if os.path.basename(root) == "region":
            yield root


def plan(server_path, levels, min_minutes=5, keep=(0, 0, 512)):
    """Silinecek chunk'ları bulur, hiçbir şeyi değiştirmez.
    levels: dünya klasörleri (ör. world, world_nether, world_the_end). keep: (merkez_x, merkez_z, yarıçap) korunur.
    Döndürür: {"files": {bölge_yolu: [indeksler]}, "chunks": silinecek, "total": toplam, "free": tahmini_bayt}"""
    limit = min_minutes * TICKS_PER_MIN
    kx, kz, kr = keep
    out, total, gone, free = {}, 0, 0, 0
    for lv in levels:
        base = os.path.join(server_path, lv)
        if not os.path.isdir(base):
            continue
        for rdir in _region_dirs(base):
            for fn in os.listdir(rdir):
                parts = fn.split(".")
                if len(parts) != 4 or parts[0] != "r" or parts[3] != "mca":
                    continue
                try:
                    rx, rz = int(parts[1]), int(parts[2])
                except ValueError:
                    continue
                path = os.path.join(rdir, fn)
                chunks, _ = _read(path)
                if not chunks:
                    continue
                drop = []
                for i, (raw, _st) in chunks.items():
                    total += 1
                    cx, cz = rx * 32 + (i % 32), rz * 32 + (i // 32)
                    bx, bz = cx * 16 + 8, cz * 16 + 8
                    if (bx - kx) ** 2 + (bz - kz) ** 2 <= kr * kr:
                        continue
                    it = _inhabited(raw)
                    if it is not None and it < limit:
                        drop.append(i)
                        free += len(raw)
                if drop:
                    out[path] = drop
                    gone += len(drop)
    return {"files": out, "chunks": gone, "total": total, "free": free}


def apply(server, plan_result, progress=None):
    """Planı uygular. Aynı chunk'ların entities/ ve poi/ kayıtları da silinir. Kazanılan bayt."""
    if server.is_running:
        raise TrimError(N_("Dünya temizliğinden önce sunucuyu durdur."))
    saved = 0
    items = list(plan_result["files"].items())
    for n, (path, drop) in enumerate(items, 1):
        drop = set(drop)
        rdir = os.path.dirname(path)
        dim = os.path.dirname(rdir)
        for sub in ("region", "entities", "poi"):
            p = os.path.join(dim, sub, os.path.basename(path))
            if not os.path.exists(p):
                continue
            before = os.path.getsize(p)
            chunks, _ = _read(p)
            if chunks is None:
                continue
            keep = {i: v for i, v in chunks.items() if i not in drop}
            saved += before - _write(p, keep)
        if progress:
            progress(n, len(items))
    return saved
