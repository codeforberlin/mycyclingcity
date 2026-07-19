# MCC-Bridge (Paper Plugin)

Connects a Paper **26.1.x** server to MyCyclingCity:

- **Vault economy provider** for team Velos (`velos_spendable`)
- **WebSocket client** for `SPEND_GROUP_VELOS`, `GET_TEAM_VELOS`, `SYNC_SHOP_CATALOG`, `HEARTBEAT`
- **LuckPerms team mapping** (optional)

## Build

Requires **JDK 21+** and **Gradle 8.x**:

```bash
# Gradle via SDKMAN (empfohlen)
sdk install gradle 8.12.1
sdk install java 21.0.9-amzn   # Build-JDK

cd mcc-bridge
gradle jar
# Output: build/libs/MCC-Bridge-0.1.0-SNAPSHOT.jar
```

**Hinweis Paper 26.1.2:** Die offizielle `paper-api:26.1.2.build.+` erfordert Java 25 zum Bauen.
Dieses Projekt kompiliert daher gegen `paper-api:1.21.11-R0.1-SNAPSHOT` (Java 21) und läuft auf Paper 26.1.2.

Copy the JAR to the Minecraft server `plugins/` folder.

## Dependencies on the MC server

1. **VaultUnlocked** (or Vault)
2. **LuckPerms** (recommended for team mapping)
3. **EconomyShopGUI** (shop UI)
4. **MCC Django** with WebSocket enabled

Install order (critical — MCC-Bridge must register Vault economy **before** EconomyShopGUI):

1. **VaultUnlocked** (Vault API)
2. **LuckPerms** (optional, team mapping)
3. **MCC-Bridge** (registers Velos economy via Vault)
4. **EconomyShopGUI** (needs an economy provider at startup)

After changing plugin JARs always do a **full server restart** (not `/reload`).

If `/plugins` shows EconomyShopGUI in **red**, check `logs/latest.log` for the startup error.
Common causes: no economy at ESGUI startup (wrong load order), or invalid YAML in
`plugins/EconomyShopGUI/shops/`. Backups from MCC sync: `*.yml.bak` next to each shop file.

## Configuration

Edit `plugins/MCC-Bridge/config.yml`:

```yaml
mcc:
  websocket_url: "wss://your-mcc-host/ws/minecraft/events/"
  shared_secret: "<MCC_MINECRAFT_WS_SHARED_SECRET>"
  server_id: "velo-stadt-1"
  # Keep Admin "Shop push" enabled (Django STALE_AFTER = 5 minutes)
  heartbeat_seconds: 60
```

MCC `.env`:

```env
MCC_MINECRAFT_WS_ENABLED=True
MCC_MINECRAFT_WS_SHARED_SECRET=<same-secret>
MCC_MINECRAFT_WS_ALLOWED_SERVER_IDS=velo-stadt-1
```

Map LuckPerms groups to MCC team scoreboard names:

```yaml
team:
  resolution: luckperms
  team_groups:
    team_alpha: TeamAlpha
```

## Commands

- `/mccbridge status` — connection status
- `/mccbridge reload` — reload config
- `/mccbridge synccatalog` — pull shop catalog from MCC
- `/mccbridge esguistatus` — EconomyShopGUI diagnostics
- `/mccbridge esguireload` — reload EconomyShopGUI after YAML sync

## Shop catalog

Define categories/items in MCC Admin (`/admin/minecraft/` → Katalog verwalten).
MCC-Bridge pulls the catalog via WebSocket and writes buy prices directly into
**EconomyShopGUI** shop YAML files (`plugins/EconomyShopGUI/shops/*.yml`), then runs `/sreload`.

Admin button **Shop-Preise an Minecraft pushen** triggers the same sync remotely.
