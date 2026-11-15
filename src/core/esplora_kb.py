"""Esplora'nın uzman bilgi bankası: Minecraft (Java) sunucu yönetimi hakkında elle derlenmiş bilgiler.

Her bölüm: (başlık, anahtar kelimeler, metin). Soru ve sunucu durumu anahtar kelimelerle karşılaştırılır,
en ilgili birkaç bölüm sistem istemine eklenir (tamamı her seferinde gönderilmez). Metinler İngilizcedir;
Esplora kullanıcının dilinde cevap verir. Emin olunmayan sürüm ayrıntıları burada kesinmiş gibi yazılmaz.
"""
import re

KB = [
    ("Java versions", "java jdk jre version sürüm unsupportedclassversionerror class file version requires java 25 21 17 16 8 temurin adoptium openjdk",
     """Minecraft server Java requirements (use the newest LTS that the version supports):
- 1.8 – 1.16.5: Java 8 (1.12+ also run on Java 11; many 1.16 servers run fine on 11).
- 1.17.x: Java 16 or newer.
- 1.18 – 1.20.4: Java 17 or newer.
- 1.20.5 – 1.21.x: Java 21 or newer.
- 26.1 and newer (new year-based numbering): Java 25 or newer (Paper prints "Minecraft 26.1 and newer requires running the server with Java 25 or above").
"UnsupportedClassVersionError ... class file version 65.0" means the server needs Java 21 (61 = Java 17, 65 = Java 21, 69 = Java 25) but an older Java started it.
Install on Windows: winget install EclipseAdoptium.Temurin.25.JDK (or .21.JDK). After installing, restart Spypaper (or sign out of Windows once) so the new PATH is seen. If several Javas are installed, put the full path of the right java.exe (e.g. C:\\Program Files\\Eclipse Adoptium\\jdk-25...\\bin\\java.exe, no quotes) into Spypaper → Server Settings → Java."""),

    ("Performance tuning", "lag kasma kasıyor tps mspt performance performans can't keep up gecikme view-distance simulation-distance ram entity varlık chunk aikar flags optimize spark",
     """Diagnosing lag:
- "Can't keep up! Is the server overloaded? Running Xms or Y ticks behind" = the main thread took longer than 50 ms per tick. Occasional ones during startup or world generation are normal; constant ones are not.
- Measure first: Paper has /tps and /mspt (MSPT above 50 = lag). The spark plugin/mod (/spark profiler start, then /spark profiler stop after a few minutes) shows exactly what is slow.
- Biggest levers: simulation-distance (entities/redstone ticking, 4–6 is fine for survival) and view-distance (chunks sent, 6–10). Lower simulation-distance before view-distance.
- Pre-generate the world (Chunky plugin/mod: /chunky radius 5000, /chunky start) — generating new chunks is the most expensive thing a server does.
- Entities: large mob farms, item piles and animal pens cost the most. Paper/Spigot settings: spigot.yml entity-activation-range and merge-radius (item/exp), paper-world-defaults.yml entities.spawning.per-player-mob-spawns: true, chunks.entity-per-chunk-save-limit (e.g. arrow: 16, experience_orb: 16, snowball: 8), collisions.max-entity-collisions (default 8, can go to 2–4), environment.optimize-explosions: true, entities.behavior.... Purpur adds more options.
- RAM: more is not always better. 4–6 GB suits most small/medium survival servers; 8–10 GB for large modpacks. Set -Xms equal to -Xmx. Leave at least 1.5–2 GB for Windows. Huge heaps without tuned GC cause long pauses.
- Aikar's flags (G1GC tuning) help Paper servers with 4–12 GB heaps.
- Fabric performance mods (server side): Lithium (general logic), FerriteCore (memory), Krypton (networking), ModernFix; C2ME speeds chunk generation but can conflict with other mods. On Forge/NeoForge: ModernFix, FerriteCore, Canary/Radium ports.
- Paper is much faster than Spigot/Bukkit; Purpur builds on Paper with extra options; Folia (regionized threading) breaks most plugins — only use it if plugins explicitly support it."""),

    ("Paper configuration files", "paper-global.yml paper-world-defaults.yml spigot.yml bukkit.yml purpur.yml config yml yapılandırma paper.yml",
     """Paper config layout (1.19+): config/paper-global.yml (server-wide), config/paper-world-defaults.yml (defaults for all worlds), <world>/paper-world.yml (per-world overrides). Before 1.19 it was a single paper.yml. Also spigot.yml, bukkit.yml (spawn-limits, ticks-per autosave), commands.yml, and purpur.yml on Purpur.
Common useful keys:
- bukkit.yml spawn-limits (monsters 70, animals 10, ...) and ticks-per.monster-spawns.
- spigot.yml world-settings.default.entity-activation-range, entity-tracking-range, merge-radius.item/exp, mob-spawn-range, view-distance: default (uses server.properties).
- paper-world-defaults.yml: chunks.auto-save-interval, chunks.max-auto-save-chunks-per-tick, entities.spawning.despawn-ranges, entities.spawning.per-player-mob-spawns, environment.optimize-explosions, tick-rates (e.g. grass-spread, container-update), anticheat.anti-xray (Paper's built-in anti-xray: enabled, engine-mode 1 or 2).
- paper-global.yml: proxies.velocity / bungee-cord settings, chunk-loading-basic, packet-limiter, unsupported-settings (only change if you know why).
Most config changes need a restart; /reload is unsafe and should not be used on Paper (it breaks many plugins)."""),

    ("Common startup errors", "error hata başlamıyor açılmıyor crash çöktü failed to bind port address already in use eula outofmemory exception server tick loop failed to load corrupted level.dat",
     """Common startup failures:
- "**** FAILED TO BIND TO PORT! ... Address already in use": another server (often the same one still running, or a second Spypaper/console window) is using server-port. Stop it, or change server-port in server.properties. Check with: netstat -ano | findstr 25565.
- "You need to agree to the EULA in order to run the server": set eula=true in eula.txt (Spypaper asks the owner on first start; it never accepts it automatically).
- "java.lang.OutOfMemoryError: Java heap space": raise -Xmx (Spypaper: Server Settings → RAM), or find the memory leak (a mod/plugin). "unable to create native thread" / "GC overhead limit exceeded" are memory issues too.
- "Exception in server tick loop" / crash report in crash-reports/: read the "Description" and the first "Caused by" lines and the stack frames that mention a mod/plugin package — that is usually the culprit.
- "Failed to load level.dat" / corrupted chunk: restore from backup (Spypaper Danger Zone → Restore from Backup); Paper can sometimes regenerate a corrupt chunk.
- "UnsupportedClassVersionError": wrong (too old) Java, see Java versions.
- Server closes immediately with no log: wrong jar name in Spypaper, or a modded server where the start file is not the jar (Forge/NeoForge use run.bat / @libraries/... args files)."""),

    ("Plugin loading problems", "plugin eklenti could not load unknown dependency depend softdepend ambiguous plugin name invalid plugin.yml paper-plugin.yml requires api-version bukkit spigot",
     """Plugin loading errors (Bukkit/Spigot/Paper):
- "Could not load 'plugins/X.jar' ... Unknown/missing dependency: Y": install plugin Y (check the plugin page for required dependencies like Vault, ProtocolLib, PlaceholderAPI, LuckPerms).
- "Ambiguous plugin name": two jars of the same plugin in plugins/ — remove the older one.
- "Unsupported API version" / "requires api-version 1.21": the plugin is newer than the server; update the server or use an older plugin release.
- NoClassDefFoundError / NoSuchMethodError in a plugin stack trace usually means the plugin version does not match the server version.
- Plugins (.jar for Bukkit/Spigot/Paper) and mods (Fabric/Forge/NeoForge) are different things: Paper cannot load Fabric/Forge mods and Fabric cannot load Bukkit plugins.
- After adding/removing plugins, restart the server (not /reload)."""),

    ("Mod loader problems", "mod fabric forge neoforge quilt mixin modloader incompatible mod requires fabric api dependency loader version client only side",
     """Mod server problems:
- Fabric: almost every mod needs Fabric API in mods/. "Incompatible mods found! ... requires {fabric-api}" lists the exact missing dependency and version.
- "Mixin apply failed" / "Mixin transformation ... failed" = two mods patch the same code or a mod is for a different Minecraft version.
- Client-only mods (minimaps, shaders/Iris/Sodium/OptiFine, HUD mods, zoom) must not be in the server's mods/ folder; they crash or are useless on the server.
- Forge/NeoForge: the mod's mods.toml declares required mods and version ranges; the error screen/log names them. Server configs live in config/ and per-world <world>/serverconfig/.
- Players must install the same content mods (blocks, items, mobs) as the server; server-side-only mods (performance, admin tools) don't need to be on clients.
- Keep the loader version current; many new mods require a recent Fabric Loader / NeoForge build."""),

    ("Connecting and networking", "bağlanamıyor connect connection refused timed out port forwarding port açma modem router 25565 ip tailscale playit firewall güvenlik duvarı online-mode lan",
     """Players can't connect:
- Same network: use the computer's LAN IP (e.g. 192.168.1.x:25565). Windows Firewall must allow Java (Private networks).
- Over the internet: either port-forward TCP 25565 (or the server-port) on the router to this PC's LAN IP and give players the public IP, or use a tunnel/VPN (playit.gg, Tailscale, ZeroTier) when the ISP uses CGNAT.
- "Connection refused": nothing is listening at that address/port (server stopped, wrong port, firewall). "Timed out": port forwarding or firewall issue.
- "Failed to verify username" / "Invalid session": online-mode=true requires official accounts and Mojang session servers. Offline (cracked) launchers only work with online-mode=false, which allows anyone to join with any name — then use a login plugin (AuthMe etc.) and whitelist.
- "Outdated client/server": the player's game version differs. ViaVersion (+ ViaBackwards) on Paper lets other versions join. Geyser + Floodgate lets Bedrock players join a Java server.
- Behind a proxy (Velocity/BungeeCord): backend servers set online-mode=false and enable proxy forwarding in Paper config."""),

    ("Permissions and moderation", "permission izin yetki luckperms lp op operator rank grup group ban kick whitelist moderasyon admin mod yetkili",
     """Permissions:
- Vanilla: /op gives operator; op-permission-level in server.properties (1 bypass spawn protection, 2 cheat commands/command blocks, 3 multiplayer management like kick/ban/op, 4 all incl. /stop). Avoid giving op to regular players.
- LuckPerms (the standard permissions plugin/mod): /lp user <name> permission set <node> true, /lp user <name> parent add <group>, /lp group <group> permission set <node>, /lp creategroup <name>, /lp editor (web editor), /lp user <name> info. Permission nodes are listed on each plugin's page (e.g. essentials.home, essentials.tpa).
- Whitelist: /whitelist add|remove <name>, /whitelist on|off, enforce-whitelist=true kicks non-whitelisted players when the list reloads. Ops can join even when not whitelisted.
- Bans: /ban <name> [reason], /ban-ip <ip|name>, /pardon <name>, /banlist. Stored in banned-players.json and banned-ips.json.
- Spypaper: Whitelist & Ban page manages these files; maintenance mode empties the whitelist temporarily and restores it."""),

    ("Command syntax by version", "command komut give enchant item component nbt syntax 1.20.5 1.21 sözdizimi execute tellraw summon attribute selector @a @p @e",
     """Command syntax changes that matter:
- Since 1.20.5, item data uses components instead of NBT: give @p diamond_sword[enchantments={sharpness:5}] works on 1.21.5+; on 1.20.5–1.21.4 the enchantments component was written as [enchantments={levels:{"minecraft:sharpness":5}}]. Before 1.20.5: give @p diamond_sword{Enchantments:[{id:"minecraft:sharpness",lvl:5s}]}.
- Custom names: 1.20.5+ [custom_name='"Name"'] (JSON text); 1.21.5+ text components in commands are written in SNBT (e.g. custom_name={text:"Name",color:"gold"}).
- /enchant only works up to the enchantment's normal max level and on compatible items; use give with components for higher levels.
- Selectors: @a all players, @p nearest, @r random, @s self, @e entities; filters like @e[type=zombie,distance=..20], @a[gamemode=survival].
- /execute: execute as <entity> at @s run <command>, execute in minecraft:the_nether run tp <player> x y z.
- From the server console there is no "self", so commands that rely on @s or the executor's position need explicit targets/coordinates.
- Teleport to another dimension: execute in minecraft:the_end run tp <player> 0 64 0.
If the exact syntax for the server's version is uncertain, say so and suggest testing in-game or checking the Minecraft Wiki for that version."""),

    ("Worlds, datapacks and backups", "dünya world nether end datapack veri paketi backup yedek seed level-name dimension reset sıfırla restore worldborder pregenerate chunky",
     """Worlds:
- Folder name = level-name in server.properties. Paper/Spigot store the Nether and End in separate folders (world_nether, world_the_end); Vanilla/Fabric/Forge keep them inside the world folder (DIM-1, DIM1, or dimensions/minecraft/... on newer versions).
- Datapacks go into <world>/datapacks/; manage with /datapack list|enable|disable and /reload (reload is fine for datapacks on vanilla/Fabric; on Paper prefer a restart if plugins are involved).
- Changing level-seed only affects a newly generated world. Spypaper's Danger Zone can reset dimensions with a new or the same seed and restore backups.
- Always stop the server (or run save-off + save-all flush) before copying world folders by hand.
- World border: /worldborder set <diameter>, /worldborder center <x> <z>. Pre-generate inside the border with Chunky."""),

    ("Proxies and multi-version", "velocity bungeecord waterfall proxy geyser floodgate bedrock viaversion viabackwards cross-play",
     """Proxies and cross-play:
- Velocity is the recommended proxy (BungeeCord/Waterfall are legacy). Backends: online-mode=false, Paper config proxies.velocity.enabled: true with the same secret as velocity's forwarding.secret file.
- Geyser (+ Floodgate so Bedrock players don't need a Java account) lets Bedrock Edition players join; Bedrock uses UDP 19132 by default, which must also be forwarded/allowed.
- ViaVersion lets newer clients join an older server; ViaBackwards lets older clients join a newer server; ViaRewind for very old (1.7/1.8) clients."""),

    ("Spypaper guide", "spypaper panel nerede where how to nasıl sayfa page sekme ayar settings remote telefon bakım maintenance tehlikeli danger takım team modrinth kaynak paketi resource pack ev home esplora",
     """How to do things in Spypaper (desktop panel):
- Server panel tabs: Dashboard, Live Console (command suggestions as you type), Logs, Esplora (this assistant), Players (inventory, armor, ender chest, stats, homes with teleport, account type, heads), Teams (/team management), Plugins/Mods (Installed, Modrinth search & install with version/loader filter, Resource Pack for the server), Mod Language Files, Server Settings (Java path, jar, RAM, BlueMap URL, crash auto-restart, backup limit, server.properties), Whitelist & Ban, Maintenance & Backup (maintenance mode, weekly schedule, backups), Live Map (BlueMap), Notes, Content Editor (datapack items, paintings, music discs, recipes), Danger Zone (PIN: reset world, restore backup, reset player data, delete server).
- Tabs can be reordered/hidden in ☰ → Panel Layout. Language, theme, update check and Start with Windows are in ☰.
- Safe mode (top bar) limits which console commands can be sent; High = read-only.
- Spypaper Remote (☰ → Spypaper Remote): phone access by QR code; per-device permissions for start/stop, maintenance and server settings.
- Server software updates: the Update button in the top bar."""),
]

_WORD = re.compile(r"[\w.\-@]+", re.UNICODE)


def _words(text):
    return {w.lower() for w in _WORD.findall(text or "") if len(w) > 2}


def relevant(question, extra="", limit=4, budget=7000):
    """Soru (ve sunucu durumundan ipuçları) için en ilgili bölümler: [(başlık, metin)]."""
    q = _words(question) | _words(extra)
    scored = []
    for i, (title, keys, text) in enumerate(KB):
        kw = _words(keys)
        score = len(q & kw) * 3
        low = (question or "").lower()
        score += sum(1 for k in kw if len(k) > 4 and k in low)        # kısmi eşleşme (kasıyor ~ kasma)
        if score:
            scored.append((score, -i, title, text))
    scored.sort(reverse=True)
    out, used = [], 0
    for _, _, title, text in scored[:limit]:
        if used + len(text) > budget:
            break
        out.append((title, text))
        used += len(text)
    if not out:                                     # hiçbir şey eşleşmezse Spypaper rehberi yine işe yarar
        out = [(KB[-1][0], KB[-1][2])]
    return out
