"""Sunucunun (Paper/Spigot/vanilla) kendi log satırları için önceden hazırlanmış çeviriler.

Eklenti satırları burada yoktur. Her kayıt: (düzenli ifade, panel dilinde şablon, yeniden çevrilecek gruplar).
Şablondaki {0}, {1}… düzenli ifadenin gruplarıdır. "yeniden çevrilecek" gruplar (ör. bağlantı kopma nedeni)
LogTranslator.message ile ayrıca çevrilir. Şablonlar tools/translations/25_server_logs.tsv ile 15 dile çevrilir.
"""
import re

from .config import N_

# Önünde "[ad] " olan ve sunucunun kendisine ait logger'lar (eklentiler değil)
CORE_LOGGERS = {
    "bootstrap", "PluginInitializerManager", "MoonriseCommon", "ChunkHolderManager", "MavenLibraryResolver",
    "SpigotLibraryLoader", "PaperVersionFetcher", "ModernPluginLoadingStrategy", "ServerMain", "minecraft",
}
CORE_LOGGER_PREFIXES = ("ca.spottedleaf.", "com.destroystokyo.paper.", "io.papermc.", "net.minecraft.", "org.bukkit.",
                        "org.spigotmc.", "com.mojang.")

NUM = r"([\d.,]+)"
NAME = r"([A-Za-z0-9_.*~-]+)"

