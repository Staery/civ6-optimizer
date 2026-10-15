"use strict";

// ===========================================================================
// Geometry (pointy-top axial hexes, Red Blob Games conventions)
// ===========================================================================
const HEX_SIZE = 27;
const GRID_RADIUS = 7;
const VIEW_CLIP = 14;            // imported tiles kept within this many hexes of a city
const MIN_SCALE = 0.25, MAX_SCALE = 3;
const SQRT3 = Math.sqrt(3);

const canvas = document.getElementById("hex");
const ctx = canvas.getContext("2d");

// Camera: screen position of hex (0,0) plus a zoom factor. The camera is applied
// as a single ctx transform in draw(), so all per-hex drawing stays in "world"
// coordinates (hex sizes/offsets are constants) and zoom/pan come for free.
const camera = { scale: 1, ox: 0, oy: 0 };
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

// Civ 6 plot Y grows north; screen Y grows down. We flip Y so the browser map is
// oriented the same way as the in-game map (north up). A pure vertical reflection
// of a pointy-top grid is still a valid tiling, so adjacency is unaffected.
const hexToPixel = (q, r) => ({
  x: HEX_SIZE * SQRT3 * (q + r / 2),
  y: -HEX_SIZE * 1.5 * r,
});
function hexRound(qf, rf) {
  let x = qf, z = rf, y = -qf - rf;
  let rx = Math.round(x), ry = Math.round(y), rz = Math.round(z);
  const dx = Math.abs(rx - x), dy = Math.abs(ry - y), dz = Math.abs(rz - z);
  if (dx > dy && dx > dz) rx = -ry - rz;
  else if (dy > dz) ry = -rx - rz;
  else rz = -rx - ry;
  return { q: rx, r: rz };
}
function pixelToHex(px, py) {
  const x = (px - camera.ox) / camera.scale;
  const y = -(py - camera.oy) / camera.scale;   // undo the vertical flip
  return hexRound((SQRT3 / 3 * x - 1 / 3 * y) / HEX_SIZE, (2 / 3 * y) / HEX_SIZE);
}

// --- camera: responsive canvas, auto-fit, zoom ------------------------------
function resizeCanvas() {
  const b = document.getElementById("board");
  const w = Math.max(360, Math.floor(b.clientWidth));
  const h = Math.max(360, Math.floor(b.clientHeight));
  if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
}
function fitView(pad = 50) {
  resizeCanvas();
  if (!state.map.size) { camera.scale = 1; camera.ox = canvas.width / 2; camera.oy = canvas.height / 2; return; }
  let minx = Infinity, miny = Infinity, maxx = -Infinity, maxy = -Infinity;
  for (const k of state.map.keys()) {
    const { q, r } = parseKey(k);
    const { x, y } = hexToPixel(q, r);
    if (x < minx) minx = x; if (x > maxx) maxx = x;
    if (y < miny) miny = y; if (y > maxy) maxy = y;
  }
  const hw = (SQRT3 * HEX_SIZE) / 2, hh = HEX_SIZE;   // half extents of one hex
  minx -= hw; maxx += hw; miny -= hh; maxy += hh;
  const w = maxx - minx, h = maxy - miny;
  const s = clamp(Math.min((canvas.width - 2 * pad) / w, (canvas.height - 2 * pad) / h), MIN_SCALE, MAX_SCALE);
  camera.scale = s;
  camera.ox = canvas.width / 2 - s * (minx + maxx) / 2;
  camera.oy = canvas.height / 2 - s * (miny + maxy) / 2;
}
// Centre the camera on one tile (e.g. the capital) at a zoom that frames the tiles
// within `radius` of it — so a freshly loaded map opens on your city, not the whole world.
function focusView(center, radius = 7, pad = 60) {
  resizeCanvas();
  let minx = Infinity, miny = Infinity, maxx = -Infinity, maxy = -Infinity, n = 0;
  for (const k of state.map.keys()) {
    const { q, r } = parseKey(k);
    if (hexDistance({ q, r }, center) > radius) continue;
    const { x, y } = hexToPixel(q, r);
    if (x < minx) minx = x; if (x > maxx) maxx = x;
    if (y < miny) miny = y; if (y > maxy) maxy = y;
    n++;
  }
  if (!n) { fitView(); return; }                       // capital not in loaded tiles -> fall back
  const hw = (SQRT3 * HEX_SIZE) / 2, hh = HEX_SIZE;
  minx -= hw; maxx += hw; miny -= hh; maxy += hh;
  const w = maxx - minx, h = maxy - miny;
  const s = clamp(Math.min((canvas.width - 2 * pad) / w, (canvas.height - 2 * pad) / h), MIN_SCALE, MAX_SCALE);
  camera.scale = s;
  camera.ox = canvas.width / 2 - s * (minx + maxx) / 2;
  camera.oy = canvas.height / 2 - s * (miny + maxy) / 2;
}
function zoomAt(px, py, factor) {
  const ns = clamp(camera.scale * factor, MIN_SCALE, MAX_SCALE);
  const k = ns / camera.scale;
  camera.ox = px - k * (px - camera.ox);
  camera.oy = py - k * (py - camera.oy);
  camera.scale = ns;
  draw();
}
const hexDistance = (a, b) =>
  (Math.abs(a.q - b.q) + Math.abs(a.r - b.r) + Math.abs(a.q + a.r - b.q - b.r)) / 2;
const key = (q, r) => `${q},${r}`;
const parseKey = (k) => { const [q, r] = k.split(",").map(Number); return { q, r }; };

// ===========================================================================
// Visual vocabulary (game-like icons)
// ===========================================================================
const TERRAIN_COLOR = {
  grassland: "#5d8a3a", plains: "#bcab53", desert: "#dcc88a", tundra: "#9cae9b",
  snow: "#dde7ee", mountain: "#6b6b70", coast: "#3f93cf", ocean: "#235f8f", lake: "#4fb3d0",
};
const TERRAIN_NAME = {
  grassland: "Луга", plains: "Равнины", desert: "Пустыня", tundra: "Тундра",
  snow: "Снег", mountain: "Горы", coast: "Прибрежные", ocean: "Океан", lake: "Озеро",
};
const DISTRICT_ICON = {
  city_center: "⭐", campus: "🔬", holy_site: "🛐", theater_square: "🎭",
  commercial_hub: "💰", harbor: "⚓", industrial_zone: "⚙️", aqueduct: "💧",
  dam: "🌊", canal: "🚢", entertainment_complex: "🎡", water_park: "🎠",
  encampment: "⚔️", government_plaza: "🏛️", neighborhood: "🏘️",
  aerodrome: "✈️", spaceport: "🚀", preserve: "🌲", diplomatic_quarter: "🤝",
};
const DISTRICT_COLOR = {
  city_center: "#f0b429", campus: "#3f8fd0", holy_site: "#c9a6e6", theater_square: "#b06fd0",
  commercial_hub: "#e0b53a", harbor: "#2aa9a0", industrial_zone: "#c8763a", aqueduct: "#4ab0d0",
  dam: "#3a86c8", canal: "#3a86c8", entertainment_complex: "#d05a9a", water_park: "#d05a9a",
  encampment: "#c0453a", government_plaza: "#9a8654", neighborhood: "#7a9a6a",
  aerodrome: "#8a93a0", spaceport: "#8a93a0", preserve: "#4f8a4a", diplomatic_quarter: "#7aa0c0",
};
// Official RU district names (civilopedia). Neighborhood = «Пригород» (was «Квартал»).
const DISTRICT_NAME = {
  city_center: "Центр города", campus: "Кампус", holy_site: "Святое место",
  theater_square: "Театральная площадь", commercial_hub: "Центр коммерции", harbor: "Гавань",
  industrial_zone: "Промышленная зона", aqueduct: "Акведук", dam: "Плотина", canal: "Канал",
  entertainment_complex: "Развлекательный комплекс", water_park: "Аквапарк",
  encampment: "Военный лагерь", government_plaza: "Правительственная площадь",
  neighborhood: "Пригород", aerodrome: "Аэродром", spaceport: "Космопорт",
  preserve: "Заповедник", diplomatic_quarter: "Дипломатический квартал",
};
const FEATURE_ICON = {
  woods: "🌲", rainforest: "🌴", marsh: "🍃", floodplains: "🏞️", oasis: "🏝️",
  reef: "🐠", ice: "🧊", geothermal_fissure: "♨️", volcanic_soil: "🌋", natural_wonder: "🌟",
};
const FEATURE_NAME = {
  woods: "Лес", rainforest: "Тропики", marsh: "Болото", floodplains: "Пойма", oasis: "Оазис",
  reef: "Риф", ice: "Лёд", geothermal_fissure: "Гейзер", volcanic_soil: "Вулк. почва",
  natural_wonder: "Чудо природы",
};
const IMPROVEMENT_ICON = {
  mine: "⛏️", quarry: "🪨", farm: "🌾", pasture: "🐄", plantation: "🌳",
  lumber_mill: "🪵", fishing_boats: "🎣",
};
const IMPROVEMENT_NAME = {
  mine: "Шахта", quarry: "Карьер", farm: "Ферма", pasture: "Пастбище",
  plantation: "Плантация", lumber_mill: "Лесопилка", fishing_boats: "Рыбол. лодки",
};
const RES_CAT_COLOR = { bonus: "#f2f2f2", luxury: "#cf6ee0", strategic: "#ef5350" };
const RES_CAT_NAME = { bonus: "бонусный", luxury: "роскошь", strategic: "стратегический" };

// Foreign/blocked tiles are tagged "rival<player>" by the importer; everything
// else (incl. real city names like "Washington") is our own / neutral land.
const isForeign = (owner) => owner != null && /^rival/.test(String(owner));

// ===========================================================================
// State
// ===========================================================================
const defaultTile = () => ({
  terrain: "grassland", feature: "none", hills: false, on_river: false,
  river_edges: null,  // # river edges (from game export); null = unknown (manual map)
  resource: null, resource_class: null, resource_revealed: null,
  improvement: "none", appeal: 0, wonder: null,
  natural_wonder: null, district: null, owner_city: null, volcano: false,
  owner_kind: null,   // foreign tile kind: major / city_state / free / barbarian
});

// colour foreign tiles by who owns them (so enemy civs ≠ city-states ≠ free cities)
const FOREIGN_FILL = {
  major: "rgba(200,50,40,0.38)", city_state: "rgba(230,170,40,0.40)",
  free: "rgba(150,90,200,0.40)", barbarian: "rgba(120,40,30,0.48)",
};
const FOREIGN_STROKE = {
  major: "rgba(220,70,60,0.7)", city_state: "rgba(240,190,60,0.85)",
  free: "rgba(180,120,230,0.8)", barbarian: "rgba(150,60,50,0.9)",
};
const FOREIGN_NAME = {
  major: "чужая цивилизация", city_state: "город-государство",
  free: "вольный город", barbarian: "варвары",
};
// marker glyph + solid label colours for foreign city centers on the map
const FOREIGN_ICON = {
  major: "⚔️", city_state: "🛡️", free: "🏳️", barbarian: "☠️",
};
const FOREIGN_LABEL = {
  major:      { bg: "#c8322a", fg: "#ffffff" },
  city_state: { bg: "#e6b23a", fg: "#241a00" },
  free:       { bg: "#9a64cf", fg: "#ffffff" },
  barbarian:  { bg: "#7a3326", fg: "#ffffff" },
};

const state = {
  map: new Map(),
  cityNames: new Map(),   // "q,r" of a city center -> real name (from game/import)
  cityPop: new Map(),     // "q,r" of a city center -> population (for district build order)
  rivalCities: [],        // [{q,r,population}] enemy cities (loyalty pressure in settle)
  settlers: [],           // [{q,r}] your Settler positions (future first-city planner)
  meta: null,
  resourceCat: {},        // resource name -> category
  nwByKey: {},            // natural wonder key -> {name, tiles, ...}
  tool: { type: "pan" },   // start in navigation mode so the map doesn't get painted by accident
  requested: new Set(["campus", "holy_site", "commercial_hub", "harbor", "industrial_zone", "theater_square"]),
  civ: "generic",
  leader: "none",
  pantheon: "none",
  secretSociety: "none",
  cityOrder: [],          // city-center keys in founding/import order; [0] = capital
  beliefs: new Set(),     // chosen religion beliefs (keys)
  planSites: null,        // recommended NEW city sites from the joint empire planner
  civList: [],
  modifiers: new Set(),
  weights: {},
  ocWeight: 0.3,
  turnPenalty: 2.0,
  regionWeight: 0.6,
  result: null,
  lastRun: null,          // action that produced the visible result (re-run on language switch)
  suggestions: null,
  wonderRecs: null,
  takenWonders: new Set(),
  liveMtime: null,
  liveSnap: null,
  autoTimer: null,
  hover: null,
};

