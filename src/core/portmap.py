"""Modem port yönlendirme (UPnP IGD). Yalnızca standart kütüphane.

Akış: SSDP ile ağdaki modemi bul → aygıt tanımını oku → WANIPConnection/WANPPPConnection
servisinin kontrol adresini al → TCP port eşlemesini ekle, kapanınca kaldır.
Modem UPnP kapalıysa ya da eşleme reddedilirse hata metni döner; uygulama çökmez.
"""
import re
import socket
import urllib.error
import urllib.request
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree as ET

from .config import N_

SSDP_ADDR = ("239.255.255.250", 1900)
SEARCH_TARGETS = ("urn:schemas-upnp-org:device:InternetGatewayDevice:1",
                  "urn:schemas-upnp-org:device:InternetGatewayDevice:2")
SERVICE_TYPES = ("urn:schemas-upnp-org:service:WANIPConnection:1",
                 "urn:schemas-upnp-org:service:WANIPConnection:2",
                 "urn:schemas-upnp-org:service:WANPPPConnection:1")
DESCRIPTION = "Spypaper"
TIMEOUT = 4


class PortMapError(Exception):
    pass


def _msearch(target):
    return ("M-SEARCH * HTTP/1.1\r\n"
            f"HOST: {SSDP_ADDR[0]}:{SSDP_ADDR[1]}\r\n"
            'MAN: "ssdp:discover"\r\n'
            "MX: 2\r\n"
            f"ST: {target}\r\n\r\n").encode()


def discover(timeout=TIMEOUT):
    """Ağdaki İnternet ağ geçidi aygıtlarının tanım adreslerini (LOCATION) döndürür."""
    locations = []
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    try:
        sock.settimeout(timeout)
        for target in SEARCH_TARGETS:
            sock.sendto(_msearch(target), SSDP_ADDR)
        while True:
            try:
                data, _addr = sock.recvfrom(65535)
            except socket.timeout:
                break
            for line in data.decode("latin-1", "replace").split("\r\n"):
                if line.lower().startswith("location:"):
                    loc = line.split(":", 1)[1].strip()
                    if loc and loc not in locations:
                        locations.append(loc)
    except OSError:
        pass
    finally:
        sock.close()
    return locations


def parse_description(xml_text, location):
    """Aygıt tanımından (servis türü, tam kontrol adresi) döndürür; bulunamazsa None."""
    root = ET.fromstring(xml_text)
    for el in root.iter():
        if not el.tag.endswith("service"):
            continue
        stype = control = None
        for child in el:
            name = child.tag.rsplit("}", 1)[-1]
            if name == "serviceType":
                stype = (child.text or "").strip()
            elif name == "controlURL":
                control = (child.text or "").strip()
        if stype in SERVICE_TYPES and control:
            return stype, urljoin(location, control)
    return None


def _envelope(stype, action, args):
    body = "".join(f"<{k}>{v}</{k}>" for k, v in args)
    return ('<?xml version="1.0"?>'
            '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
            's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
            "<s:Body>"
            f'<u:{action} xmlns:u="{stype}">{body}</u:{action}>'
            "</s:Body></s:Envelope>")


def soap_call(stype, control, action, args=(), timeout=TIMEOUT):
    """SOAP isteği gönderir; yanıt gövdesini (metin) döndürür."""
    req = urllib.request.Request(control, data=_envelope(stype, action, args).encode(), method="POST")
    req.add_header("Content-Type", 'text/xml; charset="utf-8"')
    req.add_header("SOAPAction", f'"{stype}#{action}"')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        m = re.search(r"<errorDescription>(.*?)</errorDescription>", detail)
        raise PortMapError(m.group(1) if m else f"HTTP {e.code}") from None
    except (urllib.error.URLError, OSError) as e:
        raise PortMapError(str(getattr(e, "reason", e))) from None


def local_ip_toward(host):
    """Bu bilgisayarın, verilen ağ geçidine ulaşan yerel IPv4 adresi."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((host, 9))
        return s.getsockname()[0]
    finally:
        s.close()


def gateway_for(location):
    """(servis türü, kontrol adresi, yerel IP) — bulunamazsa PortMapError."""
    try:
        with urllib.request.urlopen(location, timeout=TIMEOUT) as r:
            xml_text = r.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError) as e:
        raise PortMapError(str(getattr(e, "reason", e))) from None
    try:
        found = parse_description(xml_text, location)
    except ET.ParseError:
        found = None
    if not found:
        raise PortMapError(N_("Modemde port yönlendirme servisi bulunamadı."))
    host = urlparse(location).hostname or ""
    return found[0], found[1], local_ip_toward(host)


def _check_port(port):
    if not (1 <= int(port) <= 65535):
        raise PortMapError(N_("Geçersiz port."))
    return int(port)


class Mapping:
    """Bir TCP port eşlemesi. add() modemi bulur ve eşler; remove() kaldırır."""

    def __init__(self, port, locations=None):
        self.port = _check_port(port)
        self.locations = locations
        self.service = None          # (stype, control)
        self.external_ip = ""

    def add(self):
        locs = self.locations if self.locations is not None else discover()
        last = N_("Modem bulunamadı (UPnP kapalı olabilir).")
        for loc in locs:
            try:
                stype, control, lan = gateway_for(loc)
                soap_call(stype, control, "AddPortMapping", [
                    ("NewRemoteHost", ""), ("NewExternalPort", self.port), ("NewProtocol", "TCP"),
                    ("NewInternalPort", self.port), ("NewInternalClient", lan), ("NewEnabled", 1),
                    ("NewPortMappingDescription", DESCRIPTION), ("NewLeaseDuration", 0)])
                self.service = (stype, control)
                try:
                    body = soap_call(stype, control, "GetExternalIPAddress")
                    m = re.search(r"<NewExternalIPAddress>(.*?)</NewExternalIPAddress>", body)
                    self.external_ip = m.group(1).strip() if m else ""
                except PortMapError:
                    self.external_ip = ""
                return True
            except PortMapError as e:
                last = str(e)
        raise PortMapError(last)

    def remove(self):
        if not self.service:
            return
        stype, control = self.service
        self.service = None
        try:
            soap_call(stype, control, "DeletePortMapping", [
                ("NewRemoteHost", ""), ("NewExternalPort", self.port), ("NewProtocol", "TCP")])
        except PortMapError:
            pass
