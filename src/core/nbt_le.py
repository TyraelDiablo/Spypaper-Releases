"""Küçük-uçlu (little-endian) NBT okuyucu: Bedrock'un level.dat ve veritabanı kayıtları için. Salt okunur."""
import struct


class NBTError(Exception):
    pass


def _str(b, p):
    n = struct.unpack_from("<H", b, p)[0]
    p += 2
    return b[p:p + n].decode("utf-8", "replace"), p + n


def _payload(t, b, p):
    if t == 1:
        return struct.unpack_from("<b", b, p)[0], p + 1
    if t == 2:
        return struct.unpack_from("<h", b, p)[0], p + 2
    if t == 3:
        return struct.unpack_from("<i", b, p)[0], p + 4
    if t == 4:
        return struct.unpack_from("<q", b, p)[0], p + 8
    if t == 5:
        return struct.unpack_from("<f", b, p)[0], p + 4
    if t == 6:
        return struct.unpack_from("<d", b, p)[0], p + 8
    if t == 7:
        n = struct.unpack_from("<i", b, p)[0]
        return bytes(b[p + 4:p + 4 + n]), p + 4 + n
    if t == 8:
        return _str(b, p)
    if t == 9:
        et, n = struct.unpack_from("<bi", b, p)
        p += 5
        out = []
        for _ in range(max(0, n)):
            v, p = _payload(et, b, p)
            out.append(v)
        return out, p
    if t == 10:
        out = {}
        while True:
            ct = b[p]
            p += 1
            if ct == 0:
                return out, p
            name, p = _str(b, p)
            out[name], p = _payload(ct, b, p)
    if t == 11:
        n = struct.unpack_from("<i", b, p)[0]
        return list(struct.unpack_from(f"<{n}i", b, p + 4)), p + 4 + 4 * n
    if t == 12:
        n = struct.unpack_from("<i", b, p)[0]
        return list(struct.unpack_from(f"<{n}q", b, p + 4)), p + 4 + 8 * n
    raise NBTError(f"bilinmeyen etiket {t}")


def loads(b, offset=0):
    """Tek bir kök etiketi okur: (ad, değer)."""
    try:
        t = b[offset]
        name, p = _str(b, offset + 1)
        val, _ = _payload(t, b, p)
        return name, val
    except (IndexError, struct.error) as e:
        raise NBTError(str(e))


def read_level_dat(path):
    """level.dat: 8 baytlık başlık (sürüm, uzunluk) + NBT."""
    with open(path, "rb") as f:
        data = f.read()
    return loads(data, 8)[1]


def locate(b, offset=0):
    """Kök bileşiğin yaprak değerlerinin konumları: {('abilities','build'): (etiket, bayt_konumu)}.
    Uzunluğu değişmeyen değerleri (byte/int/float) yerinde değiştirmek için."""
    out = {}

    def walk(t, p, path):
        if t == 10:
            while True:
                ct = b[p]
                p += 1
                if ct == 0:
                    return p
                name, p = _str(b, p)
                out[path + (name,)] = (ct, p)
                p = walk(ct, p, path + (name,))
        _v, p2 = _payload(t, b, p)
        return p2

    t = b[offset]
    _name, p = _str(b, offset + 1)
    walk(t, p, ())
    return out


SIZES = {1: ("<b", 1), 2: ("<h", 2), 3: ("<i", 4), 4: ("<q", 8), 5: ("<f", 4), 6: ("<d", 8)}


def patch(b, changes):
    """changes: {yol: yeni_değer}. Yalnızca sayısal yaprakları yerinde değiştirir; yeni bytes döndürür."""
    buf = bytearray(b)
    where = locate(b)
    for path, val in changes.items():
        if path not in where:
            raise NBTError(f"alan yok: {'/'.join(path)}")
        tag, pos = where[path]
        if tag not in SIZES:
            raise NBTError(f"sayısal değil: {'/'.join(path)}")
        fmt, _n = SIZES[tag]
        struct.pack_into(fmt, buf, pos, val)
    return bytes(buf)