function freshBoard() {
  state.map.clear();
  state.cityOrder = [];
  for (let q = -GRID_RADIUS; q <= GRID_RADIUS; q++)
    for (let r = -GRID_RADIUS; r <= GRID_RADIUS; r++)
      if (Math.abs(q + r) <= GRID_RADIUS) state.map.set(key(q, r), defaultTile());
}
function cityCenters() {
  // ONLY your own city centers. Imported maps also contain rival / city-state
  // centers (district === "city_center"); those are foreign (owner_city "rivalN",
  // owner_kind !== "own") and must NOT be treated as your cities — otherwise settle
  // suggestions, amenities and housing get anchored to the whole map.
  const out = [];
  for (const [k, t] of state.map)
    if (t.district === "city_center" && !isForeign(t.owner_city) && t.owner_kind !== "major"
        && t.owner_kind !== "city_state" && t.owner_kind !== "free" && t.owner_kind !== "barbarian")
      out.push(k);
  // order by founding/import order so cityCenters()[0] is ALWAYS the capital
  const rank = (k) => { const i = state.cityOrder.indexOf(k); return i < 0 ? 1e9 : i; };
  out.sort((a, b) => rank(a) - rank(b));
  return out.map(parseKey);
}
function cityCenter() { return cityCenters()[0] || null; }
// capital ordering: first placed/imported city center is the capital
function rememberCity(k) { if (!state.cityOrder.includes(k)) state.cityOrder.push(k); }
function forgetCity(k) { const i = state.cityOrder.indexOf(k); if (i >= 0) state.cityOrder.splice(i, 1); }
function cityNameAt(i) { return i === 0 ? "Capital" : tr("Город {0}", i + 1); }
// real in-game name if we have one for this center, else a positional fallback
function centerName(c, i) { return state.cityNames.get(key(c.q, c.r)) || cityNameAt(i); }

// ===========================================================================
// Rendering
// ===========================================================================
function hexCorners(cx, cy) {
  const pts = [];
  for (let i = 0; i < 6; i++) {
    const a = (Math.PI / 180) * (60 * i - 30);
    pts.push([cx + HEX_SIZE * Math.cos(a), cy + HEX_SIZE * Math.sin(a)]);
  }
  return pts;
}
function pathHex(cx, cy) {
  const pts = hexCorners(cx, cy);
  ctx.beginPath();
  pts.forEach((p, i) => (i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])));
  ctx.closePath();
}
function emoji(text, x, y, px) {
  ctx.font = `${px}px "Segoe UI Emoji", "Segoe UI Symbol", sans-serif`;
  ctx.textAlign = "center"; ctx.textBaseline = "middle";
  ctx.fillText(text, x, y);
}

function drawBadge(x, y, dtype, rec) {
  const R = 15;
  if (rec) {
    ctx.save();
    ctx.shadowColor = "#f0b429"; ctx.shadowBlur = 12;
    ctx.beginPath(); ctx.arc(x, y, R + 3, 0, Math.PI * 2);
    ctx.strokeStyle = "#f7c948"; ctx.lineWidth = 3; ctx.stroke();
    ctx.restore();
  }
  ctx.beginPath(); ctx.arc(x, y, R, 0, Math.PI * 2);
  ctx.fillStyle = DISTRICT_COLOR[dtype] || "#888"; ctx.fill();
  ctx.lineWidth = 2; ctx.strokeStyle = "#0b0e12"; ctx.stroke();
  emoji(DISTRICT_ICON[dtype] || "▫️", x, y + 1, 17);
}
// Infrastructure recommendation marker (Aqueduct/Neighborhood/Plaza/…): dashed teal
// ring + the district icon + a small ➕, to read as "also build here" vs the solid
// yellow optimizer placements.
function drawRecBadge(x, y, dtype) {
  const R = 14;
  ctx.save();
  ctx.setLineDash([4, 3]);
  ctx.beginPath(); ctx.arc(x, y, R, 0, Math.PI * 2);
  ctx.fillStyle = "rgba(20,40,50,0.55)"; ctx.fill();
  ctx.lineWidth = 2.5; ctx.strokeStyle = "#46d3c0"; ctx.stroke();
  ctx.restore();
  emoji(DISTRICT_ICON[dtype] || "▫️", x, y + 1, 15);
  ctx.font = "bold 11px 'Segoe UI', sans-serif"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
  ctx.fillStyle = "#46d3c0"; ctx.fillText("➕", x + 11, y - 10);
}
function recMap() {
  const m = new Map();
  const ch = state.result && state.result.city_health;
  if (!ch) return m;
  for (const c of (ch.cities || [])) for (const r of (c.recommend || []))
    if (r.q != null) m.set(key(r.q, r.r), r);
  return m;
}
function roundRectPath(rx, ry, w, h, rad) {
  ctx.beginPath();
  ctx.moveTo(rx + rad, ry);
  ctx.arcTo(rx + w, ry, rx + w, ry + h, rad);
  ctx.arcTo(rx + w, ry + h, rx, ry + h, rad);
  ctx.arcTo(rx, ry + h, rx, ry, rad);
  ctx.arcTo(rx, ry, rx + w, ry, rad);
  ctx.closePath();
}
function drawBonusPill(x, y, value) {
  const w = 26, h = 15, top = y + 16;
  roundRectPath(x - w / 2, top, w, h, 7);
  ctx.fillStyle = "#1a1300"; ctx.fill();
  ctx.lineWidth = 1.5; ctx.strokeStyle = "#f0b429"; ctx.stroke();
  ctx.fillStyle = "#ffd24a"; ctx.font = "bold 11px 'Segoe UI', sans-serif";
  ctx.textAlign = "center"; ctx.textBaseline = "middle";
  ctx.fillText("+" + value, x, top + h / 2 + 0.5);
}

// Distinct colour per city so its districts read as ONE group on the map and in the
// results list. Indexed by city order (same as the centres list).
const CITY_PALETTE = ["#ff8a8a", "#6fb4ff", "#74e08a", "#f2b65c", "#c79cf0", "#4fd4c2",
                      "#ffd66b", "#ef8fc4", "#a3d65f", "#8fd0ff", "#ff9e6b", "#b0a7ff"];
function hexA(hex, a) {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}
// Authoritative ordered city names: the optimizer's own list (so a placement's
// ``city`` ALWAYS matches), falling back to the centre names before a run.
function cityOrder() {
  const r = state.result;
  if (r && r.cities && r.cities.length) return r.cities.slice();
  if (r && r.city) return [r.city];
  return cityCenters().map((c, i) => centerName(c, i));
}
// name -> colour and name -> number (1-based), tying map markers to the results list.
function ensureCityColors() {
  const col = {}, num = {};
  cityOrder().forEach((name, i) => { col[name] = CITY_PALETTE[i % CITY_PALETTE.length]; num[name] = i + 1; });
  state._cityColors = col;
  state._cityNums = num;
  return col;
}
// small numbered disc (city #) in the tile's top-left corner — unambiguous even when
// two cities' colours look similar
function drawCityTag(x, y, num, color) {
  const cx = x - 12, cy = y - 12;
  ctx.beginPath(); ctx.arc(cx, cy, 7, 0, Math.PI * 2);
  ctx.fillStyle = color; ctx.fill();
  ctx.lineWidth = 1.5; ctx.strokeStyle = "#000"; ctx.stroke();
  ctx.fillStyle = "#1a1205"; ctx.font = "bold 9px 'Segoe UI', sans-serif";
  ctx.textAlign = "center"; ctx.textBaseline = "middle";
  ctx.fillText(String(num), cx, cy + 0.5);
}