_RAW = [
    # --- açılış
    (r"^Starting org\.bukkit\.craftbukkit\.Main$", N_("org.bukkit.craftbukkit.Main başlatılıyor"), ()),
    (r"^(\S+) ServerMain WARN Advanced terminal features are not available in this environment$",
     N_("{0} Gelişmiş terminal özellikleri bu ortamda kullanılamıyor"), ()),
    (r"^Running Java (\S+) \((.+)\) on (.+)$", N_("Java {0} çalışıyor ({1}), sistem: {2}"), ()),
    (r"^Loading (\S+) (\S+) \((.+)\) for Minecraft (\S+)$", N_("{0} {1} ({2}) Minecraft {3} için yükleniyor"), ()),
    (r"^Initializing plugins\.\.\.$", N_("Eklentiler hazırlanıyor..."), ()),
    (r"^Initialized (\d+) plugins?$", N_("{0} eklenti hazırlandı"), ()),
    (r"^Paper plugins \((\d+)\):$", N_("Paper eklentileri ({0}):"), ()),
    (r"^Bukkit plugins \((\d+)\):$", N_("Bukkit eklentileri ({0}):"), ()),
    (r"^Initialising converters for DataConverter\.\.\.$", N_("DataConverter dönüştürücüleri hazırlanıyor..."), ()),
    (r"^Finished initialising converters for DataConverter in " + NUM + r" ?ms$",
     N_("DataConverter dönüştürücüleri {0} ms'de hazırlandı"), ()),
    (r"^Environment: (.+)$", N_("Ortam: {0}"), ()),
    (r"^Loaded (\d+) advancements$", N_("{0} başarım yüklendi"), ()),
    (r"^Loaded (\d+) recipes$", N_("{0} tarif yüklendi"), ()),
    (r"^Loading properties$", N_("Sunucu ayarları yükleniyor"), ()),
    (r"^This server is running (\S+) version (\S+) \((.+)\) \(Implementing API version (.+)\)$",
     N_("Bu sunucu {0} {1} sürümünü çalıştırıyor ({2}), API sürümü {3}"), ()),
    (r"^This server bundles the spark profiler\. For more information please visit (\S+)$",
     N_("Bu sunucuda spark profil aracı yerleşik gelir. Ayrıntılar: {0}"), ()),
    (r"^Server Ping Player Sample Count: (\d+)$", N_("Sunucu listesinde gösterilen örnek oyuncu sayısı: {0}"), ()),
    (r"^Using (\d+) threads for Netty based IO$", N_("Ağ işlemleri (Netty) için {0} iş parçacığı kullanılıyor"), ()),
    (r"^Using (\S+) channel type$", N_("{0} kanal türü kullanılıyor"), ()),
    (r"^Paper is using (\d+) worker threads, (\d+) I/O threads$",
     N_("Paper {0} çalışan ve {1} G/Ç iş parçacığı kullanıyor"), ()),
    (r"^FMA supported: (\w+) as determined by performance comparison test$",
     N_("FMA desteği: {0} (performans karşılaştırmasına göre)"), ()),
    (r"^Default game type: (\w+)$", N_("Varsayılan oyun modu: {0}"), ()),
    (r"^Generating keypair$", N_("Anahtar çifti oluşturuluyor"), ()),
    (r"^Paper: Using (.+) compression from Velocity\.$", N_("Paper: Velocity'nin {0} sıkıştırması kullanılıyor."), ()),
    (r"^Paper: Using (.+) cipher from Velocity\.$", N_("Paper: Velocity'nin {0} şifrelemesi kullanılıyor."), ()),
    (r"^Loading (\d+) persistent chunks for level '(.+)'\.\.\.$",
     N_("{1} için {0} kalıcı chunk yükleniyor..."), ()),
    (r"^Preparing spawn area: (\d+)%$", N_("Doğma alanı hazırlanıyor: %{0}"), ()),
    (r"^Prepared spawn area in " + NUM + r" ms$", N_("Doğma alanı {0} ms'de hazırlandı"), ()),
    (r"^Preparing start region for dimension (.+)$", N_("{0} boyutu için başlangıç bölgesi hazırlanıyor"), ()),
    (r'^Done preparing level "(.+)" \(' + NUM + r"s\)$", N_("\"{0}\" dünyası hazırlandı ({1} sn)"), ()),
    (r"^Selecting spawn point for level '(.+)'\.\.\.$", N_("{0} için doğma noktası seçiliyor..."), ()),
    (r"^Running delayed init tasks$", N_("Gecikmeli başlangıç görevleri çalıştırılıyor"), ()),
    (r"^No existing world data, creating new world$", N_("Dünya verisi yok, yeni dünya oluşturuluyor"), ()),
    (r"^This is the first time you're starting this server\.$", N_("Bu sunucu ilk kez başlatılıyor."), ()),
    (r"^It's recommended you read our 'Getting Started' documentation for guidance\.$",
     N_("Yol gösterici olarak 'Getting Started' belgesini okumanız önerilir."), ()),
    (r"^View this and more helpful information here: (\S+)$", N_("Bunu ve daha fazla yardımı burada bulabilirsiniz: {0}"), ()),
    (r"^Found new data pack (.+), loading it automatically$", N_("Yeni veri paketi bulundu: {0}, otomatik yükleniyor"), ()),
    (r"^resource-pack-id missing, using default of (.+)$", N_("resource-pack-id eksik, varsayılan kullanılıyor: {0}"), ()),
    (r"^Starting remote control listener$", N_("Uzaktan kontrol (RCON) dinleyicisi başlatılıyor"), ()),
    (r"^RCON running on (.+)$", N_("RCON çalışıyor: {0}"), ()),
    (r"^Starting GS4 status listener$", N_("Sorgu (GS4) dinleyicisi başlatılıyor"), ()),
    (r"^Thread Query Listener started$", N_("Sorgu dinleyicisi başladı"), ()),
    (r"^Query running on (.+)$", N_("Sorgu çalışıyor: {0}"), ()),
    (r"^Server empty for (\d+) seconds, pausing$", N_("Sunucu {0} saniyedir boş, duraklatılıyor"), ()),
    (r"^Time elapsed: (\d+) ms$", N_("Geçen süre: {0} ms"), ()),
    (r"^Downloading (\S+)$", N_("İndiriliyor: {0}"), ()),
    (r"^\[(\S+)\] Loading (\d+) libraries\.\.\. please wait$", N_("[{0}] {1} kütüphane yükleniyor... lütfen bekleyin"), ()),
    (r"^\[(\S+)\] Loaded library (.+)$", N_("[{0}] Kütüphane yüklendi: {1}"), ()),
    # --- sürüm denetimi ve uyarılar
    (r"^\*\*\* Currently you are (\d+) builds? behind \*\*\*$", N_("*** Şu an {0} sürüm gerisiniz ***"), ()),
    (r"^\*\*\* It is highly recommended to download the latest build from (\S+) \*\*\*$",
     N_("*** En son sürümü {0} adresinden indirmeniz önemle önerilir ***"), ()),
    (r"^You are running the latest version$", N_("En son sürümü kullanıyorsunuz"), ()),
    (r"^\*\*\*\* SERVER IS RUNNING IN OFFLINE/INSECURE MODE!$", N_("**** SUNUCU ÇEVRİMDIŞI/GÜVENSİZ MODDA ÇALIŞIYOR!"), ()),
    (r"^The server will make no attempt to authenticate usernames\. Beware\.$",
     N_("Sunucu kullanıcı adlarını doğrulamayacak. Dikkat edin."), ()),
    (r"^While this makes the game possible to play without internet access, it also opens up the ability for hackers "
     r"to connect with any username they choose\.$",
     N_("Bu, oyunun internetsiz oynanmasını sağlar ama saldırganların istedikleri kullanıcı adıyla bağlanmasına da "
        "kapı açar."), ()),
    (r'^To change this, set "online-mode" to "true" in the server\.properties file\.$',
     N_("Bunu değiştirmek için server.properties dosyasında \"online-mode\" ayarını \"true\" yapın."), ()),
    (r"^A manual \(plugin-induced\) save has been detected while server is configured to auto-save\. "
     r"This may affect performance\.$",
     N_("Otomatik kayıt açıkken bir eklenti elle kayıt başlattı. Bu performansı etkileyebilir."), ()),
    (r"^Failed to load datapacks, can't proceed with server load\. You can either fix your datapacks or reset to "
     r"vanilla with --safeMode$",
     N_("Veri paketleri yüklenemedi, sunucu açılamıyor. Veri paketlerini düzeltin ya da --safeMode ile vanilla "
        "ayarlara dönün."), ()),
    (r"^Registry loading errors:$", N_("Kayıt defteri yükleme hataları:"), ()),
    (r"^Command exception: (.+)$", N_("Komut hatası: {0}"), ()),
    (r"^Entity uuid already exists: (\S+), mapped to (.+)$", N_("Varlık UUID'si zaten var: {0}, eşleşen: {1}"), ()),
    (r"^Skipping Entity with id (\S+)$", N_("{0} kimlikli varlık atlanıyor"), ()),
    # --- oyuncular ve bağlantı
    (r"^UUID of player " + NAME + r" is ([0-9a-fA-F-]+)$", N_("{0} oyuncusunun UUID'si: {1}"), ()),
    (r"^" + NAME + r"\[/([^\]]+)\] logged in with entity id (\d+) at \((.+)\)$",
     N_("{0} giriş yaptı ({1}), varlık no {2}, konum: {3}"), ()),
    (r"^" + NAME + r" moved too quickly! (.+)$", N_("{0} çok hızlı hareket etti! {1}"), ()),
    (r"^" + NAME + r" moved wrongly!$", N_("{0} hatalı hareket etti!"), ()),
    (r"^" + NAME + r" was kicked for floating too long!$", N_("{0} çok uzun süre havada kaldığı için atıldı!"), ()),
    (r"^" + NAME + r" was kicked due to keepalive timeout!$", N_("{0} bağlantı zaman aşımı nedeniyle atıldı!"), ()),
    (r"^Disconnecting " + NAME + r" \((/[^)]+)\): (.+)$", N_("{0} ({1}) bağlantısı kesiliyor: {2}"), (2,)),
    (r"^Disconnecting (.+): (.+)$", N_("{0} bağlantısı kesiliyor: {1}"), (1,)),
    (r"^" + NAME + r" \((/[^)]+)\) lost connection: (.+)$", N_("{0} ({1}) bağlantısı koptu: {2}"), (2,)),
    (r"^" + NAME + r" lost connection: (.+)$", N_("{0} bağlantısı koptu: {1}"), (1,)),
    (r"^Disconnected$", N_("Bağlantı kesildi"), ()),
    # dil dosyası (Translation klasörü) yoksa da çevrilsin
    (r"^" + NAME + r" joined the game$", N_("{0} oyuna katıldı"), ()),
    (r"^" + NAME + r" left the game$", N_("{0} oyundan ayrıldı"), ()),
    (r"^" + NAME + r" has made the advancement \[(.+)\]$", N_("{0} [{1}] başarımını kazandı"), ()),
    (r"^" + NAME + r" has completed the challenge \[(.+)\]$", N_("{0} [{1}] meydan okumasını tamamladı"), ()),
    (r"^" + NAME + r" has reached the goal \[(.+)\]$", N_("{0} [{1}] hedefine ulaştı"), ()),
    (r"^You are not whitelisted on this server!$", N_("Bu sunucunun beyaz listesinde değilsin!"), ()),
    (r"^Username '(.+)' tried to join with an invalid session$",
     N_("'{0}' kullanıcı adı geçersiz bir oturumla girmeye çalıştı"), ()),
    (r"^Couldn't find profile with name: (.+)$", N_("Bu adla profil bulunamadı: {0}"), ()),
    (r"^Player " + NAME + r" standing on air - force-sending blocks below$",
     N_("{0} havada duruyor; altındaki bloklar yeniden gönderiliyor"), ()),
    (r"^Attempt to teleport removed player " + NAME + r" restricted$",
     N_("Oyundan çıkmış {0} ışınlanmak istendi; engellendi"), ()),
    (r"^" + NAME + r" was expected to be controlling vehicle .+ but was not\. Resetting vehicle position\.$",
     N_("{0} aracı kontrol etmiyordu; aracın konumu sıfırlanıyor."), ()),
    (r"^Failed to verify username!$", N_("Kullanıcı adı doğrulanamadı!"), ()),
    # --- komut yanıtları (dil dosyası yoksa da çevrilsin)
    (r"^Unknown or incomplete command\. See below for error$", N_("Bilinmeyen ya da eksik komut. Hata aşağıda"), ()),
    (r"^Incorrect argument for command$", N_("Komut için yanlış argüman"), ()),
    (r"^An entity is required to run this command here$", N_("Bu komutu burada çalıştırmak için bir varlık gerekir"), ()),
    (r"^An unexpected error occurred while trying to execute that command$",
     N_("Komut çalıştırılırken beklenmeyen bir hata oluştu"), ()),
    (r"^(/\S+): A Mojang provided command\.$", N_("{0}: Mojang'ın sağladığı komut."), ()),
    (r"^(/\S+): Gets the version of this server including any plugins in use$",
     N_("{0}: Sunucunun ve yüklü eklentilerin sürümünü gösterir"), ()),
    (r"^(/\S+): Gets a list of plugins running on the server$", N_("{0}: Sunucudaki eklentileri listeler"), ()),
    (r"^(/\S+): Shows the help menu$", N_("{0}: Yardım menüsünü gösterir"), ()),
    # --- kapanış
    (r"^Saving players$", N_("Oyuncular kaydediliyor"), ()),
    (r"^Saving worlds$", N_("Dünyalar kaydediliyor"), ()),
    (r"^Closing Server$", N_("Sunucu kapatılıyor"), ()),
    (r"^Closing Thread Pool$", N_("İş parçacığı havuzu kapatılıyor"), ()),
    (r"^Flushing Chunk IO$", N_("Chunk G/Ç tamponu boşaltılıyor"), ()),
    (r"^Saving usercache\.json$", N_("usercache.json kaydediliyor"), ()),
    (r"^Saving chunks for level 'ServerLevel\[(.+)\]'/(.+)$", N_("Chunk'lar kaydediliyor: {0} ({1})"), ()),
    (r"^Waiting for all RegionFile I/O tasks to complete\.\.\.$", N_("Bütün bölge dosyası G/Ç işlerinin bitmesi bekleniyor..."), ()),
    (r"^All RegionFile I/O tasks to complete$", N_("Bütün bölge dosyası G/Ç işleri tamamlandı"), ()),
    (r"^Halted I/O scheduler for world '(.+)'$", N_("{0}: G/Ç zamanlayıcısı durduruldu"), ()),
    (r"^Halted chunk system for world '(.+)'$", N_("{0}: chunk sistemi durduruldu"), ()),
    (r"^Saved (\d+) block chunks, (\d+) entity chunks, (\d+) poi chunks in world '(.+)' in " + NUM + r"s$",
     N_("{3}: {0} blok, {1} varlık ve {2} POI chunk'ı {4} sn'de kaydedildi"), ()),
    (r"^Saving all chunkholders for world '(.+)'$", N_("{0}: bütün chunk'lar kaydediliyor"), ()),
    (r"^Waiting " + NUM + r"s for chunk I/O to halt for world '(.+)'$", N_("{1}: chunk G/Ç'nin durması için {0} sn bekleniyor"), ()),
    (r"^Waiting " + NUM + r"s for chunk system to halt for world '(.+)'$",
     N_("{1}: chunk sisteminin durması için {0} sn bekleniyor"), ()),
    (r"^Awaiting termination of worker pool for up to " + NUM + r"s\.\.\.$",
     N_("Çalışan havuzunun kapanması en fazla {0} sn bekleniyor..."), ()),
    (r"^Awaiting termination of I/O pool for up to " + NUM + r"s\.\.\.$", N_("G/Ç havuzunun kapanması en fazla {0} sn bekleniyor..."), ()),
    (r"^ThreadedAnvilChunkStorage \((.+)\): All chunks are saved$", N_("Chunk deposu ({0}): bütün chunk'lar kaydedildi"), ()),
    (r"^ThreadedAnvilChunkStorage: All dimensions are saved$", N_("Chunk deposu: bütün boyutlar kaydedildi"), ()),
]

PANEL = [(re.compile(rx), tpl, groups) for rx, tpl, groups in _RAW]
NOT_SECURE = N_("Doğrulanmamış")      # sohbet etiketi: "[Not Secure] <ad> mesaj" (mesajın kendisi çevrilmez)


def is_core_logger(name):
    return name in CORE_LOGGERS or name.startswith(CORE_LOGGER_PREFIXES)
