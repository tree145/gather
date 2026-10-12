"use strict";

const $ = (id) => document.getElementById(id);
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const state = {products: [], selected: new Set(), revision: 0, draftReady: false, busy: false, scenario: "everyday"};
const presets = {
  comfort: "預算 3500 元，需要放得下 16 吋筆電。週末旅行會走很多路，重視背負設計。",
  lightweight: "預算 3500 元，需要攜帶 16 吋筆電。每天搭車通勤，重量不要超過 900 g，希望輕量一點。",
  value: "預算 1800 元，日常輕裝出門，不需要帶筆電，便宜、省錢優先。",
  carryon: "出國隨身包，假設尺寸上限 30x30x40 cm，預算 3000 元。希望省錢、有水壺袋，願意比較使用上的取捨。",
};
const fields = {budget_ntd: "budget", max_weight_g: "weight", laptop_inches: "laptop", min_capacity_l: "capacity"};
const labels = {price_ntd: "售價", dimensions_cm: "標示外部尺寸", bottle_pocket: "水壺袋", weight_g: "重量", capacity_l: "容量", laptop_inches: "筆電隔層", padded_back: "加厚背板", hip_belt: "腰帶"};
const statusLabels = {eligible: "規格符合期望", conditional: "附條件可考慮", compromise: "有差距，需取捨", excluded: "未滿足不可妥協條件", pending: "資訊不足，暫供比較"};
const checkLabels = {pass: "符合", fail: "有差距", unknown: "未提供", conditional: "規格超出・心得提供條件式線索"};

