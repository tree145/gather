"""Offline rules, grounded in submitted text; no model, AWS, or web calls."""

import re
import unicodedata
from typing import Any

from .profile import PersonaProfile

from .models import Requirements

NUMBER = r"([0-9][0-9,]*(?:\.[0-9]+)?)"
LABELS = {
    "price_ntd": "價格", "weight_g": "重量", "capacity_l": "容量",
    "laptop_inches": "筆電隔層", "padded_back": "加厚背板", "hip_belt": "腰帶",
    "dimensions_cm": "外部尺寸", "bottle_pocket": "水壺袋",
}
UNITS = {"price_ntd": "NT$", "weight_g": "g", "capacity_l": "L", "laptop_inches": "吋"}


def dimensions(text: str) -> tuple[list[float] | None, str | None]:
    match = re.search(r"(\d+(?:\.\d+)?)\s*[xX×*]\s*(\d+(?:\.\d+)?)\s*[xX×*]\s*(\d+(?:\.\d+)?)\s*(?:cm|公分)", text, re.I)
    if not match:
        return None, None
    values = [float(v) for v in match.groups()]
    return (values, match.group(0)) if all(0 < v <= 500 for v in values) else (None, None)


def _number(text: str, patterns: list[str]) -> tuple[float | None, str | None]:
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return float(match.group(1).replace(",", "")), match.group(0)
    return None, None


def extract_specs(description: str) -> dict[str, dict]:
    """Conservative demo grammar. Unknown values are never filled from model memory."""
    text = unicodedata.normalize("NFKC", description)
    specs: dict[str, dict] = {}
    patterns = {
        "price_ntd": [r"(?:NT\$|NTD|TWD|新台幣)\s*" + NUMBER,
                      r"(?:價格|售價|定價)\s*[:：]?\s*" + NUMBER + r"\s*元"],
        "weight_g": [r"(?:重量|weight)\s*[:：]?\s*" + NUMBER + r"\s*(?:公斤|kg|公克|克|g)"],
        "capacity_l": [r"(?:容量|capacity)\s*[:：]?\s*" + NUMBER + r"\s*(?:公升|升|L)"],
        "laptop_inches": [r"(?:筆電(?:隔層)?|laptop)\s*[:：]?\s*(?:支援|可放|最大)?\s*" + NUMBER + r"\s*(?:吋|英寸|inch(?:es)?|\")",
                          r"(?:支援|可放)\s*" + NUMBER + r"\s*(?:吋|英寸)\s*筆電"],
    }
    # Do not interpret a non-TWD price as a local price.
    for attr, regexes in patterns.items():
        value, evidence = _number(text, regexes)
        if attr == "weight_g" and evidence and re.search(r"kg|公斤", evidence, re.I):
            value *= 1000
        if value is not None and (value < 0 or (attr != "price_ntd" and value == 0)):
            value, evidence = None, None
        specs[attr] = {"value": value, "evidence": evidence}
    dims, evidence = dimensions(text)
    specs["dimensions_cm"] = {"value": dims, "evidence": evidence}
    for attr, label in (("padded_back", "加厚背板"), ("hip_belt", "腰帶"), ("bottle_pocket", "水壺袋")):
        match = re.search(label + r"\s*[:：]\s*(有|無|沒有|是|否|yes|no|true|false)", text, re.I)
        value = None
        evidence = None
        if match:
            value = match.group(1).lower() in {"有", "是", "yes", "true"}
            evidence = match.group(0)
        specs[attr] = {"value": value, "evidence": evidence}
    return specs


