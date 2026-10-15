# Map Exporter mod: installation

**English** · [Русский](INSTALL_RU.md)

`Civ6MapExporter` is a small gameplay-script mod. At the start of every turn it writes the
current map to Civilization VI's `Lua.log`, and the optimizer reads it from there. This is
more accurate than screenshots and simpler than parsing save files. The mod only **reads**
the map: it does not change gameplay and does not affect saved games.

> The mod is optional. You can draw a map by hand in the editor, but importing a real game
> is what makes the tool useful mid-game.

## 1. Copy the mod into the game's Mods folder

Copy the whole `mod/Civ6MapExporter` folder from this repository to:

```text
%USERPROFILE%\Documents\My Games\Sid Meier's Civilization VI\Mods\Civ6MapExporter\
    Civ6MapExporter.modinfo
    MapExporter.lua
```

If your Documents folder is synced by OneDrive, the path is
`%USERPROFILE%\OneDrive\Documents\My Games\...` instead. Create the `Mods` folder if it does not exist.

PowerShell, run from the repository root:

```powershell
$docs = [Environment]::GetFolderPath("MyDocuments")
$mods = Join-Path $docs "My Games\Sid Meier's Civilization VI\Mods"
New-Item -ItemType Directory -Force $mods | Out-Null
Copy-Item -Recurse -Force mod\Civ6MapExporter $mods
```

## 2. Turn on Lua logging (once)

Open the game's options file:

```text
%USERPROFILE%\Documents\My Games\Sid Meier's Civilization VI\AppOptions.txt
```

Find the line below and set it to `1` (add it if it is missing):

```text
EnableLuaDebugLibrary 1
```

Without it, the game may not write `Lua.log` at all.

## 3. Enable the mod in the game

1. Start Civilization VI and open **Additional Content → Mods**.
2. Tick **Civ6 Optimizer - Map Exporter** and apply.
3. Start a new game or load a save.

The mod exports the map automatically when the loading screen closes and at the start of each
of your turns.

## 4. Import the map into the optimizer

The game writes its logs to **AppData**, not to Documents:

```text
%LOCALAPPDATA%\Firaxis Games\Sid Meier's Civilization VI\Logs\Lua.log
```

In the optimizer, open **📁 Data** and pick one of:

* **🔄 From game (live)**: the server reads `Lua.log` from the default path above. Tick
  **auto-refresh** to re-import every 12 seconds while you play.
* **⬇ Import from game (Lua.log)**: choose the file by hand (for example, a log copied from another PC).

What gets imported: terrain, features, hills, rivers, resources, natural and world wonders,
appeal, improvements, your districts and borders, city names and population, your settlers,
the civ and leader of every player, city-states, and your pantheon and beliefs. Tiles owned
by other players are marked as unavailable.

Each turn appends a new dump between `CIV6OPT|BEGIN` and `CIV6OPT|END`. The importer always
takes the latest one, so you can re-import the same file as the game goes on.

## Fallback: FireTuner, without the mod

1. In `AppOptions.txt` set `EnableTuner 1`.
2. Start **FireTuner** (part of *Sid Meier's Civilization VI Development Tools* in Steam → Library → Tools).
3. Paste the contents of `MapExporter.lua` into the Lua console and call `ExportMapForOptimizer()`.
4. Continue from step 4 above.

## Troubleshooting

| Symptom | Fix |
|---|---|
| "Lua.log not found" | Check step 2 and look in `%LOCALAPPDATA%`, not in Documents |
| "Lua.log has no CIV6OPT lines" | The mod is not enabled (step 3), or your first turn has not started yet. End the turn once |
| The mod is missing from the Mods list | The folder is in the wrong place, or the files are nested one level too deep |
| The map looks shifted and adjacency is wrong | Offset parity differs on your map type. See `_offset_to_axial` in `backend/io/lualog_parser.py` and open an issue with a piece of your `Lua.log` |
| Unknown terrain or feature types | They are listed in the import `warnings`. Open an issue with their names |
| Export stopped after installing other mods | Some framework mods (for example, *Community Extension*) change the load order. Try disabling them to check |
