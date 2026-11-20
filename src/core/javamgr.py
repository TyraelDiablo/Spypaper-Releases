"""Java yöneticisi: bilgisayardaki Java kurulumlarını bulur, sunucunun Minecraft sürümüne uygun olanı önerir
ve gerekirse Eclipse Temurin'i (Adoptium) indirir.

Aranan yerler: PATH'teki java, JAVA_HOME, Program Files altındaki bilinen dağıtımlar (Adoptium, Oracle,
Microsoft, Zulu, Liberica, Corretto, Semeru), ~/.jdks, Minecraft Launcher'ın kendi Java'ları ve
Spypaper'ın indirdikleri (<Spypaper>/java/).

Sürüm, kurulumun 'release' dosyasından okunur (süreç başlatmadan); yoksa 'java -version' çalıştırılır.

İndirme: api.adoptium.net'ten JRE zip'i (yoksa JDK), SHA-256 doğrulamasıyla, <Spypaper>/java/ altına açılır.
Hiçbir şey sisteme kurulmaz, PATH ya da kayıt defteri değişmez.
"""
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile

from .config import N_, get_base_dir

LTS = (8, 11, 17, 21, 25)
API = "https://api.adoptium.net/v3/assets/latest/{major}/hotspot?architecture={arch}&image_type={kind}&os={os}&vendor=eclipse"
EXE = "java.exe" if os.name == "nt" else "java"
_cache = {}          # (yol, mtime) -> (major, tam sürüm, satıcı)


class JavaError(Exception):
    def __init__(self, template, **kw):
        super().__init__(template.format(**kw) if kw else template)
        self.template, self.kw = template, kw


# ------------------------------------------------------------------ gereksinim
def required_java(mc_version):
    """Minecraft sürümü için gereken en düşük Java (bilinmiyorsa None)."""
    if not mc_version or not re.match(r"^\d+\.\d+", mc_version):
        return None
    from .creator import java_hint
    return java_hint(mc_version)


def recommended(required):
    """İndirilmesi önerilen LTS sürüm (gerekenden küçük olmayan en eski LTS)."""
    return next((v for v in LTS if v >= (required or 21)), LTS[-1])


_JAR_VER = re.compile(r"(?:^|[-_]|mc\.)((?:1\.\d{1,2}(?:\.\d{1,2})?)|(?:2\d\.\d{1,2}(?:\.\d{1,2})?))(?=[-_.]|$)")


def mc_version(server_path, jar_name=""):
    """Sunucunun Minecraft sürümü: önce latest.log, sonra jar adı (paper-1.21.4-232.jar),
    sonra jar içindeki version.json (vanilla). Bulunamazsa ''."""
    from .config import detect_version
    ver = detect_version(server_path)[0]
    if ver:
        return ver
    name = os.path.basename(jar_name or "")
    m = _JAR_VER.search(name[:-4] if name.endswith(".jar") else name)
    if m:
        return m.group(1)
    jar = os.path.join(server_path, jar_name or "")
    if jar_name.endswith(".jar") and os.path.isfile(jar):
        try:
            with zipfile.ZipFile(jar) as z:
                if "version.json" in z.namelist():
                    return str(json.loads(z.read("version.json")).get("id") or "")
        except (OSError, zipfile.BadZipFile, ValueError):
            pass
    return ""


# ------------------------------------------------------------------ sürüm okuma
def _major(text):
    m = re.search(r'(\d+)(?:\.(\d+))?', text or "")
    if not m:
        return None
    a = int(m.group(1))
    return int(m.group(2) or 0) if a == 1 else a      # 1.8.0_402 -> 8


def resolve(java_path):
    """'java' gibi komut adlarını tam yola çevirir. Bulunamazsa ''."""
    p = (java_path or "").strip().strip('"')
    if not p:
        return ""
    if os.path.isfile(p):
        return os.path.abspath(p)
    if os.path.isdir(p):                                     # JAVA_HOME verilmiş olabilir
        for c in (os.path.join(p, "bin", EXE), os.path.join(p, EXE)):
            if os.path.isfile(c):
                return c
        return ""
    return shutil.which(p) or ""