function draw() {
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.setTransform(camera.scale, 0, 0, camera.scale, camera.ox, camera.oy);
  const centers = cityCenters();
  ensureCityColors();
  const nearestCityIdx = (q, r) => {            // which city's territory this tile is in
    let best = -1, bd = 99;
    for (let i = 0; i < centers.length; i++) {
      const d = hexDistance({ q, r }, centers[i]);
      if (d < bd) { bd = d; best = i; }
    }
    return bd <= 3 ? best : -1;
  };
  const placedAt = new Map();
  if (state.result) for (const p of state.result.placements) placedAt.set(key(p.q, p.r), p);
  const recAt = recMap();   // infrastructure recommendations (Aqueduct/Neighborhood/…)

  {
    for (const [k, t] of state.map) {
      const { q, r } = parseKey(k);
      const { x, y } = hexToPixel(q, r);

      pathHex(x, y);
      ctx.fillStyle = t ? TERRAIN_COLOR[t.terrain] || "#444" : "#11151a";
      ctx.fill();
      ctx.lineWidth = 1; ctx.strokeStyle = "#0d1014"; ctx.stroke();
      if (!t) continue;

      // hills shading (bottom-right triangle)
      if (t.hills && t.terrain !== "mountain") {
        ctx.beginPath();
        ctx.moveTo(x + 6, y + 14); ctx.lineTo(x + 18, y + 14); ctx.lineTo(x + 12, y + 4);
        ctx.closePath(); ctx.fillStyle = "rgba(0,0,0,0.22)"; ctx.fill();
      }
      // city work-radius ring — tinted by the nearest (owning) city so each city's
      // territory reads as one colour group
      const oci = nearestCityIdx(q, r);
      if (oci >= 0) {
        const col = (state._cityColors && state._cityColors[centerName(centers[oci], oci)])
          || CITY_PALETTE[oci % CITY_PALETTE.length];
        pathHex(x, y); ctx.lineWidth = 1.5; ctx.strokeStyle = hexA(col, 0.35); ctx.stroke();
      }
      // foreign / blocked tile — colour by owner kind (civ / city-state / free / barb)
      if (isForeign(t.owner_city)) {
        const fk = t.owner_kind || "major";
        pathHex(x, y); ctx.fillStyle = FOREIGN_FILL[fk] || FOREIGN_FILL.major; ctx.fill();
        ctx.lineWidth = 1.5; ctx.strokeStyle = FOREIGN_STROKE[fk] || FOREIGN_STROKE.major; ctx.stroke();
      }
      // river edges
      if (t.on_river) { pathHex(x, y); ctx.lineWidth = 3; ctx.strokeStyle = "#7fd6ff"; ctx.stroke(); }

      // mountain / volcano glyph
      if (t.volcano && !t.district) emoji("🌋", x, y, 18);
      else if (t.terrain === "mountain" && !t.district) emoji("⛰️", x, y, 18);

      // feature (top)
      if (t.feature && t.feature !== "none") emoji(FEATURE_ICON[t.feature] || "•", x, y - 15, 14);
      // improvement (bottom-left)
      if (t.improvement && t.improvement !== "none") emoji(IMPROVEMENT_ICON[t.improvement] || "•", x - 13, y + 13, 12);
      // resource dot (bottom-right), colour by category
      if (t.resource) {
        const cat = state.resourceCat[t.resource] || "bonus";
        ctx.beginPath(); ctx.arc(x + 14, y + 12, 4, 0, Math.PI * 2);
        ctx.fillStyle = RES_CAT_COLOR[cat]; ctx.fill();
        ctx.lineWidth = 1; ctx.strokeStyle = "#000"; ctx.stroke();
      }
      // built World Wonder — solid gold ring + glyph so the whole tile reads as a
      // wonder (the dashed coloured rings are *recommendations*; name label below)
      if (t.wonder) {
        pathHex(x, y); ctx.fillStyle = "rgba(240,200,60,0.16)"; ctx.fill();
        ctx.lineWidth = 3; ctx.strokeStyle = "#e8b84b"; ctx.stroke();
        emoji("🏛️", x, y - 2, 18);
      }
      // natural wonder short name (centre)
      if (t.natural_wonder) {
        const nwName = (state.nwByKey[t.natural_wonder] && state.nwByKey[t.natural_wonder].name) || t.natural_wonder;
        ctx.fillStyle = "#ffe9a8"; ctx.font = "bold 8px 'Segoe UI', sans-serif";
        ctx.textAlign = "center"; ctx.textBaseline = "middle";
        ctx.fillText(nwName.length > 9 ? nwName.slice(0, 8) + "…" : nwName, x, y + 3);
      }

      // existing district badge
      if (t.district) drawBadge(x, y, t.district, false);

      // recommended placement (optimizer yield districts) — outline the tile in its
      // city's colour so you can see at a glance which district belongs to which city
      const rec = placedAt.get(k);
      if (rec) {
        const cc = (state._cityColors && state._cityColors[rec.city]) || "#f0c84e";
        pathHex(x, y); ctx.lineWidth = 3; ctx.strokeStyle = cc; ctx.stroke();
        drawBadge(x, y, rec.district, true); drawBonusPill(x, y, rec.displayed);
        const num = state._cityNums && state._cityNums[rec.city];
        if (num) drawCityTag(x, y, num, cc);   // city # on the tile -> see list
      }
      // recommended infrastructure (housing/amenity/plaza/preserve/canal) — if the
      // tile is free and not already an optimizer placement
      const ir = recAt.get(k);
      if (ir && !rec && !t.district) drawRecBadge(x, y, ir.district);

      // hover outline
      if (state.hover && state.hover.q === q && state.hover.r === r) {
        pathHex(x, y); ctx.lineWidth = 2; ctx.strokeStyle = "#ffffff"; ctx.stroke();
      }
    }
  }

  // city name labels (above each center) + a thick city-colour ring on the centre tile,
  // so the label colour matches the district outlines and the results-panel dot
  centers.forEach((c, i) => {
    const { x, y } = hexToPixel(c.q, c.r);
    const label = centerName(c, i);
    const col = (state._cityColors && state._cityColors[label]) || CITY_PALETTE[i % CITY_PALETTE.length];
    const num = (state._cityNums && state._cityNums[label]) || (i + 1);
    pathHex(x, y); ctx.lineWidth = 3.5; ctx.strokeStyle = col; ctx.stroke();
    ctx.font = "bold 10px 'Segoe UI', sans-serif";
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    const text = `#${num} ${label}`;
    const w = ctx.measureText(text).width + 8;
    roundRectPath(x - w / 2, y - 31, w, 14, 7);
    ctx.fillStyle = col; ctx.fill();
    ctx.fillStyle = "#1a1205"; ctx.fillText(text, x, y - 24);
  });

  // foreign cities: enemy civs (⚔️ red), city-states (🛡️ amber), free cities (🏳️),
  // barbarians (☠️). Drawn only where their territory is loaded, so the marker sits
  // on visible tiles. THIS is what makes city-states / other civs distinguishable.
  for (const c of state.rivalCities || []) {
    if (!state.map.has(key(c.q, c.r))) continue;
    const fk = c.kind || "major";
    const { x, y } = hexToPixel(c.q, c.r);
    pathHex(x, y);
    ctx.lineWidth = 2.5; ctx.strokeStyle = FOREIGN_STROKE[fk] || FOREIGN_STROKE.major; ctx.stroke();
    emoji(FOREIGN_ICON[fk] || "⚔️", x, y - 1, 17);
    ctx.font = "bold 10px 'Segoe UI', sans-serif";
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    const lab = FOREIGN_LABEL[fk] || FOREIGN_LABEL.major;
    const label = c.name || tr(FOREIGN_NAME[fk]);
    const w = ctx.measureText(label).width + 8;
    roundRectPath(x - w / 2, y - 31, w, 14, 7);
    ctx.fillStyle = lab.bg; ctx.fill();
    ctx.fillStyle = lab.fg; ctx.fillText(label, x, y - 24);
  }

  // your Settler(s): where the next/first city can be founded
  for (const s of state.settlers || []) {
    const { x, y } = hexToPixel(s.q, s.r);
    pathHex(x, y);
    ctx.save(); ctx.setLineDash([3, 2]);
    ctx.lineWidth = 2.5; ctx.strokeStyle = "#5cc8ff"; ctx.stroke();
    ctx.restore();
    emoji("🚩", x, y - 1, 20);
    ctx.font = "bold 10px 'Segoe UI', sans-serif";
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    const label = tr("Поселенец");
    const w = ctx.measureText(label).width + 8;
    roundRectPath(x - w / 2, y + 9, w, 13, 6);
    ctx.fillStyle = "rgba(92,200,255,0.95)"; ctx.fill();
    ctx.fillStyle = "#04233a"; ctx.fillText(label, x, y + 15.5);
  }

  // settle suggestions overlay
  if (state.suggestions) {
    state.suggestions.forEach((s, i) => {
      const { x, y } = hexToPixel(s.q, s.r);
      pathHex(x, y);
      ctx.fillStyle = "rgba(70,211,154,0.20)"; ctx.fill();
      ctx.save(); ctx.setLineDash([4, 3]);
      ctx.lineWidth = 2.5; ctx.strokeStyle = "#46d39a"; ctx.stroke();
      ctx.restore();
      emoji("🏙️", x, y - 2, 16);
      const tag = `#${i + 1}·${s.score}`;
      ctx.font = "bold 10px 'Segoe UI', sans-serif";
      ctx.textAlign = "center"; ctx.textBaseline = "middle";
      const w = ctx.measureText(tag).width + 8;
      roundRectPath(x - w / 2, y + 9, w, 13, 6);
      ctx.fillStyle = "rgba(70,211,154,0.95)"; ctx.fill();
      ctx.fillStyle = "#06231a"; ctx.fillText(tag, x, y + 15.5);
    });
  }

  // joint-planner NEW city sites — gold ⭐ markers ("found a city here"), with the
  // district plan for them already drawn as recommended placements above.
  if (state.planSites) {
    // a NEW city's number = its index in the optimizer's city list (existing cities
    // first, then the new sites in order) — so its ⭐ marker, its district tags and the
    // results list all show the SAME number and colour.
    const existingCount = ((state.result && state.result.existing_cities) || []).length;
    state.planSites.forEach((s, i) => {
      const cnum = existingCount + i + 1;
      const col = CITY_PALETTE[(cnum - 1) % CITY_PALETTE.length];
      const { x, y } = hexToPixel(s.q, s.r);
      pathHex(x, y);
      ctx.fillStyle = hexA(col, 0.22); ctx.fill();
      ctx.save(); ctx.setLineDash([5, 3]);
      ctx.lineWidth = 3; ctx.strokeStyle = col; ctx.stroke();
      ctx.restore();
      emoji("⭐", x, y - 2, 18);
      const tag = tr("новый #{0}", cnum);
      ctx.font = "bold 10px 'Segoe UI', sans-serif";
      ctx.textAlign = "center"; ctx.textBaseline = "middle";
      const w = ctx.measureText(tag).width + 8;
      roundRectPath(x - w / 2, y + 9, w, 13, 6);
      ctx.fillStyle = col; ctx.fill();
      ctx.fillStyle = "#1a1205"; ctx.fillText(tag, x, y + 15.5);
    });
  }

  // world-wonder recommendations overlay — shown like districts, coloured by AI risk.
  // A wonder can't share a tile with a district / city / another wonder, so DON'T stack
  // the marker on a recommended-district tile or an already-occupied one (that looked
  // like "a wonder and a city on the same tile"). The wonder still appears in the list.
  if (state.wonderRecs) {
    const planKeys = new Set((state.planSites || []).map((s) => key(s.q, s.r)));
    state.wonderRecs.forEach((w, i) => {
      const wk = key(w.q, w.r);
      const wt = state.map.get(wk);
      // a wonder needs its own free tile — skip recommended-district tiles, occupied
      // tiles (incl. city centres, which carry a district) and new-city ⭐ tiles
      if (placedAt.has(wk) || planKeys.has(wk) || (wt && (wt.district || wt.wonder))) return;
      const { x, y } = hexToPixel(w.q, w.r);
      const col = RISK_COLOR[w.risk] || "#f0b429";
      pathHex(x, y);
      ctx.fillStyle = "rgba(240,200,60,0.18)"; ctx.fill();
      ctx.save(); ctx.setLineDash([4, 3]);
      ctx.lineWidth = 3; ctx.strokeStyle = col; ctx.stroke();
      ctx.restore();
      emoji("🏛️", x, y - 2, 15);
      // label "чудо ★N" — NOT "#N·★N", whose "#N" looked like a CITY number
      const tag = tr("чудо ★{0}", w.value);
      ctx.font = "bold 10px 'Segoe UI', sans-serif";
      ctx.textAlign = "center"; ctx.textBaseline = "middle";
      const wd = ctx.measureText(tag).width + 8;
      roundRectPath(x - wd / 2, y + 9, wd, 13, 6);
      ctx.fillStyle = col; ctx.fill();
      ctx.fillStyle = "#241a00"; ctx.fillText(tag, x, y + 15.5);
    });
  }
}
// AI-takeover risk colour for wonder markers (low/med/high)
const RISK_COLOR = {
  "низкий": "#46d39a", "средний": "#f0b429", "высокий": "#e06a5a",
  low: "#46d39a", medium: "#f0b429", high: "#e06a5a",
};

// ===========================================================================
// Painting
// ===========================================================================
function applyTool(q, r, erase) {
  const k = key(q, r);
  const outsideManualBoard =
    Math.abs(q + r) > GRID_RADIUS || Math.abs(q) > GRID_RADIUS || Math.abs(r) > GRID_RADIUS;
  if (!state.map.has(k) && outsideManualBoard) return;  // imported tiles are editable anywhere
  let t = state.map.get(k);
  if (!t) { t = defaultTile(); state.map.set(k, t); }
  if (erase) {
    if (t && t.district === "city_center") forgetCity(k);   // keep capital ordering correct
    state.map.set(k, defaultTile()); state.result = null; state.suggestions = null; state.wonderRecs = null; state.planSites = null; draw(); return;
  }

  const tool = state.tool;
  switch (tool.type) {
    case "terrain": t.terrain = tool.value; if (tool.value === "mountain") t.hills = false; break;
    case "feature": t.feature = tool.value; break;
    case "improvement": t.improvement = tool.value; break;
    case "hills": t.hills = !t.hills; break;
    case "river": t.on_river = !t.on_river; break;
    case "volcano": t.volcano = !t.volcano; if (t.volcano) t.terrain = "mountain"; break;
    case "resource":
      if (t.resource === tool.value) { t.resource = null; t.resource_class = null; }
      else { t.resource = tool.value; t.resource_class = tool.cls || null; }
      break;
    case "wonder": t.wonder = t.wonder ? null : "World Wonder"; break;
    case "natural_wonder":
      if (t.natural_wonder === tool.value) { t.natural_wonder = null; t.feature = "none"; }
      else { t.natural_wonder = tool.value; t.feature = "natural_wonder"; }
      break;
    case "owner": t.owner_city = tool.value; break;
    case "district":
      if (tool.value === "city_center") {
        // multiple city centers allowed — each is its own city. Track founding ORDER so
        // the FIRST placed city is always the capital (cityCenters() sorts by this).
        t.district = (t.district === "city_center") ? null : "city_center";
        if (t.district === "city_center") { t.owner_city = "Capital"; rememberCity(k); }
        else forgetCity(k);
      } else {
        t.district = t.district === tool.value ? null : tool.value;
      }
      break;
  }
  state.result = null;
  state.suggestions = null;
  state.wonderRecs = null;
  draw();
}

let painting = false, paintErase = false;
let panning = false, panStart = null;
const eventHex = (e) => {
  const rect = canvas.getBoundingClientRect();
  return pixelToHex(e.clientX - rect.left, e.clientY - rect.top);
};
canvas.addEventListener("contextmenu", (e) => e.preventDefault());
canvas.addEventListener("mousedown", (e) => {
  const panTool = state.tool && state.tool.type === "pan";
  // pan with the middle button, Shift+left, or when the "move map" tool is active
  if (e.button === 1 || (e.button === 0 && (e.shiftKey || panTool))) {
    panning = true;
    panStart = { x: e.clientX, y: e.clientY, ox: camera.ox, oy: camera.oy };
    canvas.style.cursor = "grabbing";
    e.preventDefault();
    return;
  }
  if (panTool) return;            // brush disabled — no accidental painting while moving
  painting = true; paintErase = e.button === 2;
  const h = eventHex(e); applyTool(h.q, h.r, paintErase);
});
window.addEventListener("mouseup", () => {
  painting = false; panning = false;
  canvas.style.cursor = (state.tool && state.tool.type === "pan") ? "grab" : "crosshair";
});
window.addEventListener("mousemove", (e) => {
  if (!panning) return;
  camera.ox = panStart.ox + (e.clientX - panStart.x);
  camera.oy = panStart.oy + (e.clientY - panStart.y);
  draw();
});
canvas.addEventListener("mousemove", (e) => {
  if (panning) return;
  const h = eventHex(e); state.hover = h;
  const t = state.map.get(key(h.q, h.r));
  const c = cityCenter();
  let extra = c ? tr("  ·  до центра: {0}", hexDistance(h, c)) : "";
  if (t && t.resource) extra += tr("  ·  ресурс: {0}", t.resource);
  if (t && t.natural_wonder) {
    const nw = state.nwByKey[t.natural_wonder];
    extra += tr("  ·  чудо природы: {0}", nw ? nw.name + " (" + nw.tiles + tr(" кл.)") : t.natural_wonder);
  }
  if (t && t.wonder)
    extra += tr("  ·  🏛️ {0} (построено)", t.wonder === "World Wonder" ? tr("чудо света") : t.wonder);
  if (t && isForeign(t.owner_city)) extra += `  ·  ${tr(FOREIGN_NAME[t.owner_kind || "major"])}`;
  const ir = recMap().get(key(h.q, h.r));
  if (ir) extra += `  ·  ➕ ${nm(DISTRICT_NAME, ir.district)}: ${ir.why}`;
  const wr = (state.wonderRecs || []).find((w) => w.q === h.q && w.r === h.r);
  if (wr) extra += tr("  ·  🏛️ {0} (★{1}): {2} · риск ИИ {3}", wr.name, wr.value, wr.requires, wr.risk);
  document.getElementById("coord-readout").textContent = `(${h.q}, ${h.r})${extra}`;
  if (painting) applyTool(h.q, h.r, paintErase); else draw();
});
canvas.addEventListener("wheel", (e) => {
  e.preventDefault();
  const rect = canvas.getBoundingClientRect();
  const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
  zoomAt(e.clientX - rect.left, e.clientY - rect.top, factor);
}, { passive: false });