def draft_requirements(text: str) -> Requirements:
    normalized = unicodedata.normalize("NFKC", text)
    budget, _ = _number(normalized, [
        r"預算\s*(?:不超過|最多|上限|約|為)?\s*[:：]?\s*(?:NT\$|NTD|TWD)?\s*" + NUMBER,
        NUMBER + r"\s*元(?:以內|以下)",
    ])
    weight, evidence = _number(normalized, [
        r"(?:重量|重)\s*(?:不要|不)?\s*(?:超過|高於|大於|上限|最多|低於|小於|少於)\s*" + NUMBER + r"\s*(?:公斤|kg|公克|克|g)",
        r"重量\s*" + NUMBER + r"\s*(?:公斤|kg|公克|克|g)\s*(?:以下|以內)",
    ])
    if evidence and re.search(r"kg|公斤", evidence, re.I):
        weight *= 1000
    laptop, _ = _number(normalized, [NUMBER + r"\s*(?:吋|英寸|inch(?:es)?)\s*(?:的)?\s*(?:筆電|laptop)"])
    capacity, _ = _number(normalized, [r"容量\s*(?:至少|大於|不低於)\s*" + NUMBER + r"\s*(?:公升|升|L)"])
    priority = "balanced"
    if re.search(r"輕量|越輕|輕一點|最輕|lightweight", normalized, re.I):
        priority = "lightweight"
    elif re.search(r"背負|舒適|久背|comfort", normalized, re.I):
        priority = "comfort"
    elif re.search(r"便宜|省錢|低價|最便宜|budget", normalized, re.I):
        priority = "value"
    return Requirements(text=text, budget_ntd=budget, max_weight_g=weight,
                        laptop_inches=laptop, min_capacity_l=capacity, priority=priority,
                        max_dimensions_cm=dimensions(normalized)[0],
                        wants_bottle_pocket=bool(re.search(r"(?:希望|需要|想要|附|有)水壺袋", normalized)))


def persona_for(req: Requirements) -> dict:
    criteria = []
    for attr, key, value, operator, unit in (
        ("weight", "weight_g", req.max_weight_g, "lte", "g"),
        ("laptop_size", "laptop_inches", req.laptop_inches, "gte", "inch"),
        ("capacity_size", "capacity_l", req.min_capacity_l, "gte", "L"),
    ):
        if value is not None:
            criteria.append({"attribute": attr, "operator": operator, "value": value,
                             "unit": unit, "importance": "must" if req.decision_mode == "strict" or key in req.hard_constraints else "should"})
    preference = {"comfort": "comfort", "lightweight": "weight", "value": "price"}.get(req.priority)
    if preference:
        criteria.append({"attribute": preference,
                         "operator": "maximize" if preference == "comfort" else "minimize",
                         "importance": "should"})
    profile = PersonaProfile(
        persona_id="local_shopper", label="這次選購的使用者", use_cases=[req.text],
        budget=({"max_amount": req.budget_ntd, "currency": "TWD", "flexibility": "hard" if req.decision_mode == "strict" or "price_ntd" in req.hard_constraints else "soft"}
                if req.budget_ntd is not None else None),
        criteria=criteria, context={"priority": req.priority, "decision_mode": req.decision_mode,
                                   "hard_constraints": req.hard_constraints,
                                   "max_dimensions_cm": req.max_dimensions_cm,
                                   "accept_review_conditions": req.accept_review_conditions,
                                   "wants_bottle_pocket": req.wants_bottle_pocket},
        notes=["原始描述已保留；本示範僅執行畫面上確認的數值條件與排序偏好。"],
    )
    return profile.model_dump(mode="json", exclude_none=True)


def formatted(attr: str, value: Any) -> str:
    if value is None:
        return "未提供"
    if isinstance(value, bool):
        return "有" if value else "無"
    if attr == "dimensions_cm":
        return " × ".join(f"{v:g}" for v in value) + " cm"
    if attr == "price_ntd":
        return f"NT${value:,.0f}"
    return f"{value:g} {UNITS[attr]}"


