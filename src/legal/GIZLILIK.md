# Spypaper Gizlilik Bildirimi

**Sürüm 1.1 · Yürürlük tarihi: 15.11.2026**

Bu bildirim, Spypaper'ın ("Yazılım") hangi verileri işlediğini, nerede sakladığını ve hangi durumlarda üçüncü taraflara gönderdiğini açıklar.

## Kısaca

- Spypaper **bilgisayarınızda çalışır**. Geliştiriciye (Serkan Aynacı) hiçbir veri göndermez. Telemetri, kullanım istatistiği, reklam ya da çökme raporu gönderimi **yoktur**.
- Dış bağlantılar sunucu yazılımı güncelleme ve Esplora'ya soru sorma gibi **sizin başlattığınız** işlemlerde kurulur. Tek istisna, açılışta GitHub'da yeni Spypaper sürümü olup olmadığına bakılmasıdır (bkz. 2.4); bu denetim ayarlardan kapatılabilir.
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
- Sunucu **notlarınız** (düz metin; parola yazmayın) ve otomatik bakım planı
- Bakım sürerken: bakım öncesi whitelist ve MOTD. Whitelist ayrıca sunucu klasöründe `backups/whitelist_maintenance.json` dosyasına yazılır ve bakım bitince silinir.

*Windows açılınca başlat* seçeneğini açarsanız Windows kayıt defterine (`HKCU\Software\Microsoft\Windows\CurrentVersion\Run`) Yazılımın yolu yazılır; seçeneği kapatınca silinir.

Esplora sohbet geçmişi **yalnızca bellekte** tutulur; Yazılım kapatıldığında silinir.

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

- Sorunuz ve o sohbetteki önceki mesajlar
- Sunucu adı, yazılımı, Minecraft sürümü, durumu, jar ve Java yolu, RAM sınırları, güvenli mod seviyesi
- Çevrimiçi ve bilinen **oyuncu adları** (en fazla 60)
- Eklenti / mod listesi
- Seçili `server.properties` değerleri (MOTD, port, whitelist, zorluk vb.)
- Günün özeti (oyuncu sayısı, ölüm, gecikme, hata sayıları)
- Son **60 log satırı** (sohbet mesajları ve oyuncu adları içerebilir), son hata/uyarı satırları
- Son 7 gün içindeki **en son çökme raporunun** ilk satırları (varsa)

Sağlayıcılar ve gizlilik politikaları:

- Anthropic: https://www.anthropic.com/legal/privacy
- Google (Gemini API): https://ai.google.dev/gemini-api/terms
- OpenAI: https://openai.com/policies/privacy-policy
- OpenAI uyumlu başka bir hizmet ya da yerel model (ör. Ollama, LM Studio): o hizmetin kendi politikası. Yerel bir model kullanırsanız veriler bilgisayarınızdan çıkmaz.

Bu sağlayıcılar verileri kendi politikalarına göre işler ve sunucuları Türkiye dışında olabilir. Esplora'yı kullanmamak tamamen sizin elinizdedir; API anahtarı girmediğiniz sürece hiçbir veri gönderilmez.

### 2.3 Spypaper Remote (telefon)

Spypaper Remote **varsayılan olarak kapalıdır**. Açarsanız Yazılım bilgisayarınızda küçük bir web sunucusu çalıştırır ve yalnızca QR kodla eşlediğiniz cihazlara şu özetleri gösterir: sunucu durumu, RAM/CPU kullanımı, oyuncu adları ile can/açlık/zırh/seviye/oyun modu ve son log satırları. Log satırlarındaki **IP adresleri gizlenir**. Bilgisayarda o cihaza izin verdiyseniz telefon sunucu ayarlarını (RAM, otomatik bakım planı, `server.properties`) görebilir ve değiştirebilir; RCON/sorgu/yönetim ayarları ve parolalar telefona gönderilmez. Telefon, panelin dili yerine kendi dilini (tarayıcının bildirdiği dil) kullanır. Bu veriler hiçbir üçüncü tarafa gönderilmez; doğrudan telefonunuz ile bilgisayarınız arasında, yerel ağınızda (ya da kendi kurduğunuz Tailscale gibi bir ağ üzerinden) iletilir. Bağlantı şifrelenmemiş HTTP'dir; bu yüzden yalnızca güvendiğiniz ağlarda kullanın, internete port açarak yayınlamayın. Eşli cihazları Remote penceresinden istediğiniz zaman kaldırabilirsiniz.

### 2.4 Spypaper güncelleme denetimi

*Açılışta güncellemeleri denetle* seçeneği açıksa (varsayılan) Yazılım her açılışta GitHub'a (`api.github.com`) Spypaper'ın en son sürümünü sorar. Bu istekte yalnızca standart bağlantı bilgileri (IP adresiniz) ve Spypaper'ın sürümünü içeren bir User-Agent gönderilir; sunucularınıza, oyuncularınıza ya da ayarlarınıza ait hiçbir veri gönderilmez. Güncellemeyi kabul ederseniz yeni exe GitHub'dan indirilir ve SHA-256 özetiyle doğrulanır. GitHub'ın verileri nasıl işlediği için [GitHub Gizlilik Bildirimi](https://docs.github.com/site-policy/privacy-policies/github-general-privacy-statement)'ne bakın. Denetimi ☰ → *Açılışta güncellemeleri denetle* ile kapatabilirsiniz.

### 2.5 Diğer bağlantılar

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