// ===========================================================================
// UI building
// ===========================================================================
function makeTool(label, tool, swatch, icon) {
  const el = document.createElement("div");
  el.className = "tool";
  if (swatch) { const s = document.createElement("span"); s.className = "swatch"; s.style.background = swatch; el.appendChild(s); }
  if (icon) el.appendChild(document.createTextNode(icon + " "));
  el.appendChild(document.createTextNode(label));
  el.onclick = () => {
    state.tool = tool;
    canvas.style.cursor = tool.type === "pan" ? "grab" : "crosshair";
    document.querySelectorAll("#tool-groups .tool").forEach((n) => n.classList.remove("active"));
    el.classList.add("active");
  };
  if (JSON.stringify(tool) === JSON.stringify(state.tool)) el.classList.add("active");
  return el;
}
function toolGroup(title, tools, open = true) {
  const g = document.createElement("details"); g.className = "tool-group"; g.open = open;
  const s = document.createElement("summary"); s.className = "label"; s.textContent = title; g.appendChild(s);
  const box = document.createElement("div"); box.className = "tools";
  tools.forEach((tl) => box.appendChild(tl)); g.appendChild(box);
  return g;
}
function buildPalette(meta) {
  const root = document.getElementById("tool-groups"); root.innerHTML = "";

  root.appendChild(toolGroup(tr("Навигация"), [
    makeTool(tr("Двигать карту (кисть выкл.)"), { type: "pan" }, null, "✋"),
  ]));

  root.appendChild(toolGroup(tr("Террейн"), meta.terrains.map((v) =>
    makeTool(nm(TERRAIN_NAME, v), { type: "terrain", value: v }, TERRAIN_COLOR[v]))));

  root.appendChild(toolGroup(tr("Особенности"), meta.features.map((v) =>
    v === "none" ? makeTool(tr("нет"), { type: "feature", value: "none" })
                 : makeTool(nm(FEATURE_NAME, v), { type: "feature", value: v }, null, FEATURE_ICON[v]))));

  root.appendChild(toolGroup(tr("Улучшения"), meta.improvements.map((v) =>
    v === "none" ? makeTool(tr("нет"), { type: "improvement", value: "none" })
                 : makeTool(nm(IMPROVEMENT_NAME, v), { type: "improvement", value: v }, null, IMPROVEMENT_ICON[v])), false));

  root.appendChild(toolGroup(tr("Переключатели"), [
    makeTool(tr("Холмы"), { type: "hills" }, null, "◣"),
    makeTool(tr("Река"), { type: "river" }, "#7fd6ff"),
    makeTool(tr("Чудо света"), { type: "wonder" }, null, "🏛️"),
    makeTool(tr("Вулкан"), { type: "volcano" }, null, "🌋"),
  ]));

  root.appendChild(toolGroup(tr("Чудеса природы (число = клеток)"), (meta.natural_wonders || []).map((w) =>
    makeTool(`${w.name} (${w.tiles})`, { type: "natural_wonder", value: w.key }, null, "🌟")), false));

  // resources by category — the tool carries its class so painting can block districts
  // on luxuries/strategics (can't build there in Civ 6).
  const resTools = [makeTool(tr("нет"), { type: "resource", value: null, cls: null })];
  for (const cat of ["bonus", "luxury", "strategic"])
    for (const name of (meta.resources[cat] || []))
      resTools.push(makeTool(name, { type: "resource", value: name, cls: cat }, RES_CAT_COLOR[cat]));
  root.appendChild(toolGroup(tr("Ресурсы (•=бонус ●=роскошь ●=страт.)"), resTools, false));

  root.appendChild(toolGroup(tr("Владение клеткой"), [
    makeTool(tr("Своя"), { type: "owner", value: "Capital" }, "#5d8a3a"),
    makeTool(tr("Чужая/занято"), { type: "owner", value: "rival" }, "#c8322a"),
    makeTool(tr("Ничья"), { type: "owner", value: null }, "#11151a"),
  ]));

  // every district can be marked as already-built (so the optimizer locks it)
  const districtTools = ["city_center", "campus", "holy_site", "theater_square",
    "commercial_hub", "harbor", "industrial_zone", "aqueduct", "dam", "canal",
    "entertainment_complex", "water_park", "encampment", "government_plaza",
    "diplomatic_quarter", "neighborhood", "preserve", "aerodrome", "spaceport"]
    .map((v) => makeTool(nm(DISTRICT_NAME, v), { type: "district", value: v }, DISTRICT_COLOR[v], DISTRICT_ICON[v]));
  root.appendChild(toolGroup(tr("Существующие районы"), districtTools));

  buildLegend(meta);
}

function buildLegend(meta) {
  const L = document.getElementById("legend");
  const badge = (d) => `<span class="lg-badge" style="background:${DISTRICT_COLOR[d]}">${DISTRICT_ICON[d]}</span>`;
  const rows = [];
  rows.push(tr('<div class="lg-h">Районы</div>'));
  // every district that can be drawn/recommended — so no icon is a mystery (e.g. 🚢 = Канал)
  const legendDistricts = [
    "city_center", ...meta.optimizable_districts,
    "aqueduct", "dam", "canal", "government_plaza", "diplomatic_quarter",
    "entertainment_complex", "water_park", "encampment", "neighborhood", "preserve",
    "aerodrome", "spaceport",
  ];
  for (const d of legendDistricts)
    if (DISTRICT_ICON[d]) rows.push(`<div class="lg-row">${badge(d)}<span>${nm(DISTRICT_NAME, d)}</span></div>`);
  rows.push(tr('<div class="lg-h">Особенности</div>'));
  for (const f of meta.features.filter((f) => f !== "none"))
    rows.push(`<div class="lg-row"><span class="lg-ic">${FEATURE_ICON[f] || "•"}</span><span>${nm(FEATURE_NAME, f)}</span></div>`);
  rows.push(tr('<div class="lg-h">Обозначения</div>'));
  rows.push(tr('<div class="lg-row wide"><span class="lg-ic">🌟</span><span>чудо природы (Святое место +2 за каждую соседнюю клетку)</span></div>'));
  rows.push(tr('<div class="lg-row"><span class="lg-line"></span><span>река (граница клетки)</span></div>'));
  rows.push(tr('<div class="lg-row"><span class="lg-ic">◣</span><span>холмы</span></div>'));
  rows.push(tr('<div class="lg-row"><span class="lg-dot" style="background:#f2f2f2"></span><span>ресурс: бонусный</span></div>'));
  rows.push(tr('<div class="lg-row"><span class="lg-dot" style="background:#cf6ee0"></span><span>ресурс: роскошь</span></div>'));
  rows.push(tr('<div class="lg-row"><span class="lg-dot" style="background:#ef5350"></span><span>ресурс: стратегический</span></div>'));
  rows.push(tr('<div class="lg-row"><span class="lg-ring"></span><span>рекомендация (+бонус)</span></div>'));
  rows.push(tr('<div class="lg-h">Чужие границы (не строить)</div>'));
  rows.push(tr('<div class="lg-row"><span class="lg-blocked" style="background:rgba(200,50,40,0.4);border-color:rgba(220,70,60,0.8)"></span><span>чужая цивилизация</span></div>'));
  rows.push(tr('<div class="lg-row"><span class="lg-blocked" style="background:rgba(230,170,40,0.45);border-color:rgba(240,190,60,0.9)"></span><span>город-государство</span></div>'));
  rows.push(tr('<div class="lg-row"><span class="lg-blocked" style="background:rgba(150,90,200,0.45);border-color:rgba(180,120,230,0.9)"></span><span>вольный город</span></div>'));
  L.innerHTML = rows.join("");
}

function buildCivSelect(meta) {
  const sel = document.getElementById("civ-select");
  state.civList = meta.civs || [];
  sel.innerHTML = "";
  for (const c of state.civList) {
    const o = document.createElement("option"); o.value = c.key; o.textContent = c.label; sel.appendChild(o);
  }
  sel.value = state.civ;
  const note = document.getElementById("civ-note");
  const showNote = () => {
    const c = state.civList.find((x) => x.key === state.civ);
    note.textContent = c && c.note ? c.note : "";
  };
  sel.onchange = () => { state.civ = sel.value; showNote(); buildLeaderSelect(state.meta); updateFocusLine(); };
  showNote();
}

function buildLeaderSelect(meta) {
  const sel = document.getElementById("leader-select");
  const note = document.getElementById("leader-note");
  const all = meta.leaders || [];
  const list = all.filter((l) => l.key === "none" || l.civ === state.civ);
  sel.innerHTML = "";
  for (const l of list) {
    const o = document.createElement("option"); o.value = l.key; o.textContent = l.label; sel.appendChild(o);
  }
  if (!list.some((l) => l.key === state.leader)) state.leader = "none";
  sel.value = state.leader;
  const showNote = () => {
    const l = all.find((x) => x.key === state.leader);
    note.textContent = l && l.note ? l.note : "";
  };
  sel.onchange = () => { state.leader = sel.value; showNote(); updateFocusLine(); };
  showNote();
}

// Map the in-game civ/leader type names (from the export META) to our keys and
// auto-select them, then transfer the victory focus to that civ.
function _civKeyFromGame(name) {
  if (!name) return null;
  const k = String(name).replace(/^CIVILIZATION_/, "").toLowerCase();
  return (state.civList || []).some((c) => c.key === k) ? k : null;
}
function _leaderKeyFromGame(name, civLeaders) {
  if (!name) return null;
  const s = String(name).replace(/^LEADER_/, "").toLowerCase().replace(/[^a-z]/g, "");
  for (const l of civLeaders) {
    const k = l.key.replace(/[^a-z]/g, "");
    if (k && (s.includes(k) || k.includes(s))) return l.key;
  }
  return null;
}
function applyImportLoadout(data) {
  const meta = data.meta || {};
  const civKey = _civKeyFromGame(meta.civ);
  if (!civKey) return;
  state.civ = civKey;
  const civLeaders = (state.meta.leaders || []).filter((l) => l.civ === civKey);
  state.leader = _leaderKeyFromGame(meta.leader, civLeaders) || (civLeaders[0] ? civLeaders[0].key : "none");
  const civSel = document.getElementById("civ-select"); if (civSel) civSel.value = civKey;
  const c = state.civList.find((x) => x.key === civKey);
  const cn = document.getElementById("civ-note"); if (cn) cn.textContent = c && c.note ? c.note : "";
  buildLeaderSelect(state.meta);
  const ls = document.getElementById("leader-select"); if (ls) ls.value = state.leader;
  updateFocusLine();
  applyFocus();             // transfer weights/districts to this civ's victory focus
}

// Auto-fill the Pantheon + belief selectors straight from the save (LOADOUT line).
// Only applies keys the selectors actually know; unknown game types are skipped so the
// dropdowns never break. Re-applied on every import (incl. live polling) — the tool
// mirrors the game's current religion choices.
function applyReligionLoadout(lo) {
  if (!lo) return;
  if (lo.pantheon) {
    const sel = document.getElementById("pantheon-select");
    if (sel && [...sel.options].some((o) => o.value === lo.pantheon)) {
      state.pantheon = lo.pantheon; sel.value = lo.pantheon;
      if (sel.onchange) sel.onchange();
    }
  }
  if (Array.isArray(lo.religion_beliefs) && lo.religion_beliefs.length) {
    const known = new Set((state.meta.beliefs || []).map((b) => b.key));
    const picks = lo.religion_beliefs.filter((k) => known.has(k));
    if (picks.length) {
      state.beliefs = new Set(picks);
      buildBeliefSelects(state.meta);   // re-render the 4 slots with these selected
    }
  }
}

function buildPantheonSelect(meta) {
  const sel = document.getElementById("pantheon-select");
  const note = document.getElementById("pantheon-note");
  const list = meta.pantheons || [];
  sel.innerHTML = "";
  for (const p of list) {
    const o = document.createElement("option"); o.value = p.key;
    // ✓ = the optimizer accounts for it; otherwise it's advisory (yields/growth only)
    o.textContent = p.key === "none" ? p.label : (p.modeled ? "✓ " : "• ") + p.label;
    sel.appendChild(o);
  }
  if (!list.some((p) => p.key === state.pantheon)) state.pantheon = "none";
  sel.value = state.pantheon;
  const showNote = () => {
    const p = list.find((x) => x.key === state.pantheon);
    if (!p || p.key === "none") { note.textContent = ""; return; }
    const tag = p.modeled ? tr("✓ учитывается в расчёте. ") : tr("• совет (на расчёт размещения не влияет). ");
    note.textContent = tag + (p.note || "");
  };
  sel.onchange = () => { state.pantheon = sel.value; showNote(); };
  showNote();
}

function buildSecretSelect(meta) {
  const sel = document.getElementById("secret-select");
  const note = document.getElementById("secret-note");
  const list = meta.secret_societies || [];
  sel.innerHTML = "";
  for (const s of list) {
    const o = document.createElement("option"); o.value = s.key; o.textContent = s.label; sel.appendChild(o);
  }
  if (!list.some((s) => s.key === state.secretSociety)) state.secretSociety = "none";
  sel.value = state.secretSociety;
  const showNote = () => {
    const s = list.find((x) => x.key === state.secretSociety);
    note.textContent = s && s.note ? s.note : "";
  };
  sel.onchange = () => { state.secretSociety = sel.value; showNote(); };
  showNote();
}