async function api(path, body, method) {
  const response = await fetch(`/api/demo/${path}`, {
    method: method || (body ? "POST" : "GET"),
    headers: body ? {"Content-Type": "application/json"} : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await response.json();
  if (!response.ok) {
    const detail = typeof data.detail === "string" ? data.detail : "輸入格式不正確，請確認文字長度與數值範圍。";
    throw new Error(detail);
  }
  return data;
}

function showError(error, target = "error") {
  $(target).textContent = error.message || "無法連線，請確認本地服務仍在執行。";
  $(target).hidden = false;
}

function invalidate() {
  state.revision++;
  $("results").hidden = true;
  $("empty-result").hidden = false;
  $("persona").textContent = "條件或商品已更新；比較後顯示本次需求檔案。";
  $("error").hidden = true;
  updateControls();
}

function updateControls() {
  $("count").textContent = `${state.selected.size} 件已選`;
  $("compare").disabled = state.busy || !state.draftReady || !state.selected.size;
  $("parse").disabled = state.busy;
  $("compare").innerHTML = state.busy ? "處理中…" : '依我的需求比較 <span>↗</span>';
  $("compare-note").textContent = !state.draftReady ? "修改描述後，請先按「整理我的需求」。" : `已選 ${state.selected.size} 件商品，最多可同時比較 6 件`;
}

function spec(product, key) {
  const value = product.specs[key]?.value;
  if (value === null || value === undefined) return "未提供";
  if (typeof value === "boolean") return value ? "有" : "無";
  if (key === "dimensions_cm") return `${value.join(" × ")} cm`;
  if (key === "price_ntd") return `NT$${value.toLocaleString("en-US")}`;
  return `${value} ${{weight_g: "g", capacity_l: "L", laptop_inches: "吋"}[key] || ""}`;
}

function bag(color) {
  const [base, dark, light] = ({sage: ["#839581", "#5f7560", "#a1b09a"], clay: ["#b58468", "#91634d", "#cfa78a"], sand: ["#c1b787", "#968d61", "#d7cea7"], slate: ["#8298a0", "#5c7580", "#a4b7bd"]})[color] || ["#8298a0", "#5c7580", "#a4b7bd"];
  return `<svg viewBox="0 0 120 160" role="img" aria-label="背包示意插圖，非商品實拍"><path d="M37 50C18 54 17 115 32 141M83 50C102 54 103 115 88 141" fill="none" stroke="${dark}" stroke-width="9"/><path d="M46 28V20Q60 9 74 20V28" fill="none" stroke="${dark}" stroke-width="6"/><rect x="24" y="26" width="72" height="123" rx="24" fill="${base}"/><path d="M26 54Q60 39 94 54" fill="none" stroke="${dark}" stroke-width="2"/><path d="M33 55V88M87 55V88" stroke="${light}" stroke-width="2"/><rect x="33" y="87" width="54" height="46" rx="10" fill="${light}"/><path d="M36 99H84" stroke="${dark}" stroke-width="2"/><path d="M78 99v8" stroke="${dark}" stroke-width="3"/><rect x="50" y="64" width="20" height="10" rx="2" fill="${dark}"/><path d="M22 94H14V125Q14 133 26 131M98 94H106V125Q106 133 94 131" fill="${dark}"/></svg>`;
}

function visibleProducts() { return state.products.filter((p) => !p.scenario || p.scenario === state.scenario); }
function renderProducts() {
  $("products").innerHTML = visibleProducts().map((p, i) => `<article class="product-card ${state.selected.has(p.id) ? "selected" : ""}">
    <div class="product-visual ${esc(p.color)}"><label class="select-product"><input type="checkbox" data-select="${esc(p.id)}" aria-label="選取 ${esc(p.name)}" ${state.selected.has(p.id) ? "checked" : ""}>加入比較</label><span class="product-number">${String(i + 1).padStart(2, "0")}</span>${bag(p.color)}</div>
    <div class="product-body"><p class="product-brand">${esc(p.brand)}</p><h3 class="product-name">${esc(p.name)}</h3><p class="price">${esc(spec(p, "price_ntd"))}</p><div class="spec-chips">${(p.specs.dimensions_cm?.value ? ["dimensions_cm", "bottle_pocket"] : ["weight_g", "capacity_l", "laptop_inches"]).map((key) => `<span>${labels[key]} ${esc(spec(p, key))}</span>`).join("")}</div><div class="product-source"><span>${p.is_demo ? "虛構示範商品" : "使用者提供的資料"}</span>${p.is_demo ? "" : `<button data-delete="${esc(p.id)}" aria-label="刪除 ${esc(p.name)}">刪除</button>`}</div></div>
    <details class="product-details"><summary>查看原始規格</summary><pre>${esc(p.description)}</pre></details>${reviewEvidenceHtml(p)}</article>`).join("");
  updateControls();
}

async function parseNeeds() {
  if (state.busy) return;
  const text = $("needs").value.trim();
  if (text.length < 3) return showError(new Error("請至少輸入 3 個字，描述這次選購的需求。"));
  state.draftReady = false;
  invalidate();
  const revision = state.revision;
  state.busy = true;
  updateControls();
  try {
    const data = await api("requirements", {text});
    if (revision !== state.revision) return;
    for (const [key, id] of Object.entries(fields)) $(id).value = data.requirements[key] ?? "";
    $("priority").value = data.requirements.priority;
    $("dimensions").value = data.requirements.max_dimensions_cm?.join("x") || "";
    $("wants-bottle").checked = data.requirements.wants_bottle_pocket;
    state.draftReady = true;
    $("draft-note").textContent = "已依文字規則整理。請確認下方數值，也可以直接修改後再比較。";
  } catch (error) {
    if (revision === state.revision) showError(error);
  } finally {
    state.busy = false;
    updateControls();
  }
}

function checksHtml(row) {
  return row.checks.map((c) => `<span class="check ${c.status}">${c.hard ? "不可妥協 · " : "期望 · "}${esc(c.label)} ${esc(c.required)} · ${checkLabels[c.status]}（標示 ${esc(c.actual)}）</span>`).join("");
}

function reviewEvidenceHtml(product, applied = null) {
  if (!product.compression_evidence?.length) return "";
  return `<div class="review-evidence"><strong>${product.is_demo ? "虛構示範心得" : "使用者提供的心得・未獨立驗證"}</strong>${product.compression_evidence.map((e) => `<blockquote><b>${esc(e.source_label)}</b><p>「${esc(e.quote)}」</p><p>成立條件：${esc(e.conditions)}</p><small>心得描述的尺寸：${esc(e.compressed_dimensions_cm.join(" × "))} cm · ${e.stance === "conflicting" ? "反例／衝突" : "支持線索"}${applied?.source_label === e.source_label ? " · 本次已採用，仍有不確定性" : ""}</small></blockquote>`).join("")}</div>`;
}

function evidenceHtml(row) {
  return `<details><summary>查看規格依據</summary>${Object.entries(row.product.specs).map(([key, v]) => `<p>${labels[key]}：${esc(v.evidence || "來源未提供，無法確認")}</p>`).join("")}</details>`;
}

function renderResults(data) {
  $("persona").textContent = JSON.stringify(data.persona, null, 2);
  const winner = data.results.find((r) => r.product.id === data.winner_id);
  const eligible = data.results.filter((r) => r.status === "eligible").length;
  $("result-count").textContent = `${data.results.length} 件綜合比較 · ${eligible} 件規格符合期望`;
  $("winner").innerHTML = winner ? `<article class="winner-card"><div class="winner-top"><div><span class="winner-tag">依本次條件・優先考慮</span><h3>${esc(winner.product.name)}</h3></div><span class="winner-price">${esc(spec(winner.product, "price_ntd"))}</span></div><p>${esc(data.summary)}</p><ul class="reason-list">${winner.reasons.map((r) => `<li>${esc(r)}</li>`).join("")}</ul>${winner.cautions.length ? `<div class="cautions"><strong>選擇前也要知道</strong><br>${winner.cautions.map(esc).join("<br>")}</div>` : ""}${winner.product.review ? `<div class="review"><strong>使用心得呈現示範 · 虛構內容，非網路評價</strong>${esc(winner.product.review.text)}<small>${esc(winner.product.review.context)} 不參與推薦排序。</small></div>` : '<div class="review">尚未提供可驗證的使用心得；本次僅以商品規格比較。</div>'}<div class="checks">${checksHtml(winner)}</div>${evidenceHtml(winner)}</article>` : `<div class="no-match"><strong>這次先不勉強推薦</strong><br>${esc(data.summary)}<br>可以調整條件，或加入規格更完整的商品後重新比較。</div>`;
  $("matrix").innerHTML = `<table class="matrix"><caption class="sr-only">選取商品的規格與條件比較</caption><thead><tr><th scope="col">比較項目</th>${data.results.map((r) => `<th scope="col">${esc(r.product.name)}</th>`).join("")}</tr></thead><tbody><tr><td>條件檢查</td>${data.results.map((r) => `<td><span class="status-pill ${r.status}">${statusLabels[r.status]}</span></td>`).join("")}</tr>${Object.keys(labels).map((key) => `<tr><td>${labels[key]}</td>${data.results.map((r) => `<td>${esc(spec(r.product, key))}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
  if (winner) {
    $("winner").querySelector(".winner-tag").textContent = `相對首選 · ${statusLabels[winner.status]}`;
    $("winner").querySelector(".winner-card").insertAdjacentHTML("beforeend", reviewEvidenceHtml(winner.product, winner.applied_evidence));
    if (winner.product.compression_evidence?.length) $("winner").querySelector(".review")?.remove();
  }
  $("alternatives").innerHTML = data.results.filter((r) => r.product.id !== data.winner_id).map((r) => `<article class="alternative"><h3>${esc(r.product.name)} <span class="status-pill ${r.status}">${statusLabels[r.status]}</span></h3><p>${esc(r.reasons.join(" "))}</p>${r.cautions.length ? `<p>${esc(r.cautions.join(" "))}</p>` : ""}<div class="checks">${checksHtml(r)}</div>${evidenceHtml(r)}</article>`).join("");
  $("empty-result").hidden = true;
  $("results").hidden = false;
  $("results").scrollIntoView({behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth", block: "start"});
}

$("needs").addEventListener("input", () => {
  state.draftReady = false;
  $("draft-note").textContent = "描述已修改，請重新整理需求，再確認下方條件。";
  document.querySelectorAll(".preset").forEach((b) => b.classList.remove("active"));
  invalidate();
});
for (const id of [...Object.values(fields), "priority"]) $(id).addEventListener("input", invalidate);
for (const id of ["dimensions", "decision-mode", "accept-reviews", "wants-bottle"]) $(id).addEventListener("input", invalidate);
document.querySelectorAll("[data-hard]").forEach((input) => input.addEventListener("change", invalidate));
$("parse").addEventListener("click", parseNeeds);
document.querySelectorAll(".preset").forEach((button) => button.addEventListener("click", async () => {
  if (state.busy) return;
  document.querySelectorAll(".preset").forEach((b) => b.classList.toggle("active", b === button));
  state.scenario = button.dataset.preset === "carryon" ? "carryon" : "everyday";
  state.selected = new Set(visibleProducts().slice(0, 6).map((p) => p.id));
  $("accept-reviews").checked = false;
  renderProducts();
  $("needs").value = presets[button.dataset.preset];
  await parseNeeds();
}));

$("products").addEventListener("change", (event) => {
  const input = event.target.closest("[data-select]");
  if (!input) return;
  if (input.checked && state.selected.size >= 6) {
    input.checked = false;
    return showError(new Error("一次最多比較 6 件商品，請先取消其中一件。"));
  }
  if (input.checked) state.selected.add(input.dataset.select); else state.selected.delete(input.dataset.select);
  input.closest(".product-card").classList.toggle("selected", input.checked);
  invalidate();
});
$("products").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-delete]");
  if (!button) return;
  button.disabled = true;
  try {
    await api(`products/${encodeURIComponent(button.dataset.delete)}`, null, "DELETE");
    state.products = state.products.filter((p) => p.id !== button.dataset.delete);
    state.selected.delete(button.dataset.delete);
    invalidate();
    renderProducts();
  } catch (error) { showError(error); button.disabled = false; }
});

$("compare").addEventListener("click", async () => {
  for (const id of Object.values(fields)) if (!$(id).reportValidity()) return;
  const requirements = {text: $("needs").value.trim(), priority: $("priority").value};
  const dims = $("dimensions").value.trim();
  if (dims && !/^\d+(\.\d+)?\s*[xX×*]\s*\d+(\.\d+)?\s*[xX×*]\s*\d+(\.\d+)?\s*(cm|公分)?$/.test(dims)) return showError(new Error("尺寸請使用 30x30x40 格式，單位為 cm。"));
  requirements.max_dimensions_cm = dims ? dims.replace(/cm|公分/g, "").split(/[xX×*]/).map(Number) : null;
  requirements.decision_mode = $("decision-mode").value;
  requirements.hard_constraints = [...document.querySelectorAll("[data-hard]:checked")].map((el) => el.dataset.hard);
  requirements.accept_review_conditions = $("accept-reviews").checked;
  requirements.wants_bottle_pocket = $("wants-bottle").checked;
  for (const [key, id] of Object.entries(fields)) requirements[key] = $(id).value === "" ? null : Number($(id).value);
  const revision = state.revision;
  state.busy = true;
  $("error").hidden = true;
  updateControls();
  try {
    const data = await api("recommend", {product_ids: [...state.selected], requirements});
    if (revision === state.revision) renderResults(data);
  } catch (error) { if (revision === state.revision) showError(error); }
  finally { state.busy = false; updateControls(); }
});

$("open-import").addEventListener("click", () => {
  $("import-error").hidden = true;
  $("import-dialog").showModal();
});
$("close-import").addEventListener("click", () => $("import-dialog").close());
function fillProduct(data) {
  if (!data || typeof data.name !== "string" || typeof data.description !== "string") throw new Error("JSON 需包含文字欄位 name 與 description；brand 可省略。");
  $("product-name").value = data.name;
  $("product-brand").value = typeof data.brand === "string" ? data.brand : "自訂商品";
  $("description").value = data.description;
  $("compression-json").value = data.compression_evidence ? JSON.stringify(data.compression_evidence, null, 2) : "";
  $("import-error").hidden = true;
}
$("fill-sample").addEventListener("click", async () => {
  try { fillProduct(await (await fetch("/assets/sample-product.json")).json()); }
  catch (error) { showError(error, "import-error"); }
});
$("file").addEventListener("change", async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  try {
    if (file.size > 64 * 1024) throw new Error("示範版請使用 64 KB 以下的文字檔。");
    const ext = file.name.split(".").pop().toLowerCase();
    if (!["txt", "md", "html", "json"].includes(ext)) throw new Error("支援 .txt、.md、.html、.json 文字檔。");
    const text = (await file.text()).replace(/^\uFEFF/, "");
    if (ext === "json") fillProduct(JSON.parse(text));
    else fillProduct({name: file.name.replace(/\.[^.]+$/, ""), description: text});
  } catch (error) { showError(error instanceof SyntaxError ? new Error("JSON 格式有誤，請參考下載的範本。") : error, "import-error"); }
  event.target.value = "";
});
$("import-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("import-submit").disabled = true;
  $("import-error").hidden = true;
  try {
    let evidence;
    try { evidence = $("compression-json").value.trim() ? JSON.parse($("compression-json").value) : []; }
    catch { throw new Error("壓縮心得的 JSON 格式不正確。"); }
    const product = await api("products", {name: $("product-name").value.trim(), brand: $("product-brand").value.trim() || "自訂商品", description: $("description").value, compression_evidence: evidence});
    state.products.push(product);
    if (state.selected.size < 6) state.selected.add(product.id);
    invalidate();
    renderProducts();
    $("import-dialog").close();
    $("import-form").reset();
  } catch (error) { showError(error, "import-error"); }
  finally { $("import-submit").disabled = false; }
});

(async () => {
  try {
    const data = await api("products");
    state.products = data.products;
    state.selected = new Set(visibleProducts().slice(0, 6).map((p) => p.id));
    renderProducts();
    $("connection").textContent = "本地服務已連線";
    $("needs").value = presets.comfort;
    await parseNeeds();
  } catch (error) {
    $("connection").textContent = "服務未連線";
    showError(error);
  }
})();