def recommend(products: list[dict], req: Requirements) -> dict:
    rows = []
    for product in products:
        specs = product["specs"]
        checks = []
        for attr, threshold, direction in (
            ("price_ntd", req.budget_ntd, "lte"), ("weight_g", req.max_weight_g, "lte"),
            ("laptop_inches", req.laptop_inches, "gte"),
            ("capacity_l", req.min_capacity_l, "gte"),
        ):
            if threshold is None:
                continue
            value = specs[attr]["value"]
            status = ("unknown" if value is None else
                      "pass" if (value <= threshold if direction == "lte" else value >= threshold)
                      else "fail")
            checks.append({"attribute": attr, "label": LABELS[attr], "status": status,
                           "actual": formatted(attr, value),
                           "required": ("≤ " if direction == "lte" else "≥ ") + formatted(attr, threshold),
                           "evidence": specs[attr]["evidence"],
                           "hard": req.decision_mode == "strict" or attr in req.hard_constraints,
                           "gap": (max(0, value - threshold) if direction == "lte" else max(0, threshold - value)) / max(threshold, 1) if value is not None else None})
        applied_evidence = None
        evidence_notes = []
        if req.max_dimensions_cm:
            actual = specs["dimensions_cm"]["value"]
            limit = sorted(req.max_dimensions_cm)
            ordered = sorted(actual) if actual else None
            gap = max((max(0, a - b) / b for a, b in zip(ordered, limit)), default=0) if ordered else None
            dimension_status = "unknown" if actual is None else "pass" if gap == 0 else "fail"
            hard = req.decision_mode == "strict" or "dimensions_cm" in req.hard_constraints
            evidence = product.get("compression_evidence", [])
            conflict = any(e.get("stance") == "conflicting" for e in evidence)
            if dimension_status == "fail" and evidence:
                if conflict:
                    evidence_notes.append("壓縮心得存在反例或互相衝突，這次不採用壓縮尺寸作為可行依據。")
                elif hard:
                    evidence_notes.append("尺寸已設為不可妥協，評論不能取代標示規格。")
                elif not req.accept_review_conditions:
                    evidence_notes.append("有壓縮心得，但你尚未接受附帶條件；仍按標示尺寸比較。")
                else:
                    for item in evidence:
                        compressed = sorted(item["compressed_dimensions_cm"])
                        if item["stance"] == "supporting" and all(a <= b and a <= c for a, b, c in zip(compressed, limit, ordered)):
                            applied_evidence = item
                            dimension_status = "conditional"
                            break
                    if applied_evidence is None:
                        evidence_notes.append("心得中的壓縮尺寸仍無法對應本次限制，不能解除尺寸差距。")
            checks.append({"attribute": "dimensions_cm", "label": LABELS["dimensions_cm"],
                           "status": dimension_status, "actual": formatted("dimensions_cm", actual),
                           "required": "≤ " + formatted("dimensions_cm", req.max_dimensions_cm),
                           "evidence": specs["dimensions_cm"]["evidence"], "hard": hard, "gap": gap})
        blocked = any(c["hard"] and c["status"] != "pass" for c in checks)
        status = ("excluded" if blocked else "pending" if any(c["status"] == "unknown" for c in checks)
                  else "compromise" if any(c["status"] == "fail" for c in checks)
                  else "conditional" if applied_evidence else "eligible")
        price, weight = specs["price_ntd"]["value"], specs["weight_g"]["value"]
        padded, belt = specs["padded_back"]["value"], specs["hip_belt"]["value"]
        components = {
            "value": max(0, 1 - price / 10000) if price is not None else 0,
            "lightweight": max(0, 1 - weight / 3000) if weight is not None else 0,
            "comfort": (int(padded is True) + int(belt is True)) / 2,
        }
        weights = {key: (4 if key == req.priority else 1) for key in components}
        score = sum(components[key] * weights[key] for key in components)
        # Soft gaps cost utility instead of vetoing the product. Conditional
        # evidence reduces the gap penalty but retains a residual uncertainty cost.
        penalty = sum(0.2 if c["status"] == "conditional" else 0.75 if c["status"] == "unknown"
                      else min(3, 0.5 + 5 * c["gap"]) if c["status"] == "fail" else 0 for c in checks)
        if req.wants_bottle_pocket and specs["bottle_pocket"]["value"] is True:
            score += 0.25
        score -= penalty
        reasons = []
        primary = {"comfort": ["padded_back", "hip_belt"], "lightweight": ["weight_g"],
                   "value": ["price_ntd"], "balanced": ["price_ntd", "weight_g"]}[req.priority]
        for attr in primary:
            if specs[attr]["value"] is not None:
                if attr in {"padded_back", "hip_belt"}:
                    if specs[attr]["value"] is True:
                        reasons.append(f"商品資料明確列有{LABELS[attr]}，符合你重視背負設計的方向。")
                else:
                    reasons.append(f"{LABELS[attr]}為 {formatted(attr, specs[attr]['value'])}，已納入你的排序偏好。")
        for check in checks:
            if check["status"] == "pass":
                reasons.append(f"{check['label']} {check['actual']}，符合你設定的 {check['required']}。")
        if req.wants_bottle_pocket and specs["bottle_pocket"]["value"] is True:
            reasons.insert(0, "規格列有水壺袋，符合你希望方便收納水壺的偏好。")
        if applied_evidence:
            reasons.insert(0, "在你接受附帶條件的前提下，心得提供壓縮至 " + formatted("dimensions_cm", applied_evidence["compressed_dimensions_cm"]) + " 的線索；標示規格仍超出限制。")
        cautions = list(evidence_notes)
        for check in checks:
            if check["status"] != "pass":
                cautions.append(f"{check['label']}：{check['actual']}；需求為 {check['required']}。")
        if applied_evidence:
            cautions.extend(["成立條件：" + applied_evidence["conditions"],
                             "這是尚未獨立驗證的心得線索；需以實際裝載後尺寸確認，不保證航空公司接受，也不等於通關保證。"])
        if req.max_dimensions_cm and specs["dimensions_cm"]["value"]:
            excess = max(a - b for a, b in zip(sorted(specs["dimensions_cm"]["value"]), sorted(req.max_dimensions_cm)))
            if excess > 0:
                cautions.insert(0, f"三邊旋轉對齊後，標示尺寸的最大單邊差距為超出 {excess:g} cm。")
        if req.wants_bottle_pocket and specs["bottle_pocket"]["value"] is not True:
            cautions.append("水壺袋：" + formatted("bottle_pocket", specs["bottle_pocket"]["value"]) + "；這項便利性尚未滿足或待確認。")
        if req.priority == "comfort":
            cautions.append("背負設計僅依背板與腰帶規格比對；實際舒適度需要試背，不能由規格保證。")
        if weight is not None and weight > 1000:
            cautions.append(f"空包重量 {formatted('weight_g', weight)}，偏重視輕量時應再比較。")
        missing = [LABELS[attr] for attr in primary if specs[attr]["value"] is None]
        if missing:
            cautions.append("偏好資料缺漏：" + "、".join(missing) + "；排序僅供暫時參考。")
        rows.append({"product": product, "status": status, "checks": checks,
                     "reasons": reasons[:5] or ["依目前提供的商品資料比較；建議確認更多選購條件。"],
                     "cautions": cautions, "score": round(score, 5),
                     "applied_evidence": applied_evidence, "tradeoff_penalty": round(penalty, 5)})
    rows.sort(key=lambda row: (row["status"] == "excluded", -row["score"], row["product"]["id"]))
    winner = next((row for row in rows if row["status"] != "excluded"), None)
    summary = (f"綜合偏好、差距與不確定性，本次相對首選是 {winner['product']['name']}；請一併確認取捨與成立條件。"
               if winner else "目前沒有商品能確認符合你設定的不可妥協條件，請查看差距或待確認項目。")
    if winner:
        winner_price = winner["product"]["specs"]["price_ntd"]["value"]
        reference = next((r for r in rows if r is not winner and r["status"] == "eligible" and r["product"]["specs"]["price_ntd"]["value"] is not None), None)
        if reference and winner_price is not None:
            saved = reference["product"]["specs"]["price_ntd"]["value"] - winner_price
            if saved > 0:
                winner["reasons"].insert(0, f"相較規格符合的 {reference['product']['name']}，省下 NT${saved:,.0f}；這份價差與取捨已一起比較。")
    return {"mode": "offline_rules", "winner_id": winner["product"]["id"] if winner else None,
            "summary": summary, "persona": persona_for(req), "requirements": req.model_dump(),
            "results": rows,
            "notice": "離線規則示範：未呼叫語言模型或搜尋網路。示範商品與示範心得皆為虛構；匯入商品依提供文字比對。"}