// One compact dropdown per belief slot (Founder/Follower/Worship/Enhancer) — matches the
// game's religion slots and replaces the long checkbox list. state.beliefs holds the picks.
const BELIEF_SLOTS = [
  ["founder", "belief-founder"], ["follower", "belief-follower"],
  ["worship", "belief-worship"], ["enhancer", "belief-enhancer"],
];
function buildBeliefSelects(meta) {
  const list = meta.beliefs || [];
  const rebuild = () => {
    state.beliefs = new Set();
    for (const [, id] of BELIEF_SLOTS) {
      const v = document.getElementById(id).value;
      if (v) state.beliefs.add(v);
    }
  };
  for (const [cat, id] of BELIEF_SLOTS) {
    const sel = document.getElementById(id);
    if (!sel) continue;
    sel.innerHTML = "";
    const none = document.createElement("option"); none.value = ""; none.textContent = tr("— нет —");
    sel.appendChild(none);
    for (const b of list.filter((x) => x.category === cat)) {
      const o = document.createElement("option"); o.value = b.key;
      o.textContent = (b.modeled ? "✓ " : "") + b.label;   // ✓ = учитывается в расчёте
      o.title = b.note || "";
      if (state.beliefs.has(b.key)) o.selected = true;
      sel.appendChild(o);
    }
    sel.onchange = rebuild;
  }
}

// --- victory-focus helpers ---------------------------------------------------
function currentCivMeta() { return (state.civList || []).find((c) => c.key === state.civ) || null; }
function currentLeaderMeta() {
  return ((state.meta && state.meta.leaders) || []).find((l) => l.key === state.leader) || null;
}
function effectiveVictory() {
  const lead = currentLeaderMeta();
  if (lead && lead.victory) return lead.victory;
  const civ = currentCivMeta();
  return civ ? civ.victory : "";
}
const VICTORY_LABEL = {
  science: "научная", culture: "культурная", domination: "военная (доминирование)",
  religious: "религиозная", diplomatic: "дипломатическая", gold: "экономическая",
};
function updateFocusLine() {
  const line = document.getElementById("focus-line");
  const btn = document.getElementById("btn-apply-focus");
  const civ = currentCivMeta();
  const vic = effectiveVictory();
  if (!vic) {
    line.textContent = civ && civ.unique ? civ.unique : tr("Выбери циву — подскажу предпочтительную победу и веса.");
    btn.style.display = "none";
    return;
  }
  const rec = (civ && civ.recommend) ? civ.recommend.map((d) => nm(DISTRICT_NAME, d)).join(", ") : "";
  let txt = tr("Рекомендуемая победа: <b>{0}</b>. Районы: {1}.", nm(VICTORY_LABEL, vic), rec);
  if (civ && civ.unique) txt += tr("<br>Уникальное: {0}", civ.unique);
  line.innerHTML = txt;
  btn.style.display = "";
}
function applyFocus() {
  const civ = currentCivMeta();
  const vic = effectiveVictory();
  if (!civ || !vic) return;
  // weights: start from 1.0, overlay the civ's focus preset (leader override uses civ preset)
  for (const y of (state.meta.yields || [])) state.weights[y] = 1.0;
  for (const [y, w] of Object.entries(civ.focus || {})) state.weights[y] = w;
  buildWeights(state.meta);
  // pre-check the recommended districts (keep any the player already wants)
  for (const d of (civ.recommend || [])) state.requested.add(d);
  buildDistrictPicker(state.meta);
  // reset the focus line to its base text, then show exactly one confirmation
  // (otherwise repeated clicks / re-imports stack the "✓ применено" line).
  updateFocusLine();
  const line = document.getElementById("focus-line");
  line.innerHTML += tr("<br><span style=\"color:var(--accent)\">✓ применено: веса и районы под {0} победу.</span>", nm(VICTORY_LABEL, vic));
}

// Extra districts the optimizer can also lay out (off by default). Aqueduct/Dam/Canal and
// the Government Plaza are added AUTOMATICALLY when they help (synergy infra, one Plaza per
// empire), so they're not listed here to avoid double-requesting.
const EXTRA_DISTRICTS = ["encampment", "entertainment_complex", "water_park", "preserve",
  "neighborhood", "diplomatic_quarter", "aerodrome", "spaceport"];

function buildDistrictPicker(meta) {
  const root = document.getElementById("district-picker"); root.innerHTML = "";
  const add = (d) => {
    const lab = document.createElement("label");
    const cb = document.createElement("input"); cb.type = "checkbox"; cb.checked = state.requested.has(d);
    cb.onchange = () => { cb.checked ? state.requested.add(d) : state.requested.delete(d); };
    lab.appendChild(cb);
    lab.insertAdjacentHTML("beforeend",
      ` <span class="lg-badge sm" style="background:${DISTRICT_COLOR[d]}">${DISTRICT_ICON[d]}</span> ${nm(DISTRICT_NAME, d)}`);
    root.appendChild(lab);
  };
  meta.optimizable_districts.forEach(add);
  const sub = document.createElement("div"); sub.className = "pick-sub";
  sub.textContent = tr("Прочие районы");
  root.appendChild(sub);
  EXTRA_DISTRICTS.forEach(add);
  const note = document.createElement("p"); note.className = "hint";
  note.textContent = tr("Акведук/Плотина/Канал и Правительственная площадь добавляются автоматически, когда полезны.");
  root.appendChild(note);
}
function buildModifierPicker(meta) {
  const root = document.getElementById("modifier-picker"); root.innerHTML = "";
  if (!meta.modifiers.length) { root.innerHTML = tr('<p class="hint">нет</p>'); return; }
  // Modifiers bound to any civ/leader are applied automatically by selecting that
  // civ/leader — don't also offer them as manual toggles (would double-apply).
  // Pantheon-driven modifiers live in the Пантеон dropdown, so skip them here too.
  const bound = new Set();
  for (const c of meta.civs || []) for (const n of c.modifiers || []) bound.add(n);
  for (const l of meta.leaders || []) for (const n of l.modifiers || []) bound.add(n);
  for (const p of meta.pantheons || []) if (p.modifier) bound.add(p.modifier);
  meta.modifiers.forEach((m) => {
    if (bound.has(m.name)) return; // civ/leader/pantheon-driven
    const lab = document.createElement("label");
    const cb = document.createElement("input"); cb.type = "checkbox"; cb.checked = state.modifiers.has(m.name);
    cb.onchange = () => { cb.checked ? state.modifiers.add(m.name) : state.modifiers.delete(m.name); };
    lab.appendChild(cb); lab.appendChild(document.createTextNode(` ${m.label}`));
    lab.title = m.note || "";
    root.appendChild(lab);
  });
}
function buildWeights(meta) {
  const root = document.getElementById("weights"); root.innerHTML = "";
  meta.yields.forEach((y) => {
    state.weights[y] = state.weights[y] ?? 1.0;
    const lab = document.createElement("label"); lab.textContent = y;
    const inp = document.createElement("input"); inp.type = "number"; inp.step = "0.1"; inp.value = state.weights[y];
    inp.oninput = () => { state.weights[y] = parseFloat(inp.value) || 0; };
    root.appendChild(lab); root.appendChild(inp);
  });
}

// ===========================================================================
// (De)serialization + actions
// ===========================================================================
function serialize() {
  const tiles = [];
  for (const [k, t] of state.map) { const { q, r } = parseKey(k); tiles.push({ q, r, ...t }); }
  const cities = cityCenters().map((c, i) => ({
    name: centerName(c, i), q: c.q, r: c.r, work_radius: 3, requested: [...state.requested],
    population: state.cityPop.get(key(c.q, c.r)) || 0,
  }));
  return {
    ruleset: "gathering_storm_nfp", tiles, cities, city_name: "Capital",
    rival_cities: state.rivalCities, settlers: state.settlers, taken: [...state.takenWonders],
    loadout: { civ: state.civ, leader: state.leader, victory: effectiveVictory(), pantheon: state.pantheon, secret_society: state.secretSociety, beliefs: [...state.beliefs], active_modifiers: [...state.modifiers], weights: state.weights, oc_weight: state.ocWeight, region_weight: state.regionWeight },
  };
}
function loadMapData(data, recenter = true) {
  const cityList = data.cities || [];
  // Real Civ 6 exports are huge (~7000 tiles). Keep only tiles near a city OR your
  // Settler, so the editor stays fast and auto-fit frames your area (not the whole
  // world) — and capital suggestions stay near where you can actually settle.
  const anchors = cityList.map((c) => ({ q: c.q, r: c.r }))
    .concat((data.settlers || []).map((s) => ({ q: s.q, r: s.r })))
    .concat((data.rival_cities || []).map((c) => ({ q: c.q, r: c.r })));  // show neighbours too
  const near = (q, r) => !anchors.length || anchors.some((a) => hexDistance({ q, r }, a) <= VIEW_CLIP);

  state.map.clear();
  state.cityNames.clear();
  state.cityPop.clear();
  // parser returns own cities capital-first -> preserve that as the capital ordering
  state.cityOrder = cityList.map((c) => key(c.q, c.r));
  for (const c of cityList) {
    if (c.name) state.cityNames.set(key(c.q, c.r), c.name);
    if (c.population) state.cityPop.set(key(c.q, c.r), c.population);
  }
  state.rivalCities = data.rival_cities || [];
  state.settlers = data.settlers || [];
  state.gameModes = data.game_modes || [];

  for (const td of data.tiles || []) {
    if (!near(td.q, td.r)) continue;
    const t = defaultTile();
    for (const f of ["terrain", "feature", "hills", "on_river", "river_edges", "resource", "resource_class", "resource_revealed", "improvement", "appeal", "wonder", "natural_wonder", "district", "owner_city", "volcano", "owner_kind"])
      if (td[f] !== undefined) t[f] = td[f];
    state.map.set(key(td.q, td.r), t);
  }
  if (!state.map.size) freshBoard();  // nothing usable -> blank manual board

  if (cityList[0] && cityList[0].requested) {
    state.requested = new Set(cityList[0].requested);
    buildDistrictPicker(state.meta);
  }
  state.result = null; state.suggestions = null; state.wonderRecs = null; state.planSites = null;
  if (data.meta && data.meta.civ) applyImportLoadout(data);   // auto-pick civ/leader + focus
  applyReligionLoadout(data.loadout);                         // auto-fill pantheon + beliefs
  // open the view on the capital (first own city), else the Settler, else frame everything.
  // Skipped on silent auto-refresh so polling never yanks the camera while you pan around.
  if (recenter) {
    const focus = cityList[0] || (state.settlers && state.settlers[0]);
    if (focus) focusView({ q: focus.q, r: focus.r }); else fitView();
  }
  draw();
}

// Single unified action: plans up to «+городов» new city sites AND lays out districts
// across all cities in one pass. With +городов = 0 it is a pure district optimization of
// the current cities (the old "Оптимизировать"); with > 0 it also recommends new cities
// (the old "План империи"). One button, one mental model.
async function optimize() {
  const haveCity = cityCenters().length > 0;
  const haveSettler = (state.settlers || []).length > 0;
  if (!haveCity && !haveSettler) {
    alert(tr("Нужен хотя бы один город (⭐) или Поселенец. Поставь центр города или импортируй партию."));
    return;
  }
  if (!state.requested.size) { alert(tr("Отметь хотя бы один район для расчёта.")); return; }
  const maxNew = Math.max(0, Math.min(parseInt(document.getElementById("plan-count").value, 10) || 0, 25));
  if (!haveCity && maxNew === 0) {
    alert(tr("Городов ещё нет. Поставь «+городов» больше 0, чтобы спланировать города, или поставь центр города (⭐)."));
    return;
  }
  const btn = document.getElementById("btn-optimize");
  btn.disabled = true; btn.textContent = maxNew ? tr("Планирую…") : tr("Считаю…");
  try {
    const resp = await apiFetch("/api/plan-empire", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...serialize(), max_new: maxNew }),
    });
    if (!resp.ok) { const e = await resp.json().catch(() => ({})); throw new Error(e.detail || resp.statusText); }
    state.result = await resp.json(); state.suggestions = null;
    state.planSites = state.result.new_sites || [];
    // show the recommended World Wonders on the map (like districts)
    state.wonderRecs = (state.result.city_health && state.result.city_health.wonders) || null;
    state.lastRun = optimize;
    renderResult(); draw();
  } catch (err) { alert(tr("Ошибка оптимизации: ") + err.message); }
  finally { btn.disabled = false; btn.textContent = tr("▶ Оптимизировать"); }
}

