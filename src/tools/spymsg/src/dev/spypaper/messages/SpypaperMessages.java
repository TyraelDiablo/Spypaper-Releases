package dev.spypaper.messages;

import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.HashMap;
import java.util.Map;
import org.bukkit.command.Command;
import org.bukkit.command.CommandSender;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.Listener;
import org.bukkit.event.player.PlayerLocaleChangeEvent;
import org.bukkit.plugin.java.JavaPlugin;

/**
 * Spypaper: oyunculara giden Spypaper mesajlarını her oyuncunun kendi oyun dilinde gönderir.
 * Çeviriler Spypaper'ın yazdığı plugins/SpypaperMessages/messages.tsv dosyasındadır: "dil<TAB>anahtar<TAB>metin".
 * Oyuncunun dili yoksa aynı dilin başka bölgesi, o da yoksa en_us, o da yoksa komuttaki yedek metin kullanılır.
 *   spypaper-kick <oyuncu> <anahtar> <yedek metin...>
 *   spypaper-say <anahtar> <yedek metin...>     (herkese, "[!]" önekiyle)
 *   spypaper-locales                            (her oyuncu için "locale <ad> <dil>")
 *   spypaper-reload                             (messages.tsv'yi yeniden okur)
 */
public final class SpypaperMessages extends JavaPlugin implements Listener {
    private final Map<String, Map<String, String>> texts = new HashMap<>();
    private BotEngine bots;
    private String botError;

    @Override
    public void onEnable() {
        load();
        getServer().getPluginManager().registerEvents(this, this);
        try {
            bots = new BotEngine(this);
        } catch (Throwable t) {                     // Paper dışı (Spigot) ya da uyumsuz sürüm
            botError = t.toString();
            getLogger().warning("bots unavailable: " + botError);
        }
    }

    @Override
    public void onDisable() {
        if (bots != null) bots.removeAll();
    }

    private boolean botCommand(String[] a) {
        if (bots == null) {
            getLogger().info("bot error unavailable " + botError);
            return true;
        }
        if (a.length == 0) return false;
        try {
            switch (a[0]) {
                case "spawn": {      // spawn <ad> <dünya> x y z yaw pitch
                    org.bukkit.World w = getServer().getWorld(a[2]);
                    if (w == null) {
                        getLogger().info("bot error noworld " + a[2]);
                        return true;
                    }
                    String r = bots.spawn(a[1], w, Double.parseDouble(a[3]), Double.parseDouble(a[4]),
                            Double.parseDouble(a[5]), a.length > 6 ? Float.parseFloat(a[6]) : 0f,
                            a.length > 7 ? Float.parseFloat(a[7]) : 0f);
                    getLogger().info("bot " + ("ok".equals(r) ? "spawned " : "error " + r + " ") + a[1]);
                    return true;
                }
                case "action":       // action <ad> <none|attack|use|sneak> [aralık]
                    if (!bots.setAction(a[1], a[2], a.length > 3 ? Integer.parseInt(a[3]) : 0))
                        getLogger().info("bot error notfound " + a[1]);
                    return true;
                case "remove":
                    bots.remove(a[1]);
                    getLogger().info("bot removed " + a[1]);
                    return true;
                case "come": {       // come <bot> <oyuncu>: oyuncunun yanına (ve bakışına) taşınır
                    Player to = getServer().getPlayerExact(a[2]);
                    if (to == null || !bots.moveTo(a[1], to.getLocation()))
                        getLogger().info("bot error notfound " + a[1]);
                    else
                        getLogger().info("bot moved " + a[1]);
                    return true;
                }
                case "removeall":
                    bots.removeAll();
                    return true;
                case "list":
                    for (String n : bots.bots.keySet()) getLogger().info("bot online " + n);
                    return true;
                default:
                    return false;
            }
        } catch (Exception e) {
            getLogger().warning("bot error " + e);
            return true;
        }
    }

    private void load() {
        texts.clear();
        File f = new File(getDataFolder(), "messages.tsv");
        if (!f.isFile()) return;
        try {
            for (String line : Files.readAllLines(f.toPath(), StandardCharsets.UTF_8)) {
                String[] p = line.split("\t", 3);
                if (p.length == 3) texts.computeIfAbsent(p[0].toLowerCase(), k -> new HashMap<>()).put(p[1], p[2]);
            }
        } catch (Exception e) {
            getLogger().warning("messages.tsv: " + e);
        }
    }

    private String text(Player p, String key, String fallback) {
        String loc = p.getLocale() == null ? "en_us" : p.getLocale().toLowerCase();
        Map<String, String> m = texts.get(loc);
        if (m != null && m.containsKey(key)) return m.get(key);
        String lang = loc.contains("_") ? loc.substring(0, loc.indexOf('_') + 1) : loc + "_";
        for (Map.Entry<String, Map<String, String>> e : texts.entrySet())
            if (e.getKey().startsWith(lang) && e.getValue().containsKey(key)) return e.getValue().get(key);
        m = texts.get("en_us");
        if (m != null && m.containsKey(key)) return m.get(key);
        return fallback;
    }

    private static String join(String[] a, int from) {
        StringBuilder b = new StringBuilder();
        for (int i = from; i < a.length; i++) b.append(i > from ? " " : "").append(a[i]);
        return b.toString();
    }

    @EventHandler
    public void onLocale(PlayerLocaleChangeEvent e) {
        getLogger().info("locale " + e.getPlayer().getName() + " " + e.getLocale());
    }

    @Override
    public boolean onCommand(CommandSender sender, Command cmd, String label, String[] args) {
        switch (cmd.getName()) {
            case "spypaper-bot":
                return botCommand(args);
            case "spypaper-locales":
                for (Player p : getServer().getOnlinePlayers()) getLogger().info("locale " + p.getName() + " " + p.getLocale());
                return true;
            case "spypaper-reload":
                load();
                return true;
            case "spypaper-kick": {
                if (args.length < 2) return false;
                Player p = getServer().getPlayerExact(args[0]);
                if (p != null) p.kickPlayer(text(p, args[1], join(args, 2)));
                return true;
            }
            case "spypaper-rp": {          // spypaper-rp <url> <sha1> <true|false>: oyunculara paketi şimdi gönder
                if (args.length < 2 || !args[1].matches("[0-9a-fA-F]{40}")) return true;
                byte[] hash = new byte[20];
                for (int i = 0; i < 20; i++) hash[i] = (byte) Integer.parseInt(args[1].substring(i * 2, i * 2 + 2), 16);
                boolean force = args.length > 2 && args[2].equalsIgnoreCase("true");
                int n = 0;
                for (org.bukkit.entity.Player p : getServer().getOnlinePlayers()) {
                    p.setResourcePack(args[0], hash, force);
                    n++;
                }
                getLogger().info("resource pack sent to " + n + " players");
                return true;
            }
            case "spypaper-say": {
                if (args.length < 1) return false;
                String fb = join(args, 1);
                for (Player p : getServer().getOnlinePlayers()) p.sendMessage("§c§l[!] §e" + text(p, args[0], fb));
                return true;
            }
            default:
                return false;
        }
    }
}