def info(java_path):
    """(major, tam sürüm, satıcı) ya da (None, '', '') — java bulunamadı/çalışmadı."""
    exe = resolve(java_path)
    if not exe:
        return None, "", ""
    try:
        key = (os.path.normcase(exe), os.path.getmtime(exe))
    except OSError:
        return None, "", ""
    if key in _cache:
        return _cache[key]
    res = None
    home = os.path.dirname(os.path.dirname(exe))
    rel = os.path.join(home, "release")
    if os.path.isfile(rel):
        try:
            vals = {}
            with open(rel, encoding="utf-8", errors="ignore") as f:
                for line in f:
                    k, _, v = line.partition("=")
                    vals[k.strip()] = v.strip().strip('"')
            full = vals.get("JAVA_RUNTIME_VERSION") or vals.get("JAVA_VERSION") or ""
            if full:
                res = (_major(vals.get("JAVA_VERSION") or full), full, vals.get("IMPLEMENTOR", ""))
        except OSError:
            pass
    if res is None:
        try:
            kw = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
            out = subprocess.run([exe, "-version"], capture_output=True, text=True, timeout=8,
                                 encoding="utf-8", errors="replace", **kw)
            text = out.stderr + out.stdout
            m = re.search(r'version "([^"]+)"', text)
            full = m.group(1) if m else ""
            vendor = next((v for v in ("Temurin", "Zulu", "Corretto", "Microsoft", "GraalVM", "Liberica",
                                       "Semeru", "Oracle", "OpenJDK") if v in text), "")
            res = (_major(full), full, vendor) if full else (None, "", "")
        except (OSError, subprocess.SubprocessError):
            res = (None, "", "")
    _cache[key] = res
    return res


# ------------------------------------------------------------------ arama
def managed_dir():
    return os.path.join(get_base_dir(), "java")


def _candidates():
    env = os.environ
    out = []                                          # (yol, kaynak)
    w = shutil.which("java")
    if w:
        out.append((w, "PATH"))
    if env.get("JAVA_HOME"):
        out.append((os.path.join(env["JAVA_HOME"], "bin", EXE), "JAVA_HOME"))
    pats = []
    for root in {env.get("ProgramFiles", ""), env.get("ProgramW6432", ""), env.get("ProgramFiles(x86)", "")} - {""}:
        for vendor in ("Eclipse Adoptium", "Eclipse Foundation", "AdoptOpenJDK", "Java", "Microsoft", "Zulu",
                       "BellSoft", "Amazon Corretto", "Semeru", "IBM", "OpenJDK", "GraalVM"):
            pats.append((os.path.join(root, vendor, "*", "bin", EXE), "system"))
    home = os.path.expanduser("~")
    pats.append((os.path.join(home, ".jdks", "*", "bin", EXE), "system"))
    # Minecraft Launcher'ın Java'ları (klasik ve Microsoft Store sürümü)
    mc_roots = [os.path.join(env.get("APPDATA", ""), ".minecraft", "runtime"),
                os.path.join(env.get("ProgramFiles(x86)", ""), "Minecraft Launcher", "runtime")]
    mc_roots += glob.glob(os.path.join(env.get("LOCALAPPDATA", ""), "Packages", "Microsoft.4297127D64EC6_*",
                                       "LocalCache", "Local", "runtime"))
    for r in mc_roots:
        pats.append((os.path.join(r, "*", "*", "*", "bin", EXE), "minecraft"))
    pats.append((os.path.join(managed_dir(), "*", "bin", EXE), "spypaper"))
    for pat, src in pats:
        out += [(p, src) for p in glob.glob(pat)]
    return out


def find_javas():
    """[{path, major, version, vendor, source}] — sürüme göre yeniden eskiye, tekrarlar ayıklanmış."""
    seen, found = set(), []
    for path, src in _candidates():
        try:
            real = os.path.normcase(os.path.realpath(path))
        except OSError:
            continue
        if real in seen or not os.path.isfile(path):
            continue
        seen.add(real)
        major, full, vendor = info(path)
        if major is None:
            continue
        found.append({"path": os.path.abspath(path), "major": major, "version": full, "vendor": vendor,
                      "source": src})
    prio = {"spypaper": 0, "system": 1, "JAVA_HOME": 2, "PATH": 3, "minecraft": 4}
    found.sort(key=lambda j: (-j["major"], prio.get(j["source"], 9)))
    return found


def best_for(required, javas=None):
    """Gereksinimi karşılayan en uygun Java: önce bağımsız kurulumlar (Minecraft Launcher kendi Java'larını
    güncelleyip silebilir), sonra gereken sürüme en yakın olan."""
    javas = find_javas() if javas is None else javas
    ok = [j for j in javas if required is None or j["major"] >= required]
    if not ok:
        return None
    return min(ok, key=lambda j: (j["source"] == "minecraft", j["major"] - (required or 0)))


