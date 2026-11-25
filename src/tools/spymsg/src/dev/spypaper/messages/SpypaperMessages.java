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

    @Override
    public void onEnable() {
        load();
        getServer().getPluginManager().registerEvents(this, this);
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
