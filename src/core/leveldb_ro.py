"""Salt okunur LevelDB okuyucu (Bedrock dünya veritabanı: worlds/<dünya>/db).

Mojang'ın LevelDB çatalı: tablo blokları sıkıştırılmamış (0), Snappy (1, desteklenmez), zlib (2) ya da ham deflate (4).
Okuma sırası: .ldb/.sst tabloları (eski) sonra .log (en yeni yazımlar). Aynı anahtarın en son değeri kazanır;
silinen anahtarlar düşer. Çalışan sunucunun dosyalarına dokunmamak için çağıran önce kopyasını almalıdır.
"""
import os
import re
import struct
import zlib

BLOCK = 32768
TABLE_MAGIC = 0xdb4775248b80fb57


class LevelDBError(Exception):
    pass


def _varint(buf, pos):
    shift = result = 0
    while True:
        if pos >= len(buf):
            raise LevelDBError("varint")
        b = buf[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not b & 0x80:
            return result, pos
        shift += 7


# ------------------------------------------------------------------ .log (write-ahead log)
def _log_records(data):
    """Fiziksel kayıtları birleştirip mantıksal kayıtları (yazma grupları) döndürür."""
    out, frag, pos = [], b"", 0
    while pos + 7 <= len(data):
        left = BLOCK - pos % BLOCK
        if left < 7:                       # blok sonu dolgusu
            pos += left
            continue
        _crc, length, rtype = struct.unpack_from("<IHB", data, pos)
        pos += 7
        chunk = data[pos:pos + length]
        pos += length
        if rtype == 0 and length == 0:     # sıfır dolgu
            continue
        if rtype == 1:
            out.append(chunk)
            frag = b""
        elif rtype == 2:
            frag = chunk
        elif rtype == 3:
            frag += chunk
        elif rtype == 4:
            out.append(frag + chunk)
            frag = b""
    return out


def _apply_batch(batch, db):
    if len(batch) < 12:
        return
    _seq, count = struct.unpack_from("<QI", batch, 0)
    pos = 12
    for _ in range(count):
        if pos >= len(batch):
            break
        tag = batch[pos]
        pos += 1
        klen, pos = _varint(batch, pos)
        key = bytes(batch[pos:pos + klen])
        pos += klen
        if tag == 1:
            vlen, pos = _varint(batch, pos)
            db[key] = bytes(batch[pos:pos + vlen])
            pos += vlen
        else:
            db.pop(key, None)


def read_log(path, db):
    with open(path, "rb") as f:
        data = f.read()
    for rec in _log_records(data):
        try:
            _apply_batch(rec, db)
        except LevelDBError:
            break


# ------------------------------------------------------------------ .ldb / .sst tablo
def _block(data, offset, size):
    raw = data[offset:offset + size]
    ctype = data[offset + size] if offset + size < len(data) else 0
    if ctype == 0:
        return raw
    if ctype == 2:
        return zlib.decompress(raw)
    if ctype == 4:
        return zlib.decompress(raw, -15)
    raise LevelDBError(f"sıkıştırma türü {ctype} desteklenmiyor")


def _block_entries(block):
    if len(block) < 4:
        return
    nrest = struct.unpack_from("<I", block, len(block) - 4)[0]
    end = len(block) - 4 - 4 * nrest
    pos, last = 0, b""
    while pos < end:
        shared, pos = _varint(block, pos)
        unshared, pos = _varint(block, pos)
        vlen, pos = _varint(block, pos)
        key = last[:shared] + block[pos:pos + unshared]
        pos += unshared
        val = block[pos:pos + vlen]
        pos += vlen
        last = key
        yield bytes(key), bytes(val)


def read_table(path):
    """[(iç anahtar, değer)] — iç anahtar: kullanıcı anahtarı + 8 bayt (sıra no << 8 | tür)."""
    with open(path, "rb") as f:
        data = f.read()
    if len(data) < 48 or struct.unpack_from("<Q", data, len(data) - 8)[0] != TABLE_MAGIC:
        raise LevelDBError("tablo imzası yok")
    footer = data[-48:]
    pos = 0
    _meta_off, pos = _varint(footer, pos)
    _meta_size, pos = _varint(footer, pos)
    idx_off, pos = _varint(footer, pos)
    idx_size, pos = _varint(footer, pos)
    out = []
    for _k, handle in _block_entries(_block(data, idx_off, idx_size)):
        off, p = _varint(handle, 0)
        size, p = _varint(handle, p)
        out.extend(_block_entries(_block(data, off, size)))
    return out


def _table_files(dbdir):
    """MANIFEST'te geçerli tabloları sıra no'suyla bulmak yerine numaraya göre sıralar (küçük = eski)."""
    files = []
    for n in os.listdir(dbdir):
        m = re.fullmatch(r"(\d+)\.(ldb|sst)", n)
        if m:
            files.append((int(m.group(1)), os.path.join(dbdir, n)))
    return [p for _, p in sorted(files)]


def read_db(dbdir, key_filter=None):
    """{anahtar: değer}. key_filter(bytes)->bool verilirse yalnızca eşleşenler tutulur (bellek için)."""
    best = {}                                   # anahtar -> (sıra no, değer ya da None=silinmiş)
    for path in _table_files(dbdir):
        try:
            entries = read_table(path)
        except (LevelDBError, OSError, zlib.error):
            continue
        for ikey, val in entries:
            if len(ikey) < 8:
                continue
            ukey = ikey[:-8]
            if key_filter and not key_filter(ukey):
                continue
            tag = struct.unpack_from("<Q", ikey, len(ikey) - 8)[0]
            seq, kind = tag >> 8, tag & 0xFF
            if ukey not in best or seq > best[ukey][0]:
                best[ukey] = (seq, val if kind == 1 else None)
    db = {k: v for k, (_, v) in best.items() if v is not None}
    logs = sorted((int(m.group(1)), n) for n in os.listdir(dbdir) for m in [re.fullmatch(r"(\d+)\.log", n)] if m)
    for _, n in logs:                           # log en yeni yazımlar: üzerine yazar / siler
        try:
            read_log(os.path.join(dbdir, n), db)
        except OSError:
            continue
    if key_filter:
        db = {k: v for k, v in db.items() if key_filter(k)}
    return db
