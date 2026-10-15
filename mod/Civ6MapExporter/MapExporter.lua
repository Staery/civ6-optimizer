-- Civ6 Optimizer — Map Exporter (gameplay script)
-- Dumps every plot to Lua.log, tagged with "CIV6OPT|", so the civ6-optimizer
-- tool can import the real map. Runs automatically at the start of each of your
-- turns, and once shortly after load. You can also call ExportMapForOptimizer()
-- from FireTuner's Lua console.
--
-- NOTE: a couple of API calls (GetWonderType, PlayerConfigurations) are guarded
-- with pcall because availability differs between game builds/contexts. If a
-- field is missing it degrades to "NONE" instead of erroring.

local function rowField(tbl, idx, field)
  if idx == nil or idx < 0 then return "NONE" end
  local ok, row = pcall(function() return tbl[idx] end)
  if not ok or row == nil then return "NONE" end
  return row[field] or "NONE"
end

local function safe(fn, default)
  local ok, v = pcall(fn)
  if ok and v ~= nil then return v end
  return default
end

function ExportMapForOptimizer()
  local localPlayer = Game.GetLocalPlayer()
  local w, h = Map.GetGridSize()
  local civName = safe(function()
    return PlayerConfigurations[localPlayer]:GetCivilizationTypeName()
  end, "UNKNOWN")
  local leaderName = safe(function()
    return PlayerConfigurations[localPlayer]:GetLeaderTypeName()
  end, "UNKNOWN")

  print("CIV6OPT|META|player|" .. tostring(localPlayer)
        .. "|civ|" .. tostring(civName)
        .. "|leader|" .. tostring(leaderName)
        .. "|width|" .. tostring(w) .. "|height|" .. tostring(h) .. "|wrapX|1")
  print("CIV6OPT|BEGIN")

  -- Religion / government loadout of the LOCAL player so the optimizer can auto-fill the
  -- Pantheon + belief selectors straight from the save (no manual re-entry each game):
  --   LOADOUT|pantheon|<BELIEF_*>|beliefs|<BELIEF_*,BELIEF_*,...>|government|<GOVERNMENT_*>
  -- Everything is pcall-guarded: religion/government API shape varies by build & game
  -- mode, so a missing field degrades to "NONE"/empty instead of erroring.
  -- VALIDATE: confirm GetBeliefs(religionType) returns belief indices on your build.
  do
    local pantheon = "NONE"
    local beliefs = {}
    local government = "NONE"
    local pRel = safe(function() return Players[localPlayer]:GetReligion() end, nil)
    if pRel ~= nil then
      local pIdx = safe(function() return pRel:GetPantheon() end, -1)
      if pIdx ~= nil and pIdx >= 0 then
        pantheon = rowField(GameInfo.Beliefs, pIdx, "BeliefType")
      end
      local relType = safe(function() return pRel:GetReligionTypeCreated() end, -1)
      if relType ~= nil and relType >= 0 then
        local gRel = safe(function() return Game.GetReligion() end, nil)
        local list = gRel ~= nil and safe(function() return gRel:GetBeliefs(relType) end, nil) or nil
        if type(list) == "table" then
          for _, bIdx in ipairs(list) do
            local bt = rowField(GameInfo.Beliefs, bIdx, "BeliefType")
            if bt ~= "NONE" and bt ~= pantheon then beliefs[#beliefs + 1] = bt end
          end
        end
      end
    end
    local pCul = safe(function() return Players[localPlayer]:GetCulture() end, nil)
    if pCul ~= nil then
      local gIdx = safe(function() return pCul:GetCurrentGovernment() end, -1)
      if gIdx ~= nil and gIdx >= 0 then
        government = rowField(GameInfo.Governments, gIdx, "GovernmentType")
      end
    end
    print(table.concat({"CIV6OPT", "LOADOUT", "pantheon", pantheon,
      "beliefs", table.concat(beliefs, ","), "government", government}, "|"))
  end

  -- Player kinds: PLAYER|id|kind  (major / city_state / free / barbarian).
  -- Lets the optimizer tell apart enemy CIVS from city-states / free cities /
  -- barbarians (different meaning for loyalty, blocking and display).
  for pid = 0, 63 do
    local pl = Players and Players[pid]
    if pl ~= nil and safe(function() return pl:IsAlive() end, false) then
      local kind = "major"
      if safe(function() return pl:IsBarbarian() end, false) then
        kind = "barbarian"
      else
        local lvl = safe(function()
          return PlayerConfigurations[pid]:GetCivilizationLevelTypeName()
        end, "")
        if lvl == "CIVILIZATION_LEVEL_CITY_STATE" then kind = "city_state"
        elseif lvl == "CIVILIZATION_LEVEL_FREE_CITIES" then kind = "free"
        elseif lvl ~= "CIVILIZATION_LEVEL_FULL_CIV"
               and not safe(function() return pl:IsMajor() end, true) then
          kind = "city_state"
        end
      end
      -- civType identifies a rival's civilization (-> its meta victory); for a city-state
      -- the leaderType encodes the category, e.g. LEADER_MINOR_CIV_SCIENTIFIC.
      local civType = safe(function() return PlayerConfigurations[pid]:GetCivilizationTypeName() end, "")
      local leaderType = safe(function() return PlayerConfigurations[pid]:GetLeaderTypeName() end, "")
      print(table.concat({"CIV6OPT", "PLAYER", pid, kind, civType, leaderType}, "|"))
    end
  end

  -- City roster: CITY|x|y|ownerPlayer|cityID|isCapital|population|name (name kept last
  -- because it may contain spaces). Lets the optimizer show real city names, group
  -- tiles by owning city, and estimate Amenities (which scale with population).
  local function emitCity(city, pid)
    if city == nil then return end
    local cx, cy = city:GetX(), city:GetY()
    local cid = safe(function() return city:GetID() end, -1)
    local cap = safe(function() return city:IsCapital() end, false) and 1 or 0
    local pop = safe(function() return city:GetPopulation() end, 0)
    local nm = safe(function() return Locale.Lookup(city:GetName()) end, nil)
               or safe(function() return city:GetName() end, "City")
    nm = tostring(nm):gsub("[|\r\n]", " ")
    print(table.concat({"CIV6OPT", "CITY", cx, cy, pid, cid, cap, pop, nm}, "|"))
  end
  for pid = 0, 63 do
    local pl = Players and Players[pid]
    if pl ~= nil and safe(function() return pl:IsAlive() end, false) then
      local cities = safe(function() return pl:GetCities() end, nil)
      if cities ~= nil then
        local ok = pcall(function()
          for _, city in cities:Members() do emitCity(city, pid) end
        end)
        if not ok then
          -- Some builds expose Members() as id-iterators; fall back to that shape.
          pcall(function()
            for _, cid in cities:Members() do emitCity(cities:FindID(cid), pid) end
          end)
        end
      end
    end
  end

  -- Your Settler units: SETTLER|x|y. Enables the map marker + future "first city"
  -- planner. NOTE: the Unit object method is GetType() (not GetUnitType); Members()
  -- may yield unit objects or unit IDs depending on the build, so handle both.
  pcall(function()
    local pUnits = Players[localPlayer]:GetUnits()
    for _, u in pUnits:Members() do
      local unit = u
      if type(u) == "number" then
        unit = safe(function() return pUnits:FindID(u) end, nil)
      end
      if unit ~= nil then
        local ti = safe(function() return unit:GetType() end, -1)
        local ut = rowField(GameInfo.Units, ti, "UnitType")
        if ut == "UNIT_SETTLER" then
          print(table.concat({"CIV6OPT", "SETTLER", unit:GetX(), unit:GetY()}, "|"))
        end
      end
    end
  end)

  local count = Map.GetPlotCount()
  for i = 0, count - 1 do
    local plot = Map.GetPlotByIndex(i)
    if plot ~= nil then
      local x, y = plot:GetX(), plot:GetY()
      local terrain = rowField(GameInfo.Terrains, plot:GetTerrainType(), "TerrainType")

      local feature, isNW = "NONE", 0
      local fIdx = plot:GetFeatureType()
      if fIdx ~= nil and fIdx >= 0 then
        local frow = GameInfo.Features[fIdx]
        if frow ~= nil then
          feature = frow.FeatureType or "NONE"
          if frow.NaturalWonderType ~= nil then isNW = 1 end
        end
      end

      local resource, resClass, resRevealed = "NONE", "NONE", 1
      local rIdx = plot:GetResourceType()
      if rIdx ~= nil and rIdx >= 0 then
        local rrow = GameInfo.Resources[rIdx]
        if rrow ~= nil then
          resource = rrow.ResourceType or "NONE"
          resClass = rrow.ResourceClassType or "NONE"
          -- A Strategic resource only blocks districts once its reveal tech is researched;
          -- before that you can build over it and keep access. Detect reveal via PrereqTech.
          local prereq = rrow.PrereqTech
          if prereq ~= nil then
            local techRow = GameInfo.Technologies[prereq]
            if techRow ~= nil then
              resRevealed = safe(function()
                return Players[localPlayer]:GetTechs():HasTech(techRow.Index)
              end, true) and 1 or 0
            end
          end
        end
      end

      local river = safe(function() return plot:IsRiver() end, false) and 1 or 0
      -- Count how many of the tile's 6 edges a river crosses (Dam needs >= 2). The Dam
      -- rule is "river crosses at least two sides", which IsRiver() alone can't tell.
      -- DirectionTypes 0..5 = NE, E, SE, SW, W, NW. Guarded: unsupported -> 0.
      local riverEdges = 0
      for dir = 0, 5 do
        if safe(function() return plot:IsRiverCrossingToAdjacent(dir) end, false) then
          riverEdges = riverEdges + 1
        end
      end
      local hills = safe(function() return plot:IsHills() end, false) and 1 or 0
      local owner = safe(function() return plot:GetOwner() end, -1)
      local owningCity = safe(function() return plot:GetOwningCityID() end, -1)
      -- Appeal drives Neighborhood housing, Preserve/National Park/Seaside Resort.
      local appeal = safe(function() return plot:GetAppeal() end, 0)
      -- Tile improvement (farm/mine/plantation/…) -> Industrial Zone & Observatory
      -- adjacency, housing from farms/plantations, appeal penalties from mines.
      local improvement = "NONE"
      local impIdx = safe(function() return plot:GetImprovementType() end, -1)
      if impIdx ~= nil and impIdx >= 0 then
        improvement = rowField(GameInfo.Improvements, impIdx, "ImprovementType")
      end

      local district = "NONE"
      local dIdx = safe(function() return plot:GetDistrictType() end, -1)
      if dIdx ~= nil and dIdx >= 0 then
        district = rowField(GameInfo.Districts, dIdx, "DistrictType")
      end

      local wonder = "NONE"
      local wIdx = safe(function() return plot:GetWonderType() end, -1)
      if wIdx ~= nil and wIdx >= 0 then
        wonder = rowField(GameInfo.Buildings, wIdx, "BuildingType")
      end

      print(table.concat(
        {"CIV6OPT", "TILE", x, y, terrain, feature, isNW, resource, resClass,
         river, hills, owner, district, wonder, owningCity, appeal, improvement,
         riverEdges, resRevealed}, "|"))
    end
  end

  print("CIV6OPT|END")
end

-- Auto-export at the start of your turns.
if Events ~= nil and Events.LocalPlayerTurnBegin ~= nil then
  Events.LocalPlayerTurnBegin.Add(function()
    pcall(ExportMapForOptimizer)
  end)
end

-- Auto-export once right after a save finishes loading, so religion/map data is fresh
-- without having to end a turn first. Guarded; harmless if the event is unavailable.
if Events ~= nil and Events.LoadScreenClose ~= nil then
  Events.LoadScreenClose.Add(function()
    pcall(ExportMapForOptimizer)
  end)
end

print("CIV6OPT|READY map exporter loaded")
