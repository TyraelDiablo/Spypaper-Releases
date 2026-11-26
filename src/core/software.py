"""Sunucu yazılımı sağlayıcıları: Paper, Purpur, Vanilla, Fabric, Forge, NeoForge.

Her sağlayıcı aynı arayüzü verir:
  list_versions(contact)            -> ["1.21.4", ...]  (en yeni önce)
  latest_build(version, contact)    -> {"version", "build", "label", "url", "name", "sha256" | "sha1", "size",
                                        "installer": bool}
Doğrudan jar veren yazılımlar core.updater.download ile, Forge/NeoForge ise install_with_installer()
ile (kurulum programı indirilip "java -jar installer.jar --installServer" çalıştırılarak) kurulur.
"""
import glob
import os
import re
import subprocess
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from . import updater
from .config import ARGS_FILE, N_

PURPUR_API = "https://api.purpurmc.org/v2/purpur"
VANILLA_MANIFEST = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
FABRIC_META = "https://meta.fabricmc.net/v2/versions"
FORGE_PROMOS = "https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json"
FORGE_MAVEN = "https://maven.minecraftforge.net/net/minecraftforge/forge"
NEOFORGE_MAVEN = "https://maven.neoforged.net/releases/net/neoforged/neoforge"

_MC_RE = r"\d+\.\d+(\.\d+)?"


def _get(url, contact):
    return updater._get_json(url, contact)


def _get_text(url, contact, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": updater.user_agent(contact)})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")
    except Exception as e:
        raise updater.UpdateError(N_("{host} adresine bağlanılamadı: {e}"),
                                  host=urllib.parse.urlparse(url).netloc, e=updater.net_reason(e))


def _sha1_of(url, contact):
    """Maven depoları her dosyanın yanında .sha1 tutar; alınamazsa doğrulama atlanır."""
    try:
        return _get_text(url + ".sha1", contact, timeout=10).strip().split()[0]
    except Exception:
        return ""


# ---------- Paper ----------
def _paper_versions(contact):
    return updater.list_versions(contact)


def _paper_latest(version, contact):
    return updater.latest_build(version, contact)


# ---------- Folia (PaperMC, çok iş parçacıklı; eklentilerin Folia'yı desteklemesi gerekir) ----------
def _folia_versions(contact):
    return updater.list_versions(contact, project="folia")


def _folia_latest(version, contact):
    return updater.latest_build(version, contact, project="folia", allow_beta=True)


# ---------- Velocity (PaperMC proxy; sürümleri Minecraft sürümü değil, ör. 3.4.0-SNAPSHOT) ----------
def _velocity_versions(contact):
    data = updater._get_json(updater._api("velocity"), contact)
    vers = [v for group in (data.get("versions") or {}).values() for v in group]
    return sorted(set(vers), key=updater._vkey, reverse=True)


def _velocity_latest(version, contact):
    return updater.latest_build(version, contact, project="velocity", allow_beta=True)


# ---------- Purpur ----------
def _purpur_versions(contact):
    data = _get(PURPUR_API, contact)
    vers = [v for v in data.get("versions", []) if re.fullmatch(r"\d+\.\d+(\.\d+)?", v)]
    return sorted(set(vers), key=updater._vkey, reverse=True)


def _purpur_latest(version, contact):
    data = _get(f"{PURPUR_API}/{version}", contact)
    latest = str((data.get("builds") or {}).get("latest", ""))
    if not latest:
        raise updater.UpdateError(N_("{v} için Purpur sürümü bulunamadı."), v=version)
    return {
        "version": version,
        "build": int(latest) if latest.isdigit() else 0,
        "url": f"{PURPUR_API}/{version}/latest/download",
        "name": f"purpur-{version}-{latest}.jar",
        "sha256": "", "size": 0,
    }


# ---------- Vanilla ----------
def _vanilla_versions(contact):
    data = _get(VANILLA_MANIFEST, contact)
    return [v["id"] for v in data.get("versions", []) if v.get("type") == "release"]


def _vanilla_latest(version, contact):
    manifest = _get(VANILLA_MANIFEST, contact)
    entry = next((v for v in manifest.get("versions", []) if v.get("id") == version), None)
    if not entry:
        raise updater.UpdateError(N_("{v} sürümü bulunamadı."), v=version)
    meta = _get(entry["url"], contact)
    server = (meta.get("downloads") or {}).get("server")
    if not server:
        raise updater.UpdateError(N_("{v} için resmi sunucu dosyası yok."), v=version)
    return {
        "version": version, "build": 0, "label": version, "url": server["url"],
        "name": f"minecraft_server.{version}.jar",
        "sha1": server.get("sha1", ""), "size": server.get("size", 0),
    }


# ---------- Fabric ----------
def _fabric_versions(contact):
    data = _get(f"{FABRIC_META}/game", contact)
    return [v["version"] for v in data if v.get("stable")]


