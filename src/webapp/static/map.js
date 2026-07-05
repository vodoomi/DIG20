/* 地図描画。/api/state から latest.json の内容を取得し、建物(問い合わせ住所)の位置に
 * 補償額を示す円を描く。過去の問い合わせ(history)も消さずに残す。
 *
 * 円の大きさ = 補償額、円の色 = 震度(7:紫 / 6弱・6強:赤 / 5弱・5強:オレンジ / 4以下・不明:黄)。
 */

const map = L.map("map").setView([37.1, 137.3], 9);

L.tileLayer("https://cyberjapandata.gsi.go.jp/xyz/pale/{z}/{x}/{y}.png", {
  attribution: "地図: 国土地理院(淡色地図)",
  maxZoom: 18,
}).addTo(map);

const SHINDO_COLOR_7 = "#9C27B0"; // 紫
const SHINDO_COLOR_6 = "#E53935"; // 赤
const SHINDO_COLOR_5 = "#FB8C00"; // オレンジ
const SHINDO_COLOR_OTHER = "#FDD835"; // 黄(震度4以下・不明)

function colorForShindo(shindoClass) {
  if (shindoClass === "7") return SHINDO_COLOR_7;
  if (typeof shindoClass === "string" && shindoClass.startsWith("6")) return SHINDO_COLOR_6;
  if (typeof shindoClass === "string" && shindoClass.startsWith("5")) return SHINDO_COLOR_5;
  return SHINDO_COLOR_OTHER;
}

function radiusForPayout(payoutYen) {
  return 10 + Math.sqrt(Math.max(0, payoutYen || 0)) / 150;
}

const markerLayer = L.layerGroup().addTo(map);

function collectEntries(data) {
  const entries = [];
  if (data.query) {
    entries.push({ query: data.query, intensity: data.intensity, payout: data.payout });
  }
  if (Array.isArray(data.history)) {
    entries.push(...data.history);
  }
  return entries;
}

function renderState(data) {
  markerLayer.clearLayers();

  const entries = collectEntries(data);
  let lastLatLng = null;

  for (const entry of entries) {
    const q = entry.query;
    if (!q || q.lat === undefined || q.lat === null) continue;
    if (!entry.payout) continue; // 補償額が未計算のエントリは描画しない

    const shindoClass = entry.intensity ? entry.intensity.shindo_class : null;
    const color = colorForShindo(shindoClass);
    const radius = radiusForPayout(entry.payout.payout_yen);
    const shindoLabel = shindoClass ? `震度${shindoClass}` : "震度不明";

    L.circleMarker([q.lat, q.lon], {
      radius: radius,
      color: color,
      fillColor: color,
      fillOpacity: 0.65,
      weight: 2,
    })
      .bindPopup(
        `<strong>${q.matched_address || q.address}</strong><br>` +
          `補償額 ${entry.payout.payout_yen_formatted}(${shindoLabel})`
      )
      .addTo(markerLayer);
    lastLatLng = [q.lat, q.lon];
  }

  if (lastLatLng) {
    map.panTo(lastLatLng);
  }
}

function renderLegend() {
  document.getElementById("legend").innerHTML = `
    <strong>凡例</strong>
    <div>円の大きさ: 補償額(大きいほど高額)</div>
    <div>円の色(震度): <span style="color:${SHINDO_COLOR_7}">■</span>7
      <span style="color:${SHINDO_COLOR_6}">■</span>6弱・6強
      <span style="color:${SHINDO_COLOR_5}">■</span>5弱・5強
      <span style="color:${SHINDO_COLOR_OTHER}">■</span>4以下・不明</div>
  `;
}

async function refreshMapState() {
  const res = await fetch("/api/state");
  const data = await res.json();
  renderState(data);
}

renderLegend();
refreshMapState();
