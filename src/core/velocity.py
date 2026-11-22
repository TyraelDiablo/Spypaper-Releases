"""Velocity proxy: velocity.toml okuma/düzenleme ve arka uç (Paper) sunucularını proxy'ye bağlama.

velocity.toml'u Velocity ilk açılışta yorum satırlarıyla oluşturur; burada yalnızca değiştirdiğimiz satırlara ve
[servers] bölümüne dokunulur, geri kalan her şey (yorumlar dahil) olduğu gibi kalır.
"""
import os
import re
import secrets as _secrets

try:
    import tomllib
except ImportError:          # pragma: no cover
    tomllib = None

from .config import N_

TOML = "velocity.toml"
SECRET = "forwarding.secret"


class VelocityError(Exception):
    def __init__(self, template, **kw):
        super().__init__(template.format(**kw) if kw else template)
        self.template, self.kw = template, kw


def toml_path(proxy_dir):
    return os.path.join(proxy_dir, TOML)


def exists(proxy_dir):
    return os.path.exists(toml_path(proxy_dir))


def load(proxy_dir):
    """{"bind", "motd", "online_mode", "forwarding", "servers": {ad: "host:port"}, "try": [...]}"""
    p = toml_path(proxy_dir)
    if not os.path.exists(p):
        raise VelocityError(N_("velocity.toml henüz yok. Proxy'yi bir kez başlatıp durdur; Velocity dosyayı oluşturur."))
    with open(p, "rb") as f:
        data = tomllib.load(f)
    srv = dict(data.get("servers") or {})
    tries = list(srv.pop("try", []) or [])
    return {
        "bind": str(data.get("bind", "0.0.0.0:25577")),
        "motd": str(data.get("motd", "")),
        "online_mode": bool(data.get("online-mode", True)),
        "forwarding": str(data.get("player-info-forwarding-mode", "none")).lower(),
        "servers": {k: str(v) for k, v in srv.items() if isinstance(v, str)},
        "try": [str(t) for t in tries],
        "forced_hosts": dict(data.get("forced-hosts") or {}),
    }


def _q(s):
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _key(k):
    return k if re.fullmatch(r"[A-Za-z0-9_\-]+", k) else _q(k)


def _set_top(lines, key, value):
    """Üst düzey (ilk [bölüm]'den önceki) 'key = ...' satırını değiştirir ya da ekler."""
    end = next((i for i, l in enumerate(lines) if re.match(r"\s*\[", l)), len(lines))
    for i in range(end):
        if re.match(r"\s*" + re.escape(key) + r"\s*=", lines[i]):
            lines[i] = f"{key} = {value}\n"
            return
    lines.insert(end, f"{key} = {value}\n")


def save(proxy_dir, *, bind=None, motd=None, online_mode=None, forwarding=None, servers=None, try_order=None):
    p = toml_path(proxy_dir)
    with open(p, "r", encoding="utf-8") as f:
        lines = f.readlines()
    if bind is not None:
        _set_top(lines, "bind", _q(bind))
    if motd is not None:
        _set_top(lines, "motd", _q(motd))
    if online_mode is not None:
        _set_top(lines, "online-mode", "true" if online_mode else "false")
    if forwarding is not None:
        _set_top(lines, "player-info-forwarding-mode", _q(forwarding))
    if servers is not None:
        names = list(servers)
        tries = [t for t in (try_order if try_order is not None else names) if t in servers]
        body = ["[servers]\n"] + [f"{_key(k)} = {_q(v)}\n" for k, v in servers.items()]
        body += ["try = [" + ", ".join(_q(t) for t in tries) + "]\n", "\n"]
        start = next((i for i, l in enumerate(lines) if re.match(r"\s*\[servers\]\s*$", l)), None)
        if start is None:
            lines += ["\n"] + body
        else:
            end = next((i for i in range(start + 1, len(lines)) if re.match(r"\s*\[", lines[i])), len(lines))
            # bölümün başındaki yorumları koru
            lines[start:end] = body
        # forced-hosts içinde artık olmayan sunuculara giden kayıtları temizle (yoksa Velocity açılmaz)
        with open(p, "rb") as f:
            fhd = dict(tomllib.load(f).get("forced-hosts") or {})
        fh = next((i for i, l in enumerate(lines) if re.match(r"\s*\[forced-hosts\]\s*$", l)), None)
        if fh is not None:
            end = next((i for i in range(fh + 1, len(lines)) if re.match(r"\s*\[", lines[i])), len(lines))
            out = []
            for host, vals in fhd.items():
                vals = [v for v in vals if v in servers]
                if vals:
                    out.append(f"{_q(host)} = [" + ", ".join(_q(v) for v in vals) + "]\n")
            lines[fh + 1:end] = out + ["\n"]
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.writelines(lines)
    os.replace(tmp, p)