function placeRow(p) {
  const yld = Object.entries(p.yields).map(([y, v]) => `${y} +${v}`).join(", ");
  const oc = p.opportunity ? tr(" · теряем с клетки −{0}", p.opportunity) : "";
  let phase = "";
  if (p.phase === "later") phase = tr(" <span class=\"phase later\" title=\"район запланирован на вырост\">⏳ с насел. {0}</span>", p.unlock_pop);
  else if (p.phase === "now") phase = tr(" <span class=\"phase now\" title=\"можно строить уже сейчас\">▶ сейчас</span>");
  return `<div class="place-row">`
    + `<span class="d"><span class="lg-badge sm" style="background:${DISTRICT_COLOR[p.district]}">${DISTRICT_ICON[p.district]}</span> ${nm(DISTRICT_NAME, p.district)}${phase}</span>`
    + `<span>(${p.q},${p.r})</span><span class="y">+${p.displayed}</span></div>`
    + `<div class="hint" style="margin:-2px 0 4px">${yld}${oc}</div>`;
}
const ROLE_ICON = {
  capital: "👑", production: "🏭", science: "🔬", culture: "🎭", faith: "⛪",
  gold: "💰", military: "⚔️", coastal: "⚓", general: "🏙️",
};
function roleChip(spec, city) {
  const cr = spec && spec.cities && spec.cities[city];
  if (!cr) return "";
  return ` <span class="role-chip" title="${cr.reason}">${ROLE_ICON[cr.role] || "🏙️"} ${cr.label}</span>`;
}
// Empire-wide district coverage + which city holds each one-per-empire unique.
function renderCoverage(spec) {
  if (!spec) return "";
  const cov = spec.coverage || {};
  const items = Object.entries(cov)
    .map(([d, n]) => `<span class="cov" title="${nm(DISTRICT_NAME, d)}">`
      + `<span class="lg-badge sm" style="background:${DISTRICT_COLOR[d]}">${DISTRICT_ICON[d]}</span>×${n}</span>`)
    .join(" ");
  let h = tr("<div class=\"summary\" style=\"margin-top:8px\">🧩 Покрытие империи</div>")
    + `<div class="cov-row">${items || '<span class="hint">—</span>'}</div>`;
  const u = spec.uniques || {};
  const uline = [];
  if (u.government_plaza) uline.push(tr("🏛️ Правит. площадь: <b>{0}</b>", u.government_plaza));
  if (u.diplomatic_quarter) uline.push(tr("🤝 Дипквартал: <b>{0}</b>", u.diplomatic_quarter));
  if (uline.length) h += `<div class="hint" style="margin-top:3px">${uline.join(" · ")}</div>`;
  return h;
}
function renderResult() {
  const r = state.result, root = document.getElementById("result");
  ensureCityColors();
  const badge = r.optimal ? tr('<span class="badge opt">оптимум доказан</span>') : tr('<span class="badge heur">эвристика</span>');
  let html = "";
  // joint planner: list the recommended NEW city sites first (⭐ on the map)
  if (r.new_sites && r.new_sites.length) {
    html += tr("<div class=\"summary\">🗺️ Рекомендованные НОВЫЕ города ({0}) — ⭐ на карте</div>", r.new_sites.length);
    const existingCount = (r.existing_cities || []).length;
    r.new_sites.forEach((s, i) => {
      const cnum = existingCount + i + 1;
      const col = CITY_PALETTE[(cnum - 1) % CITY_PALETTE.length];
      const dot = `<span style="display:inline-block;min-width:15px;height:15px;border-radius:50%;`
        + `vertical-align:middle;margin-right:5px;border:1px solid #000;background:${col};`
        + `color:#1a1205;font:bold 10px sans-serif;text-align:center;line-height:15px">${cnum}</span>`;
      html += tr("<div class=\"place-row\"><span class=\"d\">{0}⭐ новый #{1} ({2},{3})</span>", dot, cnum, s.q, s.r)
        + tr("<span class=\"y\">+{0} районы</span></div>", s.district_gain);
      if (s.note) html += `<div class="hint" style="margin:-2px 0 5px;color:#e6b86a">${s.note}</div>`;
    });
    html += tr("<div class=\"hint\" style=\"margin:2px 0 8px\">Места выбраны по приросту соседства районов (с учётом стыков с соседями) + качеству клетки. Основывай города на ⭐ и строй районы по плану ниже.</div>");
  }
  html += tr("<div class=\"summary\">{0} &nbsp; метод: {1}<br>суммарный счёт: <b>{2}</b>", badge, r.method, r.total_score);
  if (r.total_opportunity) {
    const net = Math.round((r.total_score - r.total_opportunity) * 100) / 100;
    html += tr(" · потеря клеток −{0} · чистыми <b>{1}</b>", r.total_opportunity, net);
  }
  if (r.total_regional) html += tr(" · региональное перекрытие +{0}", r.total_regional);
  if (r.total_buildings) {
    const full = Math.round((r.total_score + r.total_buildings) * 100) / 100;
    html += tr("<br>со зданиями района ≈ <b>{0}</b> (соседство {1} + здания {2})", full, r.total_score, r.total_buildings);
  }
  if (r.multi) html += tr(" · городов: {0}", r.cities.length);
  html += `</div>`;

  html += renderCoverage(r.specialization);

  const planLine = (name) => {
    const bp = r.build_plan && r.build_plan[name];
    if (!bp) return "";
    if (!bp.pop_known)
      return tr("<div class=\"hint\">Лимит районов: население неизвестно — порядок постройки ориентировочный.</div>");
    if (!bp.queued)
      return tr("<div class=\"hint\">Лимит районов: можно строить все {0} (насел. {1}).</div>", bp.build_now, bp.population);
    return tr("<div class=\"hint\">Лимит районов: <b>сейчас {0}</b>, в очереди {1} «на вырост» (насел. {2}). ⏳ = ждёт нужного населения.</div>", bp.build_now, bp.queued, bp.population);
  };

  if (r.multi) {
    const groups = {};
    for (const p of r.placements) (groups[p.city] = groups[p.city] || []).push(p);
    for (const city of r.cities) {
      const ps = groups[city] || [];
      const sub = Math.round(ps.reduce((a, p) => a + p.score, 0) * 100) / 100;
      const terr = (r.territory && r.territory[city] != null) ? tr(" · клеток {0}", r.territory[city]) : "";
      const col = (state._cityColors && state._cityColors[city]) || "#f0c84e";
      const num = (state._cityNums && state._cityNums[city]) || "";
      const dot = `<span style="display:inline-block;min-width:15px;height:15px;border-radius:50%;`
        + `vertical-align:middle;margin-right:5px;border:1px solid #000;background:${col};`
        + `color:#1a1205;font:bold 10px sans-serif;text-align:center;line-height:15px">${num}</span>`;
      html += tr("<div class=\"city-head\">{0}🏛️ {1}{2} <span>счёт {3}{4}</span></div>", dot, city, roleChip(r.specialization, city), sub, terr);
      html += planLine(city);
      if (!ps.length) html += tr("<div class=\"hint\">нет размещений</div>");
      for (const p of ps) html += placeRow(p);
    }
  } else {
    html += planLine(r.city);
    for (const p of r.placements) html += placeRow(p);
  }

  const tot = Object.entries(r.total_yields).map(([y, v]) => `${y}:${v}`).join("  ");
  html += tr("<div class=\"totals\">Итоги выходов: {0}</div>", tot);
  if (r.unplaceable && r.unplaceable.length)
    html += tr("<div class=\"totals\" style=\"color:#e88\">Некуда поставить: {0}</div>", r.unplaceable.map((d) => nm(DISTRICT_NAME, d)).join(", "));
  if (r.auto_infra && r.auto_infra.length) {
    const names = r.auto_infra.map((d) => nm(DISTRICT_NAME, d)).join(", ");
    html += tr("<div class=\"hint\" style=\"color:#46d3c0\">⚙️ В расчёт добавлена инфраструктура для синергии: {0} (напр., Акведук/Дамба/Канал дают +2 произв. соседней Промзоне) — она размещена в общем оптимуме.</div>", names);
  }
  html += renderCityHealth(r.city_health);
  html += renderNeighbors(r.neighbors);
  root.innerHTML = html;
  renderSetupAdvice(r.city_health);   // mirror Pantheon/Policy advice under the left selectors
}

// Nearby rivals (with their meta victory) + city-states (type/suzerain) and what to do.
function renderNeighbors(nb) {
  if (!nb || (!(nb.rivals || []).length && !(nb.city_states || []).length)) return "";
  let html = tr("<div class=\"summary\" style=\"margin-top:8px\">🌐 Соседи и угрозы</div>");
  for (const a of nb.advice || [])
    html += `<div class="hint" style="color:#e6b86a">• ${a}</div>`;
  if ((nb.rivals || []).length) {
    html += tr("<div class=\"hint\" style=\"margin-top:3px\"><b>Соперники рядом:</b></div>");
    for (const rv of nb.rivals.slice(0, 6)) {
      const vic = rv.victory_label ? `→ ${rv.victory_label}` : tr("цива неизвестна (импорт с модом)");
      html += tr("<div class=\"place-row\"><span class=\"d\">⚔️ {0} ({1} кл.)</span><span class=\"y\">{2}</span></div>", rv.civ_label || rv.name, rv.distance, vic);
    }
  }
  if ((nb.city_states || []).length) {
    html += tr("<div class=\"hint\" style=\"margin-top:3px\"><b>Города-государства рядом:</b></div>");
    for (const s of nb.city_states.slice(0, 8)) {
      const t = s.type_label ? `${s.type_label} · ${s.suzerain}` : tr("тип неизвестен (импорт с модом)");
      html += tr("<div class=\"place-row\"><span class=\"d\">🏛️ {0} ({1} кл.)</span><span class=\"y\">{2}</span></div>", s.name, s.distance, t);
    }
  }
  return html;
}

// Integrated city plan: Housing + Amenities balance and which EXTRA districts to add,
// plus top Wonders — so the optimization result is one holistic plan.
function renderCityHealth(ch) {
  if (!ch || !ch.cities || !ch.cities.length) return "";
  let html = tr("<div class=\"summary\" style=\"margin-top:8px\">🧭 План города: рост, довольство, что ещё построить</div>");
  for (const c of ch.cities) {
    html += `<div class="city-head">🏙️ ${c.city}</div>`;
    if (c.housing) {
      const col = HOUSE_COLOR[c.housing.state] || "#cdd6e0";
      const bal = (c.housing.surplus >= 0 ? "+" : "") + c.housing.surplus;
      html += tr("<div class=\"hint\">🏠 жильё {0}, запас {1} · <span style=\"color:{2}\">{3}</span> · лучший Квартал +{4} ({5})</div>", c.housing.supply, bal, col, c.housing.state_label, c.housing.best_neighborhood, c.housing.best_neighborhood_band);
    }
    if (c.amenities) {
      const col = AMEN_COLOR[c.amenities.state] || "#cdd6e0";
      const bal = (c.amenities.surplus >= 0 ? "+" : "") + c.amenities.surplus;
      html += tr("<div class=\"hint\">😊 довольство: нужно {0}, есть {1}, баланс {2} · <span style=\"color:{3}\">{4}</span></div>", c.amenities.required, c.amenities.supply, bal, col, c.amenities.state_label);
    }
    for (const rec of (c.recommend || [])) {
      const where = (rec.q != null) ? tr(" на ({0},{1})", rec.q, rec.r) : "";
      html += tr("<div class=\"hint\" style=\"color:#e6b86a\">➕ построй {0}{1} — {2}</div>", nm(DISTRICT_NAME, rec.district), where, rec.why);
    }
    if (c.governor_rec)
      html += tr("<div class=\"hint\" style=\"color:#ffd24a\">👑 Губернатор: <b>{0}</b> — {1}</div>", c.governor_rec.label, c.governor_rec.reason);
  }
  if (ch.trade) html += `<div class="hint">🚛 ${ch.trade}</div>`;
  // Pantheon / policy recommendations now live under their selectors on the left
  // (renderSetupAdvice); leave a short pointer here so it's discoverable.
  const sa = ch.setup_advice;
  if (sa && sa.pantheon)
    html += tr("<div class=\"hint\" style=\"color:#9fe0b0;margin-top:6px\">🛐 Рекомендации по пантеону/верованиям/политикам — в секциях «Религия» и «Политики» выше (раскрываются автоматически).</div>");
  if (ch.secret_society)
    html += tr("<div class=\"hint\" style=\"color:#c89bff;margin-top:4px\">🕯️ Тайное общество: <b>{0}</b> — {1}</div>", ch.secret_society.label, ch.secret_society.note);
  else if ((state.gameModes || []).includes("secret_societies"))
    html += tr("<div class=\"hint\" style=\"color:#c89bff\">⚡ В партии включены Тайные общества (обнаружены лей-линии) — выбери своё общество в панели слева.</div>");
  if (ch.wonders && ch.wonders.length) {
    html += tr("<div class=\"hint\" style=\"margin-top:4px\">🏛️ чудеса на карте (★ценность, цвет = риск ИИ; ставь Театр рядом — +2 культуры):</div>");
    for (const x of ch.wonders) {
      const col = RISK_COLOR[x.risk] || "#f0b429";
      html += tr("<div class=\"hint\">🏛️ <b>{0}</b> ★{1} на ({2},{3}) — {4}", x.name, x.value, x.q, x.r, x.requires)
        + tr(" · риск ИИ: <span style=\"color:{0}\">{1}</span>", col, x.risk)
        + tr(" · <a href=\"#\" onclick=\"markWonderTaken('{0}');return false\">занято ИИ ✖</a></div>", x.key);
    }
    if (state.takenWonders.size)
      html += tr("<div class=\"hint\">Исключены (заняты ИИ): {0} · <a href=\"#\" onclick=\"resetTakenWonders();return false\">сбросить</a></div>", [...state.takenWonders].join(", "));
  }
  return html;
}
// Mark a wonder as taken by the AI -> exclude it and re-plan (the optimizer suggests the next-best).
function markWonderTaken(k) { state.takenWonders.add(k); optimize(); }
function resetTakenWonders() { state.takenWonders.clear(); optimize(); }

