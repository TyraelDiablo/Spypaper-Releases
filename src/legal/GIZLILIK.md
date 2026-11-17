# Spypaper Gizlilik Bildirimi

**Sürüm 1.5 · Yürürlük tarihi: 17.11.2026**

Bu bildirim, Spypaper'ın ("Yazılım") hangi verileri işlediğini, nerede sakladığını ve hangi durumlarda üçüncü taraflara gönderdiğini açıklar.

## Kısaca

- Spypaper **bilgisayarınızda çalışır**. Geliştiriciye (Serkan Aynacı) hiçbir veri göndermez. Telemetri, kullanım istatistiği, reklam ya da çökme raporu gönderimi **yoktur**.
- Dış bağlantılar sunucu yazılımı güncelleme ve Esplora'ya soru sorma gibi **sizin başlattığınız** işlemlerde kurulur. İki istisna vardır: açılışta GitHub'da yeni Spypaper sürümü olup olmadığına bakılması (bkz. 2.4) ve oyuncu kafalarının Mojang'dan indirilmesi (bkz. 2.5); ikisi de ayarlardan kapatılabilir.
- Esplora'yı kullanırsanız sunucunuza ait bilgiler (oyuncu adları ve loglar dahil) **seçtiğiniz yapay zeka sağlayıcısına** gönderilir.

## 1. Bilgisayarınızda işlenen veriler

Yazılım, yönettiğiniz Minecraft sunucusunun klasöründeki dosyaları **yerel olarak** okur ve gösterir:

| Veri | Kaynak | Amaç |
|---|---|---|
| Oyuncu adları ve UUID'leri | `usercache.json`, `whitelist.json`, `ops.json`, `banned-*.json` | Oyuncu listesi, yetki ve ban yönetimi |
| Envanter, konum, ölüm noktası, istatistikler | `world/playerdata/*.dat`, `world/stats/*.json` | Oyuncular sayfası |
| Sohbet, giriş/çıkış, ölüm, komut kayıtları | `logs/latest.log`, `logs/*.log.gz` | Konsol, Günlük ve Dashboard |
| Çökme raporları | `crash-reports/` | Esplora bağlamı (yalnızca soru sorarsanız gönderilir) |
| Sunucu ayarları | `server.properties` ve yapılandırma dosyaları | Ayarlar sayfası |

Bu veriler Yazılım tarafından ayrıca kopyalanmaz ya da bir yere yüklenmez. Yedekler, sizin seçtiğiniz sunucu klasöründeki `backups/` dizinine yazılır.

### Yazılımın kendi kaydettiği veriler

`config.json` (Yazılımın yanında):

- Panel ayarları (dil, tema, yazı boyutu…)
- Sunucu profilleri (ad, klasör yolu, Java yolu, RAM, güvenli mod seviyesi)
- **PIN**: düz metin olarak değil, PBKDF2-HMAC-SHA256 (200.000 tekrar, rastgele tuz) ile özetlenmiş halde
- **Yapay zeka API anahtarı**: Windows'ta, Windows hesabınıza bağlı DPAPI ile şifrelenmiş halde. *Windows dışındaki sistemlerde anahtar yalnızca base64 ile gizlenir; bu bir şifreleme değildir.*
- PaperMC için girdiğiniz iletişim bilgisi (girdiyseniz)
- **Spypaper Remote** eşli cihazları: cihaz adı, eşlenme ve son bağlantı zamanı, cihaza verdiğiniz izinler, seçilen dil ile cihaz anahtarının yalnızca SHA-256 özeti (anahtarın kendisi saklanmaz)
- Sunucu **notlarınız** (düz metin; parola yazmayın), otomatik bakım planı ve çökme bekçisi / yedek sınırı ayarları
- **Tehlikeli Bölge PIN'i** (sunucuda PIN yoksa belirlenir): sunucu PIN'i gibi yalnızca PBKDF2 özeti olarak
- Oyuncu **evleri** (ad, boyut, koordinatlar), Esplora için yazdığınız **sunucu bilgileri** ve İçerik Editörü'nün içerikleri
- **Hile Koruması** ayarları ve Yetki Koruması'nın izinli OP listesi (oyuncu adları)
- Bakım sürerken: bakım öncesi whitelist ve MOTD. Whitelist ayrıca sunucu klasöründe `backups/whitelist_maintenance.json` dosyasına yazılır ve bakım bitince silinir.

