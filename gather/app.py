"""Gather's local application and product storage."""

import json
import os
import sqlite3
import uuid
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .html_text import clean_html

from .models import ProductInput, RecommendRequest, RequirementText
from .service import draft_requirements, extract_specs, persona_for, recommend

ROOT = Path(__file__).resolve().parent


class Catalog:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=10)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def init(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS products (id TEXT PRIMARY KEY, data TEXT)")
            for item in json.loads((ROOT / "catalog.json").read_text(encoding="utf-8")):
                item["is_demo"] = True
                item["specs"] = extract_specs(item["description"])
                conn.execute("INSERT OR REPLACE INTO products VALUES (?, ?)",
                             (item["id"], json.dumps(item, ensure_ascii=False)))

    def products(self) -> list[dict]:
        with self.connect() as conn:
            items = [json.loads(row[0]) for row in conn.execute("SELECT data FROM products ORDER BY rowid")]
        # Re-extract older local records when the demo grammar evolves.
        for item in items:
            item["specs"] = extract_specs(item["description"])
        return items

    def save(self, item: dict):
        with self.connect() as conn:
            conn.execute("INSERT INTO products VALUES (?, ?)",
                         (item["id"], json.dumps(item, ensure_ascii=False)))

    def delete(self, product_id: str):
        if product_id.startswith("demo-"):
            raise HTTPException(400, "內建示範商品請取消勾選，不需刪除。")
        with self.connect() as conn:
            deleted = conn.execute("DELETE FROM products WHERE id = ?", (product_id,)).rowcount
        if not deleted:
            raise HTTPException(404, "找不到商品。")


def create_app(database: Path | None = None) -> FastAPI:
    path = database or Path(os.environ.get(
        "GATHER_DB", str(ROOT.parent / "data" / "gather.db")))
    catalog = Catalog(path)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        catalog.init()
        yield

    app = FastAPI(title="Gather — Consumer Shopping", lifespan=lifespan)
    app.mount("/assets", StaticFiles(directory=ROOT / "static"), name="assets")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(ROOT / "static" / "index.html")

    @app.get("/api/demo/health")
    def health():
        return {"status": "ok", "mode": "offline_rules", "aws": False, "llm": False}

    @app.get("/api/demo/products")
    def products():
        return {"products": catalog.products(), "mode": "offline_rules"}

    @app.post("/api/demo/products", status_code=201)
    def add_product(body: ProductInput):
        description = body.description.strip()
        if "<" in description and ">" in description:
            _, description = clean_html(description)
        if len(description) < 10 or not body.name.strip():
            raise HTTPException(422, "請提供商品名稱與至少 10 個字的商品規格。")
        item = {"id": "custom-" + uuid.uuid4().hex[:12], "name": body.name.strip(),
                "brand": body.brand.strip() or "自訂商品", "description": description,
                "specs": extract_specs(description), "is_demo": False,
                "compression_evidence": [e.model_dump(mode="json") for e in body.compression_evidence],
                "review": None, "color": "slate"}
        catalog.save(item)
        return item

    @app.delete("/api/demo/products/{product_id}")
    def delete_product(product_id: str):
        catalog.delete(product_id)
        return {"deleted": product_id}

    @app.post("/api/demo/requirements")
    def requirements(body: RequirementText):
        try:
            draft = draft_requirements(body.text)
        except ValueError as exc:
            raise HTTPException(422, "解析出的數值超出範圍，請調整描述或直接填寫下方條件。") from exc
        return {"requirements": draft.model_dump(), "persona": persona_for(draft)}

    @app.post("/api/demo/recommend")
    def recommendation(body: RecommendRequest):
        by_id = {p["id"]: p for p in catalog.products()}
        ids = list(dict.fromkeys(body.product_ids))
        if any(pid not in by_id for pid in ids):
            raise HTTPException(404, "部分商品不存在，請重新載入商品清單。")
        return recommend([by_id[pid] for pid in ids], body.requirements)

    return app


app = create_app()