// Situational Pantheon / Policy recommendations, shown under their selectors (left panel).
// `ch` is the optimize result's city_health (or null to show the "press Optimize" hint).
// open the collapsible section that contains an element (so fresh advice isn't hidden)
function openSectionOf(id) {
  const el = document.getElementById(id);
  const d = el && el.closest("details.sect");
  if (d) d.open = true;
}
function renderSetupAdvice(ch) {
  const pa = document.getElementById("pantheon-advice");
  const pl = document.getElementById("policy-advice");
  const bl = document.getElementById("belief-advice");
  const sa = ch && ch.setup_advice;
  if (!sa) {
    const hint = tr("<span class=\"a-alt\">Нажми «▶ Оптимизировать» — подберём под твою карту.</span>");
    if (pa) pa.innerHTML = hint;
    if (pl) pl.innerHTML = hint;
    if (bl) bl.innerHTML = hint;
    return;
  }
  if (bl) {
    let s = "";
    if (sa.beliefs && sa.beliefs.length)
      s += tr("<span class=\"a-h\">👉 Под твою карту:</span><br>")
        + sa.beliefs.map((b) => `${b.label} — <span class="a-alt">${b.why}</span>`).join("<br>");
    else s += tr("<span class=\"a-alt\">добавь Святое место/Кампус — подскажем верования под карту</span>");
    const bm = sa.belief_meta;
    if (bm && bm.picks && bm.picks.length) {
      s += tr("<br><span class=\"a-h\">🏆 Мета сообщества:</span><br>")
        + bm.picks.map((b) => `${b.label} — <span class="a-alt">${b.why}</span>`).join("<br>");
      if (bm.note) s += `<br><span class="a-alt">${bm.note}</span>`;
    }
    bl.innerHTML = s;
  }
  if (pa) {
    const p = sa.pantheon;
    if (p && (p.label || (p.meta && p.meta.length))) {
      let s = "";
      if (p.label) {
        s += tr("<span class=\"a-h\">👉 По карте: {0}</span><br>{1}", p.label, p.reason);
        for (const a of (p.alternatives || []))
          s += tr("<br><span class=\"a-alt\">· или {0} — {1}</span>", a.label, a.reason);
      }
      // community-meta openers (free Settler/Builder, fast districts) when none picked
      for (const m of (p.meta || []))
        s += tr("{0}<span class=\"a-h\">🚀 Мета: {1}</span> — <span class=\"a-alt\">{2}</span>", s ? "<br>" : "", m.label, m.reason);
      pa.innerHTML = s;
    } else pa.innerHTML = tr("<span class=\"a-alt\">подходящего пантеона по карте не нашлось</span>");
  }
  if (pl) {
    if (sa.policies && sa.policies.length)
      pl.innerHTML = tr("<span class=\"a-h\">👉 Под твои районы:</span><br>")
        + sa.policies.map((p) => p.why).join("<br>");
    else pl.innerHTML = tr("<span class=\"a-alt\">специализированных районов для карт ещё нет</span>");
  }
  // surface fresh recommendations even if the user kept these sections collapsed
  if (sa.pantheon || (sa.beliefs && sa.beliefs.length)) openSectionOf("pantheon-advice");
  if (sa.policies && sa.policies.length) openSectionOf("policy-advice");
}

async function suggestFirstCity() {
  if (!state.settlers || !state.settlers.length) {
    alert(tr("Поселенец не найден. Импортируй партию «🔄 Из игры (live)» с поселенцем (новый город ещё не основан) — если его нет, перезагрузи сохранение, чтобы мод обновился."));
    return;
  }
  const btn = document.getElementById("btn-first-city");
  btn.disabled = true; btn.textContent = tr("Считаю…");
  try {
    const resp = await apiFetch("/api/first-city", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...serialize(), settler: state.settlers[0], turn_penalty: state.turnPenalty, count: 6 }),
    });
    if (!resp.ok) { const e = await resp.json().catch(() => ({})); throw new Error(e.detail || resp.statusText); }
    const data = await resp.json();
    state.suggestions = data.suggestions; state.result = null; state.wonderRecs = null;
    state.lastRun = suggestFirstCity;
    renderFirstCity(data.suggestions); draw();
  } catch (err) { alert(tr("Ошибка: ") + err.message); }
  finally { btn.disabled = false; btn.textContent = tr("🚩 Столица"); }
}
function renderFirstCity(s) {
  const root = document.getElementById("result");
  if (!s || !s.length) { root.innerHTML = tr('<p class="hint">Нет подходящих клеток в досягаемости Поселенца (1–3 хода).</p>'); return; }
  let html = tr("<div class=\"summary\">🚩 Где основать СТОЛИЦУ (штраф за ход {0})</div>", state.turnPenalty);
  s.forEach((x, i) => {
    const fw = x.fresh_water ? tr("пресная вода") : tr("нет пресн. воды");
    const cs = x.coastal ? tr(", побережье") : "";
    const turn = x.turn ? tr("ход {0}", x.turn) : "";
    const best = i === 0 ? tr(' <span class="phase now">лучшее</span>') : "";
    html += `<div class="place-row"><span class="d">#${i + 1} (${x.q},${x.r}) · ${turn}${best}</span><span class="y">${x.score}</span></div>`
      + tr("<div class=\"hint\" style=\"margin:-2px 0 4px\">{0}{1} · тайлы {2}, районы {3}</div>", fw, cs, x.breakdown.tiles, x.breakdown.districts);
    if (x.note) html += `<div class="hint" style="margin:-2px 0 6px;color:#e6b86a">${x.note}</div>`;
  });
  html += tr("<div class=\"hint\" style=\"margin-top:6px\">🚩 — Поселенец. Зелёные ромбы — кандидаты под столицу (ход = когда сможешь основать). Двигай Поселенца на #1 и основывай.</div>");
  root.innerHTML = html;
}

async function suggestSettles() {
  const btn = document.getElementById("btn-settle");
  btn.disabled = true; btn.textContent = tr("Ищу…");
  try {
    const resp = await apiFetch("/api/suggest-cities", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...serialize(), count: 6 }),
    });
    if (!resp.ok) { const e = await resp.json().catch(() => ({})); throw new Error(e.detail || resp.statusText); }
    const data = await resp.json();
    state.suggestions = data.suggestions; state.result = null; state.wonderRecs = null; state.planSites = null;
    state.lastRun = suggestSettles;
    renderSuggestions(); draw();
  } catch (err) { alert(tr("Ошибка: ") + err.message); }
  finally { btn.disabled = false; btn.textContent = tr("🏙️ Места городов"); }
}
function renderSuggestions() {
  const root = document.getElementById("result");
  const s = state.suggestions || [];
  if (!s.length) { root.innerHTML = tr('<p class="hint">Подходящих мест не найдено (мало размеченной карты или всё занято/близко).</p>'); return; }
  let html = tr("<div class=\"summary\">🏙️ Рекомендованные места под города (топ {0})</div>", s.length);
  s.forEach((x, i) => {
    const fw = x.fresh_water ? tr("пресная вода") : tr("нет пресн. воды");
    const cs = x.coastal ? tr(", побережье") : "";
    const b = x.breakdown || {};
    const amen = b.amenities ? tr(", удобства {0}", b.amenities) : "";
    html += `<div class="place-row"><span class="d">#${i + 1} (${x.q},${x.r})</span><span class="y">${x.score}</span></div>`
      + tr("<div class=\"hint\" style=\"margin:-2px 0 4px\">{0}{1} · тайлы {2}, районы {3}{4}</div>", fw, cs, b.tiles, b.districts, amen);
    if (x.note) html += `<div class="hint" style="margin:-2px 0 6px;color:#e6b86a">${x.note}</div>`;
  });
  html += tr("<div class=\"hint\" style=\"margin-top:6px\">Зелёные клетки на карте — эти места. Поставь там центр города (⭐) и пересчитай.</div>");
  root.innerHTML = html;
}

// Joint planner: pick the best NEW city sites (for district combos) + full district plan.
const AMEN_COLOR = {
  ecstatic: "#46d39a", happy: "#7fd6ff", content: "#cdd6e0",
  displeased: "#e6b86a", unhappy: "#e08a8a", unrest: "#d0453a", revolt: "#d0453a",
};
async function checkAmenities() {
  if (!cityCenters().length) { alert(tr("Нет городов. Импортируй партию или поставь центр города (⭐).")); return; }
  const btn = document.getElementById("btn-amenities");
  btn.disabled = true; btn.textContent = tr("Считаю…");
  try {
    const resp = await apiFetch("/api/amenities", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(serialize()),
    });
    if (!resp.ok) { const e = await resp.json().catch(() => ({})); throw new Error(e.detail || resp.statusText); }
    const data = await resp.json();
    state.result = null; state.suggestions = null; state.wonderRecs = null; state.planSites = null;
    renderAmenities(data.cities); draw();
  } catch (err) { alert(tr("Ошибка: ") + err.message); }
  finally { btn.disabled = false; btn.textContent = tr("😊 Довольство"); }
}
function renderAmenities(rows) {
  const root = document.getElementById("result");
  let html = tr("<div class=\"summary\">😊 Довольство по городам</div>");
  if (!rows || !rows.length) { root.innerHTML = html + tr('<p class="hint">нет городов</p>'); return; }
  for (const r of rows) {
    const col = AMEN_COLOR[r.state] || "#cdd6e0";
    const pop = r.population ? tr("нас. {0}", r.population) : tr("нас. ?");
    const bal = (r.surplus >= 0 ? "+" : "") + r.surplus;
    html += `<div class="city-head">🏙️ ${r.city} <span style="color:${col}">${r.state_label}</span></div>`
      + tr("<div class=\"hint\">{0} · нужно {1}, есть {2}, баланс {3}</div>", pop, r.required, r.supply, bal);
    for (const a of (r.advice || [])) html += `<div class="hint" style="color:#e6b86a">• ${a}</div>`;
  }
  html += tr("<div class=\"hint\" style=\"margin-top:6px\">Оценка: роскошь покрывает 4 самых населённых города; Парк развлечений/Аквапарк дают довольство. Чудеса/политики/религию учитывай вручную.</div>");
  root.innerHTML = html;
}

const HOUSE_COLOR = {
  growing: "#46d39a", slowing: "#e6b86a", capped: "#e08a8a", shrinking: "#d0453a",
};
async function checkHousing() {
  if (!cityCenters().length) { alert(tr("Нет городов. Импортируй партию или поставь центр города (⭐).")); return; }
  const btn = document.getElementById("btn-housing");
  btn.disabled = true; btn.textContent = tr("Считаю…");
  try {
    const resp = await apiFetch("/api/housing", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(serialize()),
    });
    if (!resp.ok) { const e = await resp.json().catch(() => ({})); throw new Error(e.detail || resp.statusText); }
    const data = await resp.json();
    state.result = null; state.suggestions = null; state.wonderRecs = null; state.planSites = null;
    renderHousing(data.cities); draw();
  } catch (err) { alert(tr("Ошибка: ") + err.message); }
  finally { btn.disabled = false; btn.textContent = tr("🏠 Жильё"); }
}
function renderHousing(rows) {
  const root = document.getElementById("result");
  let html = tr("<div class=\"summary\">🏠 Жильё и рост по городам</div>");
  if (!rows || !rows.length) { root.innerHTML = html + tr('<p class="hint">нет городов</p>'); return; }
  for (const r of rows) {
    const col = HOUSE_COLOR[r.state] || "#cdd6e0";
    const pop = r.population ? tr("нас. {0}", r.population) : tr("нас. ?");
    const bal = (r.surplus >= 0 ? "+" : "") + r.surplus;
    html += `<div class="city-head">🏙️ ${r.city} <span style="color:${col}">${r.state_label}</span></div>`
      + tr("<div class=\"hint\">{0} · жильё {1}, запас {2} · лучший Квартал +{3} ({4})</div>", pop, r.supply, bal, r.best_neighborhood, r.best_neighborhood_band);
    for (const a of (r.advice || [])) html += `<div class="hint" style="color:#e6b86a">• ${a}</div>`;
  }
  html += tr("<div class=\"hint\" style=\"margin-top:6px\">Запас &lt;5 → рост замедляется; 0 → почти остановлен. Жильё: пресная вода/Акведук, фермы/плантации, Канализация, Кварталы (по привлекательности). Здания (Амбар/Канализация) не видны — оценка снизу.</div>");
  root.innerHTML = html;
}

