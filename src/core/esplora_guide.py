"""Esplora'nın Spypaper'ı tanıması için kısa kullanım kılavuzu.

Spypaper'a yeni bir özellik eklendiğinde buraya da bir satır eklenir (README ile birlikte), böylece Esplora
"bunu nasıl yaparım?" sorularında doğru sayfayı ve düğmeyi gösterebilir. Sayfa adları {SinifAdi} yer tutucusuyla
yazılır; arayüz bunları kullanıcının panel dilindeki başlıklarla değiştirir.
"""

GUIDE = """
=== SPYPAPER GUIDE (where things are; name pages and buttons exactly as written here) ===
Home screen: server cards. Card menu: start/stop, edit, open folder, "Make a Copy" (clone a server into a new folder, world optional, ports changed automatically, logs/backups/PINs not copied), delete. "New Server": software (Paper, Purpur, Folia, Vanilla, Fabric, Forge, NeoForge, Velocity proxy), version, RAM, port, world: normal (seed, type) or a template map (Skyblock, PvP arenas, OneBlock, Parkour, Hide and Seek, Lobby) or "Import from Zip/Folder" (own map).
Top bar inside a server: Start/Stop/Restart, "Update" = Server Software window (update the jar or SWITCH software, e.g. Paper -> Fabric; with "Prepare the folder for the new software" incompatible plugins/mods are moved to backups/switch-..., Paper's world_nether/world_the_end are merged back for vanilla/mod loaders; world, player data, whitelist, bans, OPs are kept; Velocity <-> server is not possible).
Side menu: language, theme, text size, "Units" (metric or feet/miles; used for walked distance and world border size), "Spypaper Remote" (remote access and tunnel providers such as Playit.gg (optional account link) and Cloudflare), "Sleep Mode" (locks the window with a PIN), "Quit Spypaper".
{DashboardPage}: status, TPS/RAM, players, quick actions.
{ConsolePage}: live console, send commands. {LogsPage}: log viewer with translated lines, crash reports.
{MapPage}: live map. {EsploraPage}: you. Users can type / for commands (skills) and use the + button: add image, add text file, commands, create/manage skills (SKILL.md), tone settings.
{NotesPage}: owner notes. {PlayersPage}: players, inventories, last seen, skins. {TeamsPage}: teams. {AdminPage}: whitelist, bans, OPs.
{PluginsPage}: plugins/ or mods/ folder, Modrinth search and install, resource pack, "Spypaper Mods" (ready data/resource packs: flat health/hunger bars, death coordinates, items don't despawn).
{ModTransPage}: translate mod language files.
{ContentPage}: content without mods (data + resource pack, 1.21+): paintings, music discs (own sound or Newgrounds ID), custom tools/weapons and food with stats, effects, 3x3 recipes, HUD sprites. "Design..." opens the Texture Designer: pixel painting (pencil, eraser, bucket, eyedropper, mirror, undo), templates (sword, pickaxe, apple, disc...), View: flat item, block (16x16x16 cube) or 3D model (16x16x16 voxels, layer by layer, "Build from Texture"). New placeable blocks are NOT possible without mods; the cube/3D model is how the item looks in hand.
{VelocityPage} (only on a Velocity proxy): velocity.toml settings, linked servers and join order, "Add Spypaper Server" (sets modern forwarding in paper-global.yml and online-mode=false on the backend).
{SettingsPage}: panel settings (Java, RAM), World Border, "Build Height" card (Overworld min/max Y via a data pack; with "Also generate terrain in the depths" a bottom below -64 also moves terrain generation down for newly explored areas (bedrock at the new floor, deepslate in between, old areas stay empty below), presets up to -2032..2032, recommended RAM: 4 GB default, 6 GB up to Y 640, 8 GB up to 1024, more for larger; "Raise RAM" button; stop the server first, takes effect after restart; changing the bottom or lowering the top can damage an existing world; after a height change "Ignoring heightmap data ... size does not match" warnings for old chunks are harmless, the game recalculates them), server.properties with explanations. {ConfigsPage}: other config files (bukkit, spigot, paper...). {FilesPage}: file browser.
{MaintenancePage}: world backups and restore, maintenance mode, "Export as Map" (world zip without player data).
{TasksPage}: scheduled tasks (backups, restarts, commands, announcements); automatic restart after a crash is built in.
{DiscordPage}: Discord webhook/bot notifications. {GuardPage}: anti-cheat. {DangerPage}: reset world, delete server (unlock by PIN or typing the server name).
Help and bug reports: GitHub Issues of Spypaper only.
"""


def guide(names):
    """names: {"DashboardPage": "Dashboard", ...} panel dilinde. Bilinmeyen yer tutucu adıyla kalır."""
    out = GUIDE
    for k, v in names.items():
        out = out.replace("{" + k + "}", f'"{v}"')
    return out