def secret(proxy_dir, create=True):
    p = os.path.join(proxy_dir, SECRET)
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            s = f.read().strip()
        if s:
            return s
    if not create:
        return ""
    s = _secrets.token_urlsafe(12)
    with open(p, "w", encoding="utf-8") as f:
        f.write(s)
    return s


def backend_port(server_dir):
    from .clone import read_props as read_properties
    try:
        return int(read_properties(server_dir).get("server-port", 25565))
    except Exception:
        return 25565


def _yaml_set_velocity(text, secret_):
    """paper-global.yml içindeki proxies.velocity bloğunu ayarlar (yorum ve diğer ayarlar korunur)."""
    block = ("  velocity:\n    enabled: true\n    online-mode: true\n    secret: '" + secret_.replace("'", "''") + "'\n")
    m = re.search(r"^proxies:\s*\n", text, re.M)
    if not m:
        return text.rstrip("\n") + "\nproxies:\n" + block
    start = m.end()
    end_m = re.search(r"^\S", text[start:], re.M)
    end = start + end_m.start() if end_m else len(text)
    sec = text[start:end]
    v = re.search(r"^  velocity:\s*\n((?:    .*\n|\s*\n)*)", sec, re.M)
    sec = sec[:v.start()] + block + sec[v.end():] if v else sec + block
    return text[:start] + sec + text[end:]


def link_backend(proxy_dir, server_dir):
    """Paper/Purpur/Folia arka ucunu modern bilgi aktarımı (modern forwarding) ile proxy'ye bağlar.
    Döndürür: değişen dosyaların listesi."""
    from .clone import read_props as read_properties, write_props as write_properties
    sec = secret(proxy_dir)
    changed = []
    cfg = os.path.join(server_dir, "config", "paper-global.yml")
    if not os.path.exists(cfg):
        raise VelocityError(N_("Bu sunucuda config/paper-global.yml yok. Sunucuyu (Paper, Purpur ya da Folia) bir kez "
                               "başlatıp durdur, sonra tekrar dene."))
    with open(cfg, encoding="utf-8") as f:
        text = f.read()
    new = _yaml_set_velocity(text, sec)
    if new != text:
        with open(cfg, "w", encoding="utf-8") as f:
            f.write(new)
        changed.append(cfg)
    props = read_properties(server_dir)
    if props.get("online-mode", "true") != "false":
        write_properties(server_dir, {"online-mode": "false"})
        changed.append(os.path.join(server_dir, "server.properties"))
    return changed


def unique_name(name, existing):
    base = re.sub(r"[^a-z0-9_\-]+", "-", (name or "server").lower()).strip("-") or "server"
    n, i = base, 2
    while n in existing:
        n, i = f"{base}-{i}", i + 1
    return n


PENDING = ".spypaper-velocity.json"


def set_pending(proxy_dir, opts):
    import json
    with open(os.path.join(proxy_dir, PENDING), "w", encoding="utf-8") as f:
        json.dump(opts, f)


def apply_pending(proxy_dir):
    """Oluşturma sırasında seçilen port/MOTD'u, Velocity velocity.toml'u yazdıktan sonra uygular. True: uygulandı."""
    import json
    p = os.path.join(proxy_dir, PENDING)
    if not (os.path.exists(p) and exists(proxy_dir)):
        return False
    try:
        with open(p, encoding="utf-8") as f:
            o = json.load(f)
        save(proxy_dir, bind=o.get("bind"), motd=o.get("motd"), online_mode=o.get("online_mode"),
             forwarding=o.get("forwarding"))
    finally:
        try:
            os.remove(p)
        except OSError:
            pass
    return True
