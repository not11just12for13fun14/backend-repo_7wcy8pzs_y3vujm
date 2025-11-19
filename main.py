import os
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from schemas import BlogPost
from database import create_document, get_documents, db

try:
    from bson import ObjectId
except Exception:
    ObjectId = None  # Fallback, routes will raise if missing

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def serialize_doc(doc: dict) -> dict:
    if not doc:
        return doc
    d = dict(doc)
    if d.get("_id") is not None:
        d["id"] = str(d.pop("_id"))
    # Convert datetime fields to ISO strings if present
    for k in ("created_at", "updated_at"):
        if k in d and hasattr(d[k], "isoformat"):
            d[k] = d[k].isoformat()
    return d


@app.get("/")
def read_root():
    return {"message": "Pottery Blog Backend Running"}


@app.get("/api/hello")
def hello():
    return {"message": "Hello from the backend API!"}


@app.get("/test")
def test_database():
    """Test endpoint to check if database is available and accessible"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"

    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    # Check environment variables
    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"

    return response


# Blog API
@app.post("/api/posts")
def create_post(post: BlogPost):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    inserted_id = create_document("blogpost", post)
    # Fetch the created document to return
    created = db["blogpost"].find_one({"_id": ObjectId(inserted_id)}) if ObjectId else None
    return {"id": inserted_id, "post": serialize_doc(created) if created else post.model_dump()}


@app.get("/api/posts")
def list_posts(
    limit: Optional[int] = Query(default=20, ge=1, le=100),
    tag: Optional[str] = Query(default=None, description="Filter by tag"),
):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    filt = {}
    if tag:
        filt = {"tags": {"$in": [tag]}}
    items = get_documents("blogpost", filt, limit)
    return [serialize_doc(it) for it in items]


@app.get("/api/posts/{post_id}")
def get_post(post_id: str):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    try:
        oid = ObjectId(post_id) if ObjectId else None
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid post id")
    doc = db["blogpost"].find_one({"_id": oid}) if oid else None
    if not doc:
        raise HTTPException(status_code=404, detail="Post not found")
    return serialize_doc(doc)


class UpdatePost(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    cover_image: Optional[str] = None
    tags: Optional[List[str]] = None
    author: Optional[str] = None


@app.put("/api/posts/{post_id}")
def update_post(post_id: str, payload: UpdatePost):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    try:
        oid = ObjectId(post_id) if ObjectId else None
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid post id")
    if oid is None:
        raise HTTPException(status_code=500, detail="ObjectId support not available")

    updates = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
    if not updates:
        return {"updated": False}
    updates["updated_at"] = __import__("datetime").datetime.utcnow()
    result = db["blogpost"].update_one({"_id": oid}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Post not found")
    doc = db["blogpost"].find_one({"_id": oid})
    return serialize_doc(doc)


@app.delete("/api/posts/{post_id}")
def delete_post(post_id: str):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    try:
        oid = ObjectId(post_id) if ObjectId else None
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid post id")
    res = db["blogpost"].delete_one({"_id": oid}) if oid else None
    if not res or res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Post not found")
    return {"deleted": True}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
