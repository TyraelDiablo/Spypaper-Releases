<p align="center"><img src="docs/logo.png" width="96" alt="Spypaper logo"></p>

# Spypaper

**English** · [Türkçe](README.tr.md)

**A desktop management panel for Minecraft servers.** Start and stop your server, watch the console live, look into player inventories, manage plugins and mods, take backups, install or update the server software in one click, view a live BlueMap, and ask **Esplora**, an AI assistant that knows your server.

Written in Python + PySide6 and built as a single `.exe` for Windows. The interface is available in 16 languages. Free and open source (GPL-3.0).

**[⬇ Download the latest release](https://github.com/TyraelDiablo/Spypaper-Releases/releases/latest)** · **[Report a bug / suggest a feature](https://github.com/TyraelDiablo/Spypaper-Releases/issues)**

> Spypaper is not an official Minecraft product. It is not approved by or associated with Mojang Studios or Microsoft.

![Dashboard](docs/screenshots/dashboard.png)

---

## Features

| Section | What it does |
|---|---|
| **Home screen** | Lists all your servers as cards; quick start/stop, edit and open folder without entering the panel. |
| **New server** | Create a server from scratch: pick the software and Minecraft version, set RAM, port, MOTD, game mode and difficulty; Spypaper downloads the server and prepares the folder. |
| **Dashboard** | Live RAM/CPU, online players, today's joins, deaths, lag warnings and errors, hourly activity chart. |
| **Live Console** | Colored console, command history, optional translation of server messages into the panel language. |
| **Log** | Events, sessions and charts from `logs/latest.log` and archived `.log.gz` files. Works even if the server was started outside the panel. |
| **Esplora** | An AI assistant (bring your own API key: Anthropic Claude, Google Gemini, OpenAI and compatible services) scoped strictly to managing this server. Preset questions by category, chat bubbles, stop and regenerate. It never runs commands itself; you send the commands it suggests with **▶ Run**. |
| **Players** | Health, hunger, armor and XP shown with Minecraft's own HUD bars, and the player's game mode. Inventory, armor and Ender chest with item icons (block items such as fences and stairs are rendered from the game's 3D models), enchantments, armor trims and durability. Item names in your language (from Minecraft's own language files). Common player commands. Supports Minecraft 26.x's new `world/players/` layout. |
| **Plugins / Mods** | Manages `plugins/` on Paper, Purpur and Spigot, and `mods/` on Fabric, Quilt, Forge and NeoForge: add, remove, disable. |
| **Mod Language Files** | Finds the English language files inside mod and plugin jars wherever they are (`assets/*/lang/en_us.json`, `lang/en.yml`, `locales/locale.json`…), JSON or YAML, flat or nested. You write the translation; the panel saves it into the jar and into the plugin's own data folder copy. Format code checks (`%s`, `%player%`, `§a`, `&c`, `<red>`), import/export, restore original. |
| **Server Settings** | `server.properties` editor, Java path, RAM, jar, server icon. |
| **Whitelist & Bans** | Whitelist, ban and op lists. |
| **Maintenance & Backups** | World backups (Overworld, Nether, End), automatic backups and maintenance mode. |
| **Live Map** | Shows the BlueMap 3D map inside the panel. If BlueMap isn't installed, it downloads the right version for your server software and Minecraft version from Modrinth and (with your consent) enables its texture download. |
| **Server Software** | Pick a version and download/install **Paper, Purpur, Vanilla, Fabric, Forge or NeoForge**. Files are verified with SHA-256 / SHA-1 where available; the old jar is moved to `backups/jars/`. |
| **Spypaper Remote** | Watch your servers from your phone and start, stop or restart them. Pair with a QR code; no app store, no account, no database. See [Spypaper Remote](#spypaper-remote-phone). |
| **Security** | 4-level safe mode (confirm, block or read-only for dangerous commands) and an optional per-server PIN. |
| **Appearance** | 7 themes, font size, high contrast, reduced motion, right-to-left languages, [Lucide](https://lucide.dev) icons, themed in-app dialogs instead of Windows message boxes. |

---

## Screenshots

| | |
|---|---|
| ![Home screen](docs/screenshots/ana-ekran.png) | ![Log](docs/screenshots/gunluk.png) |
| **Home screen:** multiple servers with status and software badges | **Log:** events and sessions from latest.log and archives |
| ![Esplora](docs/screenshots/esplora.png) | ![Mod Language Files](docs/screenshots/mod-dil-dosyalari.png) |
| **Esplora:** server-aware AI, send a suggested command in one click | **Mod Language Files:** translate plugin/mod language files side by side |
| ![Light theme](docs/screenshots/dashboard-acik-tema.png) | |
| **Light theme:** one of 7 themes | |

*Screenshots show the Turkish interface; the app follows the language you choose.*

---

## Requirements

- **Windows 10/11** (also runs on Linux and macOS from source; API key encryption uses Windows DPAPI and is Windows-only).
- **Java** matching your Minecraft version (Java 21 for 1.20.5+, Java 25 for 26.x). The panel does not install Java.
- To run from source: **Python 3.10+** and [uv](https://docs.astral.sh/uv/).

---

## Getting started

### With the exe

1. Download `Spypaper.exe` from [Releases](https://github.com/TyraelDiablo/Spypaper-Releases/releases/latest) and put it in a folder (e.g. `D:\Spypaper\`).
2. Open it → **Create New Server** to set up a fresh server, or **Add Existing** to choose a server folder you already have (the jar, version and software are detected automatically).
3. For item names and icons, use **Players → Get Game Files** (see below).

`config.json` is created next to the exe on first start. It holds your server profiles, settings and the encrypted API key, so **don't share it**.

### From source

The source code lives in the `src` folder.

```bat
src\calistir.bat
```

or

```bat
cd src
uv run --with nbtlib --with pyside6 --with psutil --with pyyaml --with segno python main.py
```

### Building the exe

```bat
src\build.bat
```

The result is `src\dist\Spypaper.exe`. The interface translations (`locales/`) and legal texts (`legal/`) are embedded in the exe. Qt WebEngine is included for the built-in map, so the exe is about 150 MB.

---

## Minecraft language files and icons

In-game texts such as item, enchantment and death message names, and the item icons, are read from Minecraft's own files. These files belong to Mojang, so they are **not distributed** with Spypaper; each user prepares them on their own computer.

Use the **Get Game Files** button on the **Players** page or **☰ → Game Files**:

1. **Extract from the Minecraft installation on this computer:** `.minecraft` is found automatically, no internet needed. You must have launched that game version from the launcher at least once.
2. **Download from Mojang's official servers:** for machines without Minecraft (e.g. a dedicated server box). The client jar is downloaded temporarily; only the language files, icons and HUD images are kept and the jar is deleted.

Block items that have no flat picture (fences, stairs, walls, slabs…) are drawn from the game's own 3D models at this step. If you prepared the game files with an older Spypaper version, run **Game Files** again to get these icons and the HUD bars.

Files are written to the `Translation` and `Icons` folders next to the exe. If you prefer the command line, `mc_dilleri_cikar.bat` does the same:

```bat
src\mc_dilleri_cikar.bat                  :: the panel's 16 languages, newest version
src\mc_dilleri_cikar.bat --surum 26.3     :: a specific version
src\mc_dilleri_cikar.bat --hepsi          :: every language in Minecraft
```

---

## Server software

The **Update** button detects your current software and offers newer builds of it; you can also switch to different software.

| Software | Source | Verification | Notes |
|---|---|---|---|
| Paper | PaperMC Fill API v3 | SHA-256 | STABLE channel only |
| Purpur | api.purpurmc.org | — | |
| Vanilla | Mojang version manifest | SHA-1 | Releases only |
| Fabric | meta.fabricmc.net | — | Server launcher jar |
| Forge | files.minecraftforge.net | SHA-1 | Runs the official installer |
| NeoForge | maven.neoforged.net | SHA-1 | Runs the official installer; beta builds are flagged |

Forge (1.17+) and NeoForge servers start from an argument file instead of a jar (`java @user_jvm_args.txt @libraries/.../win_args.txt nogui`). The panel handles this automatically.

> PaperMC asks for a User-Agent with contact information. You can enter an e-mail address or website under ☰ → General.

**Minecraft EULA:** if `eula.txt` hasn't been accepted when the server starts for the first time, the panel asks you. It never accepts the EULA on your behalf.

---

## Spypaper Remote (phone)

Watch your servers from your phone and start, stop or restart them. There is no app store app: Spypaper on your computer serves a small mobile web app, and your phone opens it in the browser. Add it to the home screen and it opens like an app (Android and iPhone).

![Spypaper Remote on a phone](docs/screenshots/remote.png)

**Setting it up**

1. In Spypaper open **☰ → Spypaper Remote** and turn it on. If Windows Firewall asks, allow access on *Private networks*.
2. Click **Pair New Device** and scan the QR code with your phone's camera. Tap **Pair** on the page that opens.
3. Done. The phone stays paired; you can remove it at any time from the same window.

**What the phone can do:** server status, RAM/CPU, players online and today's joins, each player's health, hunger, armor, level and game mode (with Minecraft-style bars), the latest log lines, a link to the BlueMap live map, and **Start / Stop / Restart**. There is no free command input.

**Security**

- Remote is off by default and only works while Spypaper is open on your computer.
- Pairing uses a one-time code that expires after 2 minutes. The phone keeps its key in an HttpOnly cookie; `config.json` only stores a SHA-256 hash of it. No database is involved.
- If a server has a PIN, the phone asks for it too (5 wrong tries lock it for 5 minutes). Safe mode *High* (read-only) blocks control from the phone, and you can turn phone control off entirely and keep it watch-only.
- IP addresses in log lines are hidden before they reach the phone.
- The connection is plain HTTP inside your own network. **Do not open a port on your router for it.** To reach it from outside (mobile data), install [Tailscale](https://tailscale.com) on the computer and the phone and pick the address marked *(Tailscale)* in the Remote window; the traffic is then encrypted by Tailscale.

![Spypaper Remote window on the desktop](docs/screenshots/remote-desktop.png)

---

## Esplora (AI assistant)

1. ☰ → **AI** → choose a provider, enter your API key → **Test Connection**.
2. Use **Fetch Models** to list the models your key can access.

| Provider | Default model | Notes |
|---|---|---|
| Anthropic (Claude) | `claude-sonnet-5-5` | |
| Google Gemini | `gemini-3.8-flash` | If a model is retired and the service suggests a new one, the panel switches automatically |
| OpenAI / compatible | `gpt-4o-mini` | Use the *Server URL* field for OpenRouter, LM Studio, Ollama, etc. |

**Privacy:** when you ask Esplora something, your question plus the server name, version, settings, plugin/mod list, player names, recent log lines and the latest crash report (if any) are sent to the AI provider you chose. See the [Privacy Notice](src/legal/PRIVACY_EN.md).

The API key is stored in `config.json`; on Windows it is encrypted with DPAPI, bound to your user account.

---

## Interface translations

UI strings are written in Turkish in the code and translated through the tables in `src/tools/translations/*.tsv`.

```bat
cd src
uv run python tools\extract_strings.py      :: lists translatable strings and anything missing
uv run python tools\build_locales.py        :: TSV -> locales\<lang>.json
```

`build_locales.py` reports an error if a translation's placeholders (`{n}`, `{name}`…) don't match the original.

Supported languages: Türkçe, English, Deutsch, Français, Español, Português (Brasil), Italiano, Nederlands, Polski, Русский, Українська, Azərbaycanca, 日本語, 한국어, 简体中文, العربية.

---

## Project layout

```
Spypaper-Releases/
├─ README.md, README.tr.md
├─ LICENSE                 GNU GPL v3
├─ docs/                  logo and README screenshots
└─ src/                    source code
   ├─ main.py              entry point
   ├─ calistir.bat         run from source
   ├─ build.bat            build the exe
   ├─ mc_dilleri_cikar.bat extract Minecraft language files from the command line
   ├─ core/                UI-independent logic
   │  ├─ config.py         settings, server profiles, jar/software detection
   │  ├─ server.py         server process (start, stop, commands)
   │  ├─ software.py       Paper/Purpur/Vanilla/Fabric/Forge/NeoForge providers
   │  ├─ updater.py        downloads and verification
   │  ├─ players.py        player data (NBT), inventory, Minecraft translations
   │  ├─ logwatch.py       latest.log tracking, events, metrics
   │  ├─ logtrans.py       translating server messages into the panel language
   │  ├─ files.py          plugins/mods folder, server.properties, backups
   │  ├─ maintenance.py    maintenance mode and automatic backups
   │  ├─ gamefiles.py      Minecraft language files and icons (local install or Mojang)
   │  ├─ iconrender.py     renders block item icons from the game's 3D models
   │  ├─ modtrans.py       mod/plugin language file editor (JSON, YAML)
   │  ├─ creator.py        creating new servers
   │  ├─ bluemap.py        BlueMap detection, Modrinth install, configuration
   │  ├─ remote.py         Spypaper Remote web server (pairing, phone API)
   │  ├─ ai.py, esplora.py AI providers, Esplora rules and preset questions
   │  ├─ safemode.py       safe mode and PIN
   │  └─ secrets.py        API key encryption
   ├─ ui/                  PySide6 interface (window, pages, themes, i18n, HUD, dialogs)
   │  └─ assets/           Spypaper logo (SVG, PNG, ICO)
   ├─ remote_web/          Spypaper Remote phone app (HTML, CSS, JS)
   ├─ locales/             compiled interface translations
   ├─ tools/               translation and Minecraft language file tools
   └─ legal/               privacy notice, third-party notices, license copy
```

---

## Roadmap

Planned next (order may change; share your ideas on [Issues](https://github.com/TyraelDiablo/Spypaper-Releases/issues)):

- [ ] **Scheduled tasks:** restart at a set time, countdown announcements, commands and backups
- [ ] **Crash watchdog:** automatic restart after an unexpected shutdown, stop after repeated crashes
- [ ] **Restore from backup** and a backup limit (delete old backups automatically)
- [ ] **Plugin and mod store:** search, install and update notices from Modrinth and Hangar
- [ ] **Discord notifications:** server started, stopped, crashed, player joined (webhook)
- [ ] **Java manager:** detect and download the right Java for your Minecraft version
- [ ] **TPS / MSPT chart** on the Dashboard
- [ ] **Config file editor** (`paper-global.yml`, `config/*.toml`…) with syntax checks
- [ ] **Self-update** via GitHub Releases
- [x] **Spypaper Remote:** watch and control servers from your phone
- [ ] Spypaper Remote: chat, player actions and notifications

---

## Troubleshooting

- **Item names are in English or icons are missing:** click **Get Game Files** on the Players page. The bottom of the page shows which language file is in use.
- **The phone can't reach Spypaper Remote:** the phone and computer must be on the same Wi-Fi (guest networks often block this), Windows Firewall must allow Spypaper on private networks, and the address in the Remote window must be your computer's local address (usually `192.168…`). If the port is busy, change it in the Remote window.
- **The server won't start:** read the error in the Live Console or ask Esplora *"Why won't the server start?"*. Make sure your Java version matches your Minecraft version.
- **Forge/NeoForge installation failed:** check that the Java path is correct and the server folder is writable; the last lines of the installer output are shown in the window.
- **Gemini/OpenAI error 429:** the provider's rate limit was reached; try again later.

---

## License

Spypaper is free and open-source software licensed under the [GNU General Public License v3](LICENSE) (GPL-3.0).
You may use, study, modify and share it free of charge. If you distribute a modified version, you must share its
source code under the same license. The program comes with no warranty.

Copyright © 2026 Serkan Aynacı ([TyraelDiablo](https://github.com/TyraelDiablo))

## Legal

- [Privacy Notice](src/legal/PRIVACY_EN.md) · [Gizlilik Bildirimi](src/legal/GIZLILIK.md)
- [Third-Party Notices](src/legal/UCUNCU_TARAF.md)

Minecraft is a trademark of Mojang Studios. Spypaper does not distribute any Minecraft files. Running a Minecraft server requires accepting the [Minecraft EULA](https://aka.ms/MinecraftEULA).