def _fabric_latest(version, contact):
    loaders = _get(f"{FABRIC_META}/loader", contact)
    loader = next((x["version"] for x in loaders if x.get("stable")), loaders[0]["version"])
    installers = _get(f"{FABRIC_META}/installer", contact)
    installer = next((x["version"] for x in installers if x.get("stable")), installers[0]["version"])
    return {
        "version": version, "build": 0, "label": loader,
        "url": f"{FABRIC_META}/loader/{version}/{loader}/{installer}/server/jar",
        "name": f"fabric-server-mc.{version}-loader.{loader}-launcher.{installer}.jar",
        "sha256": "", "size": 0,
    }


# ---------- Forge ----------
def _forge_promos(contact):
    return (_get(FORGE_PROMOS, contact) or {}).get("promos", {})


def _forge_versions(contact):
    promos = _forge_promos(contact)
    vers = {k.rsplit("-", 1)[0] for k in promos}
    vers = [v for v in vers if re.fullmatch(_MC_RE, v)]
    return sorted(vers, key=updater._vkey, reverse=True)


def _forge_latest(version, contact):
    promos = _forge_promos(contact)
    fv = promos.get(f"{version}-recommended") or promos.get(f"{version}-latest")
    if not fv:
        raise updater.UpdateError(N_("{v} için Forge sürümü bulunamadı."), v=version)
    full = f"{version}-{fv}"
    url = f"{FORGE_MAVEN}/{full}/forge-{full}-installer.jar"
    return {
        "version": version, "build": 0, "label": fv, "url": url,
        "name": f"forge-{full}-installer.jar", "sha1": _sha1_of(url, contact), "size": 0,
        "installer": True, "recommended": bool(promos.get(f"{version}-recommended")),
    }


# ---------- NeoForge ----------
def neoforge_mc(nv):
    """NeoForge sürümünden Minecraft sürümü.
    Eski düzen: 21.1.77 -> 1.21.1, 21.0.5 -> 1.21, 20.4.80 -> 1.20.4
    Yıl tabanlı düzen (Minecraft 26.x ve sonrası): 26.1.0.5 -> 26.1, 26.1.2.3 -> 26.1.2"""
    parts = nv.split("-")[0].split(".")
    try:
        a, b = int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        return ""
    if a < 26:
        return f"1.{a}" if b == 0 else f"1.{a}.{b}"
    if len(parts) >= 4:
        return f"{a}.{b}" if parts[2] == "0" else f"{a}.{b}.{parts[2]}"
    return f"{a}.{b}"


def _neoforge_all(contact):
    xml = _get_text(f"{NEOFORGE_MAVEN}/maven-metadata.xml", contact)
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as e:
        raise updater.UpdateError(N_("Beklenmeyen yanıt: {e}"), e=e)
    by_mc = {}
    for el in root.iter("version"):
        nv = (el.text or "").strip()
        mc = neoforge_mc(nv)
        if mc and re.fullmatch(_MC_RE, mc):
            by_mc.setdefault(mc, []).append(nv)
    return by_mc


def _neoforge_versions(contact):
    return sorted(_neoforge_all(contact), key=updater._vkey, reverse=True)


def _neoforge_latest(version, contact):
    cands = _neoforge_all(contact).get(version, [])
    if not cands:
        raise updater.UpdateError(N_("{v} için NeoForge sürümü bulunamadı."), v=version)
    stable = [v for v in cands if "-" not in v]           # -beta / -alpha olmayanlar
    pick = max(stable or cands, key=updater._vkey)
    url = f"{NEOFORGE_MAVEN}/{pick}/neoforge-{pick}-installer.jar"
    return {
        "version": version, "build": 0, "label": pick, "url": url,
        "name": f"neoforge-{pick}-installer.jar", "sha1": _sha1_of(url, contact), "size": 0,
        "installer": True, "beta": not stable,
    }


SOFTWARE = {
    "paper":    {"name": "Paper",    "versions": _paper_versions,    "latest": _paper_latest,    "modded": False},
    "purpur":   {"name": "Purpur",   "versions": _purpur_versions,   "latest": _purpur_latest,   "modded": False},
    "folia":    {"name": "Folia",    "versions": _folia_versions,    "latest": _folia_latest,    "modded": False},
    "vanilla":  {"name": "Vanilla",  "versions": _vanilla_versions,  "latest": _vanilla_latest,  "modded": False},
    "fabric":   {"name": "Fabric",   "versions": _fabric_versions,   "latest": _fabric_latest,   "modded": True},
    "forge":    {"name": "Forge",    "versions": _forge_versions,    "latest": _forge_latest,    "modded": True},
    "neoforge": {"name": "NeoForge", "versions": _neoforge_versions, "latest": _neoforge_latest, "modded": True},
    "bedrock":  {"name": "Bedrock (vanilla)", "versions": lambda c: __import__("core.bedrock", fromlist=["x"]).versions(c),
                 "latest": lambda v, c: __import__("core.bedrock", fromlist=["x"]).latest(v, c), "modded": False,
                 "bedrock": True},
    "velocity": {"name": "Velocity (proxy)", "versions": _velocity_versions, "latest": _velocity_latest, "modded": False,
                 "proxy": True},
}


def is_proxy_key(key):
    return bool(SOFTWARE.get(key, {}).get("proxy"))


def is_bedrock_key(key):
    return bool(SOFTWARE.get(key, {}).get("bedrock"))