Oyuncu kafası görüntüleri Yazılımın yanındaki `cache/skins/`, Modrinth ikonları `cache/modrinth/` klasöründe önbelleklenir. İçerik Editörü'ne eklediğiniz resim ve sesler sunucu klasöründe `spypaper_content/` içinde durur. Hile Koruması açıksa sunucu klasöründeki `spypaper_guard/` içine doğrulanan oyuncuların adı ve doğrulama tarihi (`verified.json`) ile koruma olayları (`guard.log`: oyuncu adı ve ne olduğu) yazılır; IP adresi yazılmaz.

*Windows açılınca başlat* seçeneğini açarsanız Windows kayıt defterine (`HKCU\Software\Microsoft\Windows\CurrentVersion\Run`) Yazılımın yolu yazılır; seçeneği kapatınca silinir.

Esplora sohbetleri, *Sohbetleri bu bilgisayarda kaydet* seçeneği açıksa (varsayılan) Yazılım'ın klasöründeki `esplora_chats/<sunucu>/` altında JSON dosyaları olarak **yalnızca bu bilgisayarda** saklanır: sorularınız, Esplora'nın yanıtları, onayladığınız veri notları ve zamanları. Gönderdiğiniz **görseller kaydedilmez**, yalnızca sayıları kalır. Sunucu başına en fazla 100 sohbet tutulur, daha eskiler silinir. Bu dosyalar hiçbir yere gönderilmez; ancak kayıtlı bir sohbete devam ederseniz önceki mesajlar, her soruda olduğu gibi, seçtiğiniz yapay zeka sağlayıcısına yeniden gönderilir. Esplora → **Geçmiş**'ten sohbetleri tek tek ya da toplu silebilir, kaydetmeyi kapatabilirsiniz.

## 2. Üçüncü taraflara gönderilen veriler

### 2.1 Sunucu yazılımı indirme (Güncelle penceresi)

Güncelle penceresini açtığınızda ve indirme yaptığınızda Yazılım, seçtiğiniz yazılımın resmi sunucularına bağlanır:

| Hizmet | Adres |
|---|---|
| PaperMC | fill.papermc.io |
| PurpurMC | api.purpurmc.org |
| Mojang | piston-meta.mojang.com, piston-data.mojang.com |
| FabricMC | meta.fabricmc.net |
| Minecraft Forge | files.minecraftforge.net, maven.minecraftforge.net |
| NeoForged | maven.neoforged.net |

Gönderilenler: IP adresiniz (her internet bağlantısında olduğu gibi), istenen sürüm bilgisi ve "Spypaper/sürüm" bilgisini içeren User-Agent. PaperMC'nin istediği **iletişim bilgisini** girdiyseniz bu bilgi de User-Agent içinde gönderilir. Sunucu dosyalarınız, oyuncu verileriniz ya da loglarınız **gönderilmez**.

### 2.2 Esplora (yapay zeka asistanı)

Esplora'ya bir soru gönderdiğinizde (yazarak ya da hazır soru düğmesiyle), aşağıdakiler ☰ → Yapay Zeka Ayarları'nda **seçtiğiniz sağlayıcıya** gönderilir:

- Sorunuz, o sohbetteki önceki mesajlar ve eklediğiniz **görseller** (ekran görüntüleri; mesaj başına en fazla 4)
- Sunucu adı, yazılımı, Minecraft sürümü, durumu, jar ve Java yolu, RAM sınırları, güvenli mod seviyesi
- Çevrimiçi ve bilinen **oyuncu adları** (en fazla 60)
- Eklenti / mod listesi
- Seçili `server.properties` değerleri (MOTD, port, whitelist, zorluk vb.)
- Günün özeti (oyuncu sayısı, ölüm, gecikme, hata sayıları)
- Son **60 log satırı** (sohbet mesajları ve oyuncu adları içerebilir), son hata/uyarı satırları
- Son 7 gün içindeki **en son çökme raporunun** ilk satırları (varsa)
- Esplora için yazdığınız **sunucu bilgileri** (☰ değil, Esplora → Sunucu Bilgileri)
- Soruyla ilgiliyse sunucunun **yapılandırma dosyalarından** bölümler (ör. `spigot.yml`, `config/paper-world-defaults.yml`, sorudaki eklentinin `config.yml` dosyası). Parola, token, API anahtarı, veritabanı bilgisi ve webhook adresi gibi değerler gönderilmeden önce `***` ile değiştirilir; yine de yapılandırma dosyalarına kişisel veri yazmayın.

Aşağıdaki maddelerin hangilerinin gönderileceğini Esplora → **Veri İzinleri**'nden siz belirlersiniz: her veri türü *Erişim yok*, *Onaylı* (her istekte size sorulur) ya da *Onaysız* olabilir. Yukarıdaki liste varsayılan ayarlardır. Ayrıca, yalnızca izin verdiğinizde ve Esplora adını verdiği bir oyuncu için istediğinde şunlar da gönderilebilir:

- Oyuncu **koordinatları** (son konum, son ölüm noktası, kayıtlı evler), **gelişimleri**, **envanteri** (zırh, ikinci el, Ender sandığı dahil) ve **değerleri** (can, açlık, XP, oyun modu, istatistikler)
- Whitelist, ban ve OP listelerindeki oyuncu adları; yedek listesi ve bakım planı; takımlar ve üyeleri; İçerik Editörü içerikleri; Hile Koruması ayarları ve son olayları (oyuncu adları içerir); sunucu notlarınız (varsayılan olarak kapalı)

Bu veriler varsayılan olarak her istekte size sorulur; *Hep izin ver* derseniz o veri türü artık sorulmadan gönderilir.

Sağlayıcılar ve gizlilik politikaları:

- Anthropic: https://www.anthropic.com/legal/privacy
- Google (Gemini API): https://ai.google.dev/gemini-api/terms
- OpenAI: https://openai.com/policies/privacy-policy
- OpenAI uyumlu başka bir hizmet ya da yerel model (ör. Ollama, LM Studio): o hizmetin kendi politikası. Yerel bir model kullanırsanız veriler bilgisayarınızdan çıkmaz.

Bu sağlayıcılar verileri kendi politikalarına göre işler ve sunucuları Türkiye dışında olabilir. Esplora'yı kullanmamak tamamen sizin elinizdedir; API anahtarı girmediğiniz sürece hiçbir veri gönderilmez.

### 2.3 Spypaper Remote (telefon)

Spypaper Remote **varsayılan olarak kapalıdır**. Açarsanız Yazılım bilgisayarınızda küçük bir web sunucusu çalıştırır ve yalnızca QR kodla eşlediğiniz cihazlara şu özetleri gösterir: sunucu durumu, RAM/CPU kullanımı, oyuncu adları ile can/açlık/zırh/seviye/oyun modu ve son log satırları. Log satırlarındaki **IP adresleri gizlenir**. Bilgisayarda o cihaza izin verdiyseniz telefon sunucu ayarlarını (RAM, otomatik bakım planı, `server.properties`) görebilir ve değiştirebilir; RCON/sorgu/yönetim ayarları ve parolalar telefona gönderilmez. Telefon, panelin dili yerine kendi dilini (tarayıcının bildirdiği dil) kullanır. Bu veriler, dış erişim için Cloudflare tüneli seçmediğiniz sürece hiçbir üçüncü tarafa gönderilmez; telefonunuz ile bilgisayarınız arasında yerel ağınızda (ya da kendi kurduğunuz Tailscale gibi bir ağ üzerinden) iletilir. Bağlantı şifrelenmemiş HTTP'dir; bu yüzden yalnızca güvendiğiniz ağlarda kullanın, internete port açarak yayınlamayın. Eşli cihazları Remote penceresinden istediğiniz zaman kaldırabilirsiniz.