async function suggestWonders() {
  if (!cityCenters().length) { alert(tr("Поставь центр города — чудеса ищутся в твоих границах.")); return; }
  const btn = document.getElementById("btn-wonders");
  btn.disabled = true; btn.textContent = tr("Ищу…");
  try {
    const resp = await apiFetch("/api/suggest-wonders", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...serialize(), taken: [...state.takenWonders], top: 12 }),
    });
    if (!resp.ok) { const e = await resp.json().catch(() => ({})); throw new Error(e.detail || resp.statusText); }
    const data = await resp.json();
    state.wonderRecs = data.recommendations;
    state.takenWonders = new Set(data.taken);
    state.result = null; state.suggestions = null;
    renderWonders(); draw();
  } catch (err) { alert(tr("Ошибка: ") + err.message); }
  finally { btn.disabled = false; btn.textContent = tr("🏛️ Чудеса света"); }
}
function renderWonders() {
  const root = document.getElementById("result");
  const recs = state.wonderRecs || [];
  let html = tr("<div class=\"summary\">🏛️ Рекомендованные чудеса света (топ {0})</div>", recs.length);
  if (state.takenWonders.size)
    html += tr("<div class=\"hint\">Исключены (заняты/построены): {0} · <a href=\"#\" id=\"reset-taken\">сбросить</a></div>", [...state.takenWonders].join(", "));
  if (!recs.length)
    html += tr('<p class="hint">Нет доступных чудес на размеченной территории. Нужны подходящие клетки в твоих границах (пустыня, горы, у реки, рядом с районами и т.д.).</p>');
  recs.forEach((w, i) => {
    const alts = w.alternatives.length
      ? tr(" · запасные: {0}", w.alternatives.map((a) => `(${a.q},${a.r})`).join(" ")) : "";
    html += `<div class="wonder-row">`
      + `<div class="wr-head"><b>#${i + 1} ${w.name}</b><span class="wr-val">★${w.value}</span></div>`
      + tr("<div class=\"hint\">место ({0},{1}) · {2} · риск ИИ: <b>{3}</b></div>", w.q, w.r, w.requires, w.risk)
      + `<div class="hint">${w.note}</div>`
      + tr("<div class=\"wr-actions\"><a href=\"#\" class=\"mark-taken\" data-key=\"{0}\">занято ИИ ✖</a>{1}</div>", w.key, alts)
      + `</div>`;
  });
  root.innerHTML = html;
  root.querySelectorAll(".mark-taken").forEach((a) =>
    (a.onclick = (e) => { e.preventDefault(); state.takenWonders.add(a.dataset.key); suggestWonders(); }));
  const rt = document.getElementById("reset-taken");
  if (rt) rt.onclick = (e) => { e.preventDefault(); state.takenWonders.clear(); suggestWonders(); };
}

// ===========================================================================
// Wire up
// ===========================================================================
document.getElementById("btn-optimize").onclick = optimize;
document.getElementById("btn-first-city").onclick = suggestFirstCity;
document.getElementById("btn-settle").onclick = suggestSettles;

// "Данные" dropdown: close after picking an action, and on any outside click
document.querySelectorAll("details.menu .menu-list button").forEach((b) =>
  b.addEventListener("click", () => { const d = b.closest("details.menu"); if (d) d.open = false; }));
document.addEventListener("click", (e) => {
  document.querySelectorAll("details.menu[open]").forEach((d) => { if (!d.contains(e.target)) d.open = false; });
});
// Housing / Amenities / Wonders are no longer standalone buttons — they're folded into
// the "Optimize" result (renderCityHealth) so the plan is holistic. The fetch helpers
// (checkHousing/checkAmenities/suggestWonders) remain for reference but are unbound.
document.getElementById("btn-clear").onclick = () => {
  freshBoard(); state.cityNames.clear();
  state.result = null; state.suggestions = null; state.wonderRecs = null; state.planSites = null;
  document.getElementById("result").innerHTML = ""; fitView(); draw();
};
document.getElementById("btn-save").onclick = () => {
  const blob = new Blob([JSON.stringify(serialize(), null, 2)], { type: "application/json" });
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "civ6_map.json"; a.click();
};
document.getElementById("btn-load").onclick = () => document.getElementById("file-input").click();
document.getElementById("file-input").onchange = (e) => {
  const f = e.target.files[0]; if (!f) return;
  const reader = new FileReader();
  reader.onload = () => { try { loadMapData(JSON.parse(reader.result)); } catch (err) { alert(tr("Плохой JSON: ") + err.message); } };
  reader.readAsText(f); e.target.value = "";
};
document.getElementById("btn-sample").onclick = async () => {
  const resp = await apiFetch("/api/sample");
  if (!resp.ok) { alert(tr("Пример не найден. Запусти scripts/build_sample.py")); return; }
  loadMapData(await resp.json());
};
document.getElementById("btn-import").onclick = () => document.getElementById("lua-input").click();
document.getElementById("lua-input").onchange = (e) => {
  const f = e.target.files[0]; if (!f) return;
  const reader = new FileReader();
  reader.onload = async () => {
    try {
      const resp = await apiFetch("/api/import-lualog", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: reader.result }),
      });
      if (!resp.ok) { const er = await resp.json().catch(() => ({})); throw new Error(er.detail || resp.statusText); }
      const data = await resp.json();
      loadMapData(data);
      const w = (data.warnings && data.warnings.length) ? tr("\nПредупреждения: {0}", data.warnings.join("; ")) : "";
      alert(tr("Импортировано клеток: {0}.{1}", data.tiles.length, w));
    } catch (err) { alert(tr("Ошибка импорта: ") + err.message); }
  };
  reader.readAsText(f); e.target.value = "";
};

// --- live (dynamic) re-import from the running game --------------------------
function _snapOf(data) {
  const wonders = new Set(); let foreign = 0; const districts = new Set();
  for (const t of data.tiles || []) {
    if (t.wonder) wonders.add(t.wonder);
    if (t.owner_city && /^rival/.test(t.owner_city)) foreign++;
    if (t.district && t.district !== "city_center") districts.add(`${t.district}@${t.q},${t.r}`);
  }
  return { wonders, foreign, districts };
}
function _diffSnap(prev, cur) {
  if (!prev) return [];
  const msgs = [];
  const newW = [...cur.wonders].filter((w) => !prev.wonders.has(w));
  if (newW.length) msgs.push(tr("новые чудеса на карте (возможно, забрал ИИ): {0}", newW.join(", ")));
  const df = cur.foreign - prev.foreign;
  if (df > 0) msgs.push(tr("занятых/чужих клеток стало больше: +{0}", df));
  const newD = [...cur.districts].filter((d) => !prev.districts.has(d)).length;
  if (newD) msgs.push(tr("новых районов на карте: {0}", newD));
  return msgs;
}
function renderChanges(changes) {
  const root = document.getElementById("result");
  root.innerHTML = tr("<div class=\"summary\">🔄 Изменения с прошлого обновления</div>")
    + (changes.length ? changes.map((c) => `<div class="hint">• ${c}</div>`).join("")
                      : tr('<div class="hint">существенных изменений нет</div>'))
    + tr("<div class=\"hint\" style=\"margin-top:6px\">Нажми «Оптимизировать» или «Чудеса света» для пересчёта по новой карте.</div>");
}
async function liveImport(silent) {
  const btn = document.getElementById("btn-live");
  try {
    const resp = await apiFetch("/api/import-latest");
    if (!resp.ok) {
      if (!silent) { const e = await resp.json().catch(() => ({})); alert(tr("Live-импорт: ") + (e.detail || resp.statusText)); }
      return;
    }
    const data = await resp.json();
    if (state.liveMtime && data.mtime && data.mtime === state.liveMtime) {
      if (!silent) { btn.textContent = tr("🔄 без изменений"); setTimeout(() => (btn.textContent = tr("🔄 Из игры (live)")), 1200); }
      return;
    }
    const cur = _snapOf(data);
    const changes = _diffSnap(state.liveSnap, cur);
    state.liveMtime = data.mtime; state.liveSnap = cur;
    loadMapData(data, !silent);   // manual click recenters on the capital; silent poll keeps the camera
    renderChanges(changes);
  } catch (err) { if (!silent) alert(tr("Ошибка live-импорта: ") + err.message); }
}
document.getElementById("btn-live").onclick = () => liveImport(false);
document.getElementById("chk-auto").onchange = (e) => {
  if (e.target.checked) { liveImport(false); state.autoTimer = setInterval(() => liveImport(true), 12000); }
  else { clearInterval(state.autoTimer); state.autoTimer = null; }
};

// zoom controls + responsive canvas
document.getElementById("btn-zoom-in").onclick = () => zoomAt(canvas.width / 2, canvas.height / 2, 1.2);
document.getElementById("btn-zoom-out").onclick = () => zoomAt(canvas.width / 2, canvas.height / 2, 1 / 1.2);
document.getElementById("btn-zoom-fit").onclick = () => { fitView(); draw(); };
let _resizeTimer = null;
window.addEventListener("resize", () => {
  clearTimeout(_resizeTimer);
  _resizeTimer = setTimeout(() => { resizeCanvas(); draw(); }, 120);
});

// Build every panel that depends on the API catalogue (names come back in the current language).
async function loadMeta() {
  state.meta = await (await apiFetch("/api/meta")).json();
  state.resourceCat = {}; state.nwByKey = {};
  for (const cat of ["bonus", "luxury", "strategic"])
    for (const name of (state.meta.resources[cat] || [])) state.resourceCat[name] = cat;
  for (const w of (state.meta.natural_wonders || [])) state.nwByKey[w.key] = w;
  buildPalette(state.meta);
  buildCivSelect(state.meta);
  buildLeaderSelect(state.meta);
  buildPantheonSelect(state.meta);
  buildSecretSelect(state.meta);
  buildBeliefSelects(state.meta);
  updateFocusLine();
  buildDistrictPicker(state.meta);
  buildModifierPicker(state.meta);
  buildWeights(state.meta);
}

// RU <-> EN without a reload: static text, catalogue panels and the last result are redone.
function showLangButtons() {
  document.querySelectorAll("#lang-switch button").forEach((b) => b.classList.toggle("on", b.dataset.lang === LANG));
}
async function setLang(lang) {
  if (lang === LANG) return;
  LANG = lang;
  try { localStorage.setItem(LANG_KEY, lang); } catch (e) { /* not persisted */ }
  localizeDom();
  showLangButtons();
  document.getElementById("coord-readout").textContent = "";
  // buttons whose text the code rewrites while working
  document.getElementById("btn-optimize").textContent = tr("▶ Оптимизировать");
  document.getElementById("btn-first-city").textContent = tr("🚩 Столица");
  document.getElementById("btn-settle").textContent = tr("🏙️ Места городов");
  document.getElementById("btn-live").textContent = tr("🔄 Из игры (live)");
  await loadMeta();
  if (state.lastRun && (state.result || state.suggestions)) state.lastRun();
  else {
    renderSetupAdvice(null);
    document.getElementById("result").innerHTML =
      '<p class="hint">' + tr("Поставь центр города, нарисуй карту (или импортируй из игры) и нажми «Оптимизировать».") + "</p>";
  }
  draw();
}
document.querySelectorAll("#lang-switch button").forEach((b) => (b.onclick = () => setLang(b.dataset.lang)));

async function init() {
  freshBoard();
  resizeCanvas();
  localizeDom();
  showLangButtons();
  await loadMeta();
  canvas.style.cursor = state.tool.type === "pan" ? "grab" : "crosshair";
  document.getElementById("btn-apply-focus").onclick = applyFocus;
  renderSetupAdvice(null);          // placeholder under the Pantheon/Policy selectors
  const ocInput = document.getElementById("oc-weight");
  const ocVal = document.getElementById("oc-val");
  ocInput.value = state.ocWeight; ocVal.textContent = state.ocWeight.toFixed(1);
  ocInput.oninput = () => { state.ocWeight = parseFloat(ocInput.value); ocVal.textContent = state.ocWeight.toFixed(1); };
  const regInput = document.getElementById("region-weight");
  const regVal = document.getElementById("region-val");
  regInput.value = state.regionWeight; regVal.textContent = state.regionWeight.toFixed(1);
  regInput.oninput = () => { state.regionWeight = parseFloat(regInput.value); regVal.textContent = state.regionWeight.toFixed(1); };
  const tpInput = document.getElementById("turn-penalty");
  const tpVal = document.getElementById("tp-val");
  tpInput.value = state.turnPenalty; tpVal.textContent = state.turnPenalty.toFixed(1);
  tpInput.oninput = () => { state.turnPenalty = parseFloat(tpInput.value); tpVal.textContent = state.turnPenalty.toFixed(1); };
  fitView();
  draw();
}
init();