def check(profile):
    """Sunucu başlamadan önce: (gereken, seçili major, seçili yol). Bilinmeyenler None/''."""
    req = required_java(mc_version(profile.server_path, profile.get("jar_name")))
    exe = resolve(profile.get("java_path"))
    return req, (info(exe)[0] if exe else None), exe


# ------------------------------------------------------------------ indirme
def _arch():
    import platform
    m = platform.machine().lower()
    return "aarch64" if m in ("arm64", "aarch64") else "x64"


def release(major, contact=""):
    """Temurin {major} için en yeni sürüm: {name, url, sha256, size, version, kind}."""
    from .updater import user_agent
    osname = "windows" if os.name == "nt" else "mac" if sys.platform == "darwin" else "linux"
    for kind in ("jre", "jdk"):
        url = API.format(major=int(major), arch=_arch(), kind=kind, os=osname)
        req = urllib.request.Request(url, headers={"User-Agent": user_agent(contact)})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                data = json.loads(r.read())
        except Exception as e:
            from .updater import net_reason
            raise JavaError(N_("Java sürüm listesi alınamadı: {error}"), error=net_reason(e))
        for item in data or []:
            pkg = (item.get("binary") or {}).get("package") or {}
            if pkg.get("link", "").endswith((".zip", ".tar.gz")) and pkg.get("checksum"):
                return {"name": pkg["name"], "url": pkg["link"], "sha256": pkg["checksum"],
                        "size": int(pkg.get("size") or 0), "version": item.get("release_name", ""), "kind": kind}
    raise JavaError(N_("Bu bilgisayar için Java {major} bulunamadı."), major=major)


def download(major, contact="", progress=None, cancelled=None):
    """Temurin {major}'ü indirir, doğrular, <Spypaper>/java/ altına açar. java yolunu döndürür.
    progress(alınan, toplam). cancelled() True dönerse iptal edilir."""
    from .updater import net_reason, user_agent
    rel = release(major, contact)
    os.makedirs(managed_dir(), exist_ok=True)
    tmp = os.path.join(managed_dir(), rel["name"] + ".part")
    h = hashlib.sha256()
    try:
        req = urllib.request.Request(rel["url"], headers={"User-Agent": user_agent(contact)})
        with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
            total = int(r.headers.get("Content-Length") or rel["size"] or 0)
            got = 0
            while True:
                if cancelled and cancelled():
                    raise JavaError(N_("İndirme iptal edildi."))
                chunk = r.read(256 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                h.update(chunk)
                got += len(chunk)
                if progress:
                    progress(got, total)
    except JavaError:
        _rm(tmp)
        raise
    except Exception as e:
        _rm(tmp)
        raise JavaError(N_("İndirme başarısız: {e}"), e=net_reason(e))
    if h.hexdigest().lower() != rel["sha256"].lower():
        _rm(tmp)
        raise JavaError(N_("Dosya doğrulanamadı ({algo} uyuşmuyor). Güncelleme iptal edildi."), algo="SHA-256")
    try:
        return _extract(tmp, rel)
    finally:
        _rm(tmp)


def _rm(p):
    try:
        os.remove(p)
    except OSError:
        pass


def _extract(archive, rel):
    base = managed_dir()
    stage = os.path.join(base, ".extract")
    shutil.rmtree(stage, ignore_errors=True)
    os.makedirs(stage)
    try:
        if rel["name"].endswith(".zip"):
            with zipfile.ZipFile(archive) as z:
                for m in z.namelist():                    # zip içinden dışarı yazma girişimlerine karşı
                    dest = os.path.realpath(os.path.join(stage, m))
                    if not dest.startswith(os.path.realpath(stage) + os.sep) and dest != os.path.realpath(stage):
                        raise JavaError(N_("Arşiv geçersiz."))
                z.extractall(stage)
        else:
            import tarfile
            with tarfile.open(archive) as tf:
                tf.extractall(stage, filter="data")
        tops = [d for d in os.listdir(stage) if os.path.isdir(os.path.join(stage, d))]
        if len(tops) != 1:
            raise JavaError(N_("Arşiv geçersiz."))
        target = os.path.join(base, tops[0])
        if os.path.isdir(target):                         # aynı sürüm zaten var: yenisiyle değiştir
            shutil.rmtree(target, ignore_errors=True)
        shutil.move(os.path.join(stage, tops[0]), target)
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    exe = os.path.join(target, "bin", EXE)
    if not os.path.isfile(exe):
        raise JavaError(N_("Arşiv geçersiz."))
    return exe