*Dış erişim (isteğe bağlı).* Remote penceresinde **Modemde portu otomatik aç (UPnP)** açıksa Yazılım, yerel ağınızdaki modeme UPnP ile (SSDP çok noktaya yayını ve modemin UPnP servisine istekler) panel portunu açar; kapatınca portu kapatır. Bu istekler yalnızca ağınızda kalır ve modemin dış IP adresi Remote penceresinde gösterilir. Port açmak paneli şifresiz (HTTP) internete çıkarır. **Tünel sağlayıcısı: Cloudflare** seçiliyse, sizin kurduğunuz cloudflared programı Cloudflare'in tünel ağına bağlanır ve telefonunuzdan gelen istekler Cloudflare sunucularından geçer; bu trafik [Cloudflare Gizlilik Bildirimi](https://www.cloudflare.com/privacypolicy/)'ne tabidir. **Tünel sağlayıcısı: Playit.gg** seçiliyse, sizin kurduğunuz playit programı playit.gg hesabınıza bağlanır ve istekler Playit sunucularından geçer; bu trafik Playit.gg'nin [playit.gg](https://playit.gg) sitesindeki koşullarına ve gizlilik politikasına tabidir. Yazılım tünel adresini öğrenmek için playit ajanınızın gizli anahtarıyla `api.playit.gg`'ye istek gönderir. Anahtar `playit.toml` dosyasından okunur; **Anahtar gir** ile elle girerseniz yalnızca bilgisayarınızdaki ayar dosyasında saklanır ve telefona gönderilmez. Spypaper bu trafiği saklamaz. Eşli cihazların son bağlantı zamanları dışında Remote isteklerinin kaydı tutulmaz.

### 2.4 Spypaper güncelleme denetimi

*Açılışta güncellemeleri denetle* seçeneği açıksa (varsayılan) Yazılım her açılışta GitHub'a (`api.github.com`) Spypaper'ın en son sürümünü sorar. Bu istekte yalnızca standart bağlantı bilgileri (IP adresiniz) ve Spypaper'ın sürümünü içeren bir User-Agent gönderilir; sunucularınıza, oyuncularınıza ya da ayarlarınıza ait hiçbir veri gönderilmez. Güncellemeyi kabul ederseniz yeni exe GitHub'dan indirilir ve SHA-256 özetiyle doğrulanır. GitHub'ın verileri nasıl işlediği için [GitHub Gizlilik Bildirimi](https://docs.github.com/site-policy/privacy-policies/github-general-privacy-statement)'ne bakın. Denetimi ☰ → *Açılışta güncellemeleri denetle* ile kapatabilirsiniz.

### 2.5 Oyuncu kafaları (Mojang)

*Oyuncu kafalarını göster* açıksa (varsayılan) Oyuncular sayfası, oyuncuların görünüşünü (skin) Mojang'dan indirir: lisanslı oyuncular için `sessionserver.mojang.com`'a oyuncunun UUID'si, lisanssız oyuncular için `api.mojang.com`'a oyuncu adı gönderilir; görüntü `textures.minecraft.net`'ten alınır. Görüntüler 1 gün önbelleklenir. Bkz. [Microsoft Gizlilik Bildirimi](https://privacy.microsoft.com/privacystatement). ☰ → *Oyuncu kafalarını göster* ile kapatabilirsiniz.

### 2.6 Modrinth ve Newgrounds (siz başlattığınızda)