def key_from_detected(soft):
    """detect_version() çıktısını ("Paper", "NeoForge", ...) sağlayıcı anahtarına çevirir."""
    s = (soft or "").lower()
    return s if s in SOFTWARE else "paper"


def list_versions(key, contact=""):
    return SOFTWARE[key]["versions"](contact)


def latest_build(key, version, contact=""):
    info = SOFTWARE[key]["latest"](version, contact)
    info.setdefault("label", str(info["build"]) if info.get("build") else "")
    info.setdefault("installer", False)
    info["software"] = key
    return info


def current(server_path, jar_name):
    """(yazılım_anahtarı, mc_sürümü, etiket) — etiket: Paper/Purpur build no, Forge/NeoForge sürümü vb."""
    from .config import detect_version
    from . import bedrock
    if bedrock.is_bedrock(server_path):
        v = bedrock.installed_version(server_path)
        return "bedrock", v, v
    jar = (jar_name or "").replace("\\", "/")
    base = os.path.basename(jar)
    pats = (
        ("paper",    r"^paper-(" + _MC_RE + r")-(\d+)\.jar$"),
        ("purpur",   r"^purpur-(" + _MC_RE + r")-(\d+)\.jar$"),
        ("folia",    r"^folia-(" + _MC_RE + r")-(\d+)\.jar$"),
        ("vanilla",  r"^minecraft_server\.(" + _MC_RE + r")\.jar$"),
        ("fabric",   r"^fabric-server-mc\.(" + _MC_RE + r")-loader\.([\w.+\-]+?)-launcher"),
    )
    m = re.match(r"^velocity-([\w.\-]+?)-(\d+)\.jar$", base, re.I)
    if m:
        return "velocity", m.group(1), m.group(2)
    for key, p in pats:
        m = re.match(p, base, re.I)
        if m:     # grup 2: sürümün isteğe bağlı yama kısmı; grup 3: build / loader
            return key, m.group(1), m.group(1) if key == "vanilla" else m.group(3)
    m = re.search(r"libraries/net/neoforged/neoforge/([^/]+)/", jar)
    if m:
        return "neoforge", neoforge_mc(m.group(1)), m.group(1)
    m = re.search(r"libraries/net/minecraftforge/forge/(" + _MC_RE + r")-([^/]+)/", jar)
    if m:
        return "forge", m.group(1), m.group(3)
    m = re.match(r"^forge-(" + _MC_RE + r")-([\w.\-]+?)(?:-universal|-server)?\.jar$", base, re.I)
    if m:
        return "forge", m.group(1), m.group(3)
    ver, soft = detect_version(server_path)
    cur_v, cur_b = updater.current_build(server_path, jar_name)
    key = key_from_detected(soft)
    if key == "paper" and cur_b:
        return key, cur_v, str(cur_b)
    return key, ver, ""


def install_with_installer(info, server_path, java, contact="", progress=None, log=None):
    """Forge / NeoForge: kurulum programını indirir, sunucu klasöründe '--installServer' ile çalıştırır.
    Başlatılacak dosyayı (args.txt göreli yolu ya da eski Forge için jar) döndürür.
    log(satır): kurulum çıktısı."""
    inst = updater.download(dict(info), server_path, "", contact, progress=progress)
    inst_path = os.path.join(server_path, inst)
    before = set(os.listdir(server_path))
    kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    try:
        p = subprocess.Popen([java or "java", "-jar", inst, "--installServer"], cwd=server_path,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                             encoding="utf-8", errors="replace", **kwargs)
    except Exception as e:
        raise updater.UpdateError(N_("Kurulum programı çalıştırılamadı: {e}"), e=e)
    tail = []
    for line in p.stdout:
        line = line.rstrip()
        tail = (tail + [line])[-15:]
        if log:
            log(line)
    if p.wait() != 0:
        raise updater.UpdateError(N_("Kurulum başarısız oldu (çıkış kodu {c}):\n{tail}"), c=p.returncode,
                                  tail="\n".join(tail[-6:]))
    # kurulum programını ve günlüğünü kaldır
    for f in (inst_path, inst_path + ".log"):
        try:
            os.remove(f)
        except OSError:
            pass

    label = info["label"]
    if info["software"] == "neoforge":
        cand = f"libraries/net/neoforged/neoforge/{label}/{ARGS_FILE}"
    else:
        cand = f"libraries/net/minecraftforge/forge/{info['version']}-{label}/{ARGS_FILE}"
    if os.path.isfile(os.path.join(server_path, *cand.split("/"))):
        return cand
    # eski Forge (1.16 ve öncesi): klasörde çalıştırılabilir forge-*.jar oluşur
    new = [f for f in set(os.listdir(server_path)) - before
           if f.lower().endswith(".jar") and "installer" not in f.lower()]
    new += [os.path.basename(f) for f in glob.glob(os.path.join(server_path, f"forge-{info['version']}-{label}*.jar"))
            if "installer" not in f.lower()]
    if new:
        return sorted(set(new), key=len)[0]
    raise updater.UpdateError(N_("Kurulum tamamlandı ama başlatma dosyası bulunamadı."))
