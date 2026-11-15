# Spypaper Privacy Notice

**Version 1.0 · Effective date: 14 November 2026**

> If this English version conflicts with the Turkish version ([GIZLILIK.md](GIZLILIK.md)), the Turkish version prevails.

This notice explains what data Spypaper ("Software") processes, where it is stored and when it is sent to third parties.

## In short

- Spypaper **runs on your computer**. It sends no data to the developer (Serkan Aynacı). There is **no** telemetry, usage analytics, advertising or crash reporting.
- External connections are made only for actions **you start**: updating server software and asking Esplora a question.
- If you use Esplora, information about your server (including player names and logs) is sent to **the AI provider you choose**.

## 1. Data processed on your computer

The Software **locally** reads and displays files in your Minecraft server folder:

| Data | Source | Purpose |
|---|---|---|
| Player names and UUIDs | `usercache.json`, `whitelist.json`, `ops.json`, `banned-*.json` | Player list, permissions and bans |
| Inventory, position, death location, statistics | `world/playerdata/*.dat`, `world/stats/*.json` | Players page |
| Chat, join/leave, death and command records | `logs/latest.log`, `logs/*.log.gz` | Console, Log and Dashboard |
| Crash reports | `crash-reports/` | Esplora context (sent only if you ask a question) |
| Server settings | `server.properties` and config files | Settings page |

This data is not copied elsewhere or uploaded by the Software. Backups are written to the `backups/` folder inside your server folder.

### Data the Software stores itself

`config.json` (next to the Software):

- Panel settings (language, theme, font size…)
- Server profiles (name, folder, Java path, RAM, safe mode level)
- **PIN**: not in plain text, but hashed with PBKDF2-HMAC-SHA256 (200,000 iterations, random salt)
- **AI API key**: on Windows, encrypted with DPAPI bound to your Windows account. *On other systems the key is only base64-obfuscated; this is not encryption.*
- The contact information you entered for PaperMC (if any)

Esplora chat history is kept **in memory only** and is deleted when the Software closes.

## 2. Data sent to third parties

### 2.1 Server software downloads (Update window)

When you open the Update window or download, the Software connects to the official servers of the software you select:

| Service | Address |
|---|---|
| PaperMC | fill.papermc.io |
| PurpurMC | api.purpurmc.org |
| Mojang | piston-meta.mojang.com, piston-data.mojang.com |
| FabricMC | meta.fabricmc.net |
| Minecraft Forge | files.minecraftforge.net, maven.minecraftforge.net |
| NeoForged | maven.neoforged.net |

Sent: your IP address (as with any internet connection), the requested version, and a User-Agent containing "Spypaper/version". If you entered the **contact information** PaperMC asks for, it is included in the User-Agent. Your server files, player data and logs are **not** sent.

### 2.2 Esplora (AI assistant)

When you send Esplora a question (typed or via a preset button), the following is sent to **the provider you selected** in ☰ → AI Settings:

- Your question and earlier messages in that chat
- Server name, software, Minecraft version, state, jar and Java path, RAM limits, safe mode level
- Online and known **player names** (up to 60)
- Plugin / mod list
- Selected `server.properties` values (MOTD, port, whitelist, difficulty, etc.)
- A summary of the day (player, death, lag and error counts)
- The last **60 log lines** (which may contain chat messages and player names) and recent error/warning lines
- The first lines of the **most recent crash report** from the last 7 days (if any)

Providers and their privacy policies:

- Anthropic: https://www.anthropic.com/legal/privacy
- Google (Gemini API): https://ai.google.dev/gemini-api/terms
- OpenAI: https://openai.com/policies/privacy-policy
- Any other OpenAI-compatible service or local model (e.g. Ollama, LM Studio): that service's own policy. With a local model, data does not leave your computer.

These providers process data under their own policies, and their servers may be located outside your country. Using Esplora is entirely up to you; no data is sent unless you enter an API key.

### 2.3 Spypaper Remote (phone)

Spypaper Remote is **off by default**. If you turn it on, the Software runs a small web server on your computer and shows only these summaries to devices you paired with a QR code: server status, RAM/CPU usage, player names with health/hunger/armor/level/game mode, and recent log lines. **IP addresses in log lines are hidden.** This data is not sent to any third party; it travels directly between your phone and your computer on your local network (or a network you set up yourself, such as Tailscale). The connection is unencrypted HTTP, so use it only on networks you trust and do not expose it to the internet through port forwarding. Paired devices are stored as a device name, pairing and last-seen times, and only a SHA-256 hash of the device key; you can remove them at any time in the Remote window.

### 2.4 Other connections

- The **Live Map** page opens the map address you configured (default `http://localhost:8100`).
- Documentation links in the drawer open in your default browser.

## 3. Your responsibilities as a server owner

You are the **data controller** for the personal data of players who connect to your server (player names, IP addresses, chat content); the Software is only a tool you use. You may have obligations under the GDPR, Türkiye's Law No. 6698 (KVKK) or local law. In particular:

- If you use Esplora, you may need to inform players that logs containing their names and chat may be sent to an AI provider abroad.
- Some Minecraft players may be children; take extra care with their data.
- Keep your backups and `config.json` secure and do not share them.

## 4. Deleting your data

- Delete `config.json` to remove the data the Software stores.
- Revoke your API key in your provider's dashboard.
- For data already sent to a provider, refer to that provider's privacy policy; the Developer has no access to it.

## 5. Changes

This notice may change when the Software is updated. Changes that add new data transfers will be noted in the release notes.

## 6. Contact

Serkan Aynacı (TyraelDiablo) · Questions and reports: [GitHub Issues](https://github.com/TyraelDiablo/Spypaper-Releases/issues)
