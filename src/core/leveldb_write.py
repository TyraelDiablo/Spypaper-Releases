"""Bedrock dünya veritabanına (LevelDB) tek bir anahtar yazmak: güncel .log dosyasına yeni bir yazma grubu eklenir.

Yalnızca sunucu KAPALIYKEN kullanılır (açıkken veritabanı kilitlidir ve sunucu kendi kopyasını yazar).
Sıra numarası, veritabanındaki en büyük sıra numarasından büyük seçilir; böylece açılışta bu değer kazanır.
"""
import os
import re
import struct

from . import leveldb_ro as L

BLOCK = 32768
_TABLE = []


def _crc32c(data):
    global _TABLE
    if not _TABLE:
        for i in range(256):
            c = i
            for _ in range(8):
                c = (c >> 1) ^ 0x82F63B78 if c & 1 else c >> 1
            _TABLE.append(c)
    crc = 0xFFFFFFFF
    for byte in data:
        crc = _TABLE[(crc ^ byte) & 0xFF] ^ (crc >> 8)
    return crc ^ 0xFFFFFFFF


def _mask(crc):
    return ((((crc >> 15) | (crc << 17)) & 0xFFFFFFFF) + 0xA282EAD8) & 0xFFFFFFFF


def _varint(n):
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def _manifest(dbdir):
    """(log numarası, son sıra no)"""
    try:
        with open(os.path.join(dbdir, "CURRENT"), encoding="ascii") as f:
            name = f.read().strip()
        with open(os.path.join(dbdir, name), "rb") as f:
            data = f.read()
    except OSError:
        return None, 0
    log_no, last_seq = None, 0
    for rec in L._log_records(data):
        p = 0
        try:
            while p < len(rec):
                tag, p = L._varint(rec, p)
                if tag == 1:                          # comparator
                    n, p = L._varint(rec, p)
                    p += n
                elif tag in (2, 3, 4, 9):             # log no, next file, last seq, prev log
                    v, p = L._varint(rec, p)
                    if tag == 2:
                        log_no = v
                    elif tag == 4:
                        last_seq = max(last_seq, v)
                elif tag == 5:                        # compact pointer
                    _lvl, p = L._varint(rec, p)
                    n, p = L._varint(rec, p)
                    p += n
                elif tag == 6:                        # deleted file
                    _lvl, p = L._varint(rec, p)
                    _f, p = L._varint(rec, p)
                elif tag == 7:                        # new file
                    _lvl, p = L._varint(rec, p)
                    _f, p = L._varint(rec, p)
                    _sz, p = L._varint(rec, p)
                    n, p = L._varint(rec, p)
                    p += n
                    n, p = L._varint(rec, p)
                    p += n
                else:
                    break
        except L.LevelDBError:
            pass
    return log_no, last_seq


def max_sequence(dbdir):
    _log, best = _manifest(dbdir)
    for n in os.listdir(dbdir):
        path = os.path.join(dbdir, n)
        if re.fullmatch(r"\d+\.(ldb|sst)", n):
            try:
                for ikey, _v in L.read_table(path):
                    if len(ikey) >= 8:
                        best = max(best, struct.unpack_from("<Q", ikey, len(ikey) - 8)[0] >> 8)
            except Exception:
                pass
        elif re.fullmatch(r"\d+\.log", n):
            with open(path, "rb") as f:
                for rec in L._log_records(f.read()):
                    if len(rec) >= 12:
                        seq, cnt = struct.unpack_from("<QI", rec, 0)
                        best = max(best, seq + cnt - 1)
    return best


def _log_file(dbdir):
    log_no, _ = _manifest(dbdir)
    if log_no is not None and os.path.isfile(os.path.join(dbdir, f"{log_no:06d}.log")):
        return os.path.join(dbdir, f"{log_no:06d}.log")
    logs = sorted((int(m.group(1)), n) for n in os.listdir(dbdir) for m in [re.fullmatch(r"(\d+)\.log", n)] if m)
    if not logs:
        raise OSError("LevelDB log dosyası yok")
    return os.path.join(dbdir, logs[-1][1])


def put(dbdir, key, value):
    seq = max_sequence(dbdir) + 1
    batch = struct.pack("<QI", seq, 1) + b"\x01" + _varint(len(key)) + key + _varint(len(value)) + value
    path = _log_file(dbdir)
    pos = os.path.getsize(path)
    out = bytearray()
    data, first = batch, True
    while True:
        left = BLOCK - pos % BLOCK
        if left < 7:                                   # blok sonu: sıfır dolgu
            out += b"\x00" * left
            pos += left
            left = BLOCK
        avail = left - 7
        frag = data[:avail]
        data = data[avail:]
        end = not data
        rtype = 1 if first and end else 2 if first else 4 if end else 3
        crc = _mask(_crc32c(bytes([rtype]) + frag))
        out += struct.pack("<IHB", crc, len(frag), rtype) + frag
        pos += 7 + len(frag)
        first = False
        if end:
            break
    with open(path, "ab") as f:
        f.write(out)
    return seq