- **Güncellemeleri denetle**'ye bastığınızda, yüklü `.jar` dosyalarınızın SHA-1 özetleri (dosyaların kendisi değil) `api.modrinth.com`'a gönderilir ve hangi sürümlerin daha yeni olduğu sorulur. Bu yalnızca siz düğmeye bastığınızda olur; arka planda kontrol yapılmaz. Bkz. [Modrinth Gizlilik Politikası](https://modrinth.com/legal/privacy).

- **Modrinth** sekmesinde arama yaptığınızda arama metniniz, seçtiğiniz Minecraft sürümü ve yükleyici `api.modrinth.com`'a gönderilir; eklenti/mod/kaynak paketi ve ikonlar `cdn.modrinth.com`'dan indirilir. Bkz. [Modrinth Gizlilik Politikası](https://modrinth.com/legal/privacy).
- **Hile Koruması** sayfasında *Kur*'a bastığınızda GrimAC anti-hile eklentisi ve bağımlılıkları, sunucu sürümünüz ve yükleyiciniz gönderilerek `api.modrinth.com` / `cdn.modrinth.com`'dan indirilir.
- **İçerik Editörü**'nde Newgrounds ID'si girip *Getir*'e bastığınızda o ID'nin sayfası `www.newgrounds.com`'dan, ses dosyası `audio.ngfiles.com`'dan indirilir. Bkz. [Newgrounds Gizlilik Politikası](https://www.newgrounds.com/wiki/help-information/privacy-policy). Parçaların hakları sanatçılarına aittir; yalnızca kullanma izniniz olan parçaları ekleyin.

### 2.7 Kaynak paketi paylaşımı

İçerik Editörü'nde *Kaynak paketini Spypaper paylaşsın* seçeneğini açarsanız Yazılım, seçtiğiniz portta (varsayılan 8766) küçük bir web sunucusu çalıştırır ve yalnızca oluşturulan kaynak paketi dosyasını verir. Paketi indiren oyuncuların IP adresleri bu bağlantıda bilgisayarınıza ulaşır ama diske kaydedilmez. **Bot Doğrulaması** açıksa bu IP adresleri ve indirme zamanları, giriş yapan oyuncunun sunucu logundaki IP'siyle karşılaştırmak için yalnızca bellekte (en fazla son 1000 indirme) tutulur ve Yazılım kapanınca silinir. Seçenek varsayılan olarak kapalıdır.

### 2.8 Diğer bağlantılar

- **Canlı Harita** sayfası, ayarladığınız harita adresini (varsayılan `http://localhost:8100`) açar.
- Çekmecedeki belge bağlantıları varsayılan tarayıcınızda açılır.

## 3. Sunucu sahibi olarak sizin sorumluluklarınız

Sunucunuza bağlanan oyuncuların kişisel verilerinin (oyuncu adı, IP adresi, sohbet içeriği) **veri sorumlusu siz**siniz; Yazılım yalnızca sizin kullandığınız bir araçtır. 6698 sayılı Kişisel Verilerin Korunması Kanunu (KVKK), GDPR ya da bulunduğunuz yerdeki mevzuat kapsamında yükümlülükleriniz olabilir. Özellikle:

- Esplora'yı kullanıyorsanız, oyuncu adları ve sohbet içeren logların yurt dışındaki bir yapay zeka sağlayıcısına aktarılabileceğini oyuncularınıza bildirmeniz gerekebilir.
- Minecraft oyuncularının bir kısmı çocuk olabilir; onların verilerini işlerken ek özen gösterin.
- Yedeklerinizi ve `config.json` dosyanızı güvenli tutun, başkalarıyla paylaşmayın.

## 4. Verilerinizi silme

- Yazılımın kaydettiği verileri silmek için `config.json` dosyasını silin.
- API anahtarınızı iptal etmek için sağlayıcınızın panelini kullanın.
- Sağlayıcıya gönderilmiş verilerin silinmesi için ilgili sağlayıcının gizlilik politikasına başvurun; Geliştiricinin bu verilere erişimi yoktur.

## 5. Değişiklikler

Bu bildirim, Yazılım güncellendiğinde değişebilir. Yeni veri gönderimi ekleyen değişiklikler sürüm notlarında belirtilir.

## 6. İletişim

Serkan Aynacı (TyraelDiablo) · Sorular ve bildirimler: [GitHub Issues](https://github.com/TyraelDiablo/Spypaper-Releases/issues)
