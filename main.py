import io
import os
import uuid
import logging
from pathlib import Path

import requests
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, UnidentifiedImageError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("hossam-image-server")

app = FastAPI(title="Hossam State Image Server", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "hossam-images")

MAX_SIZE = 8 * 1024 * 1024

ALLOWED_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}

def config_ok():
    return bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY and SUPABASE_BUCKET)

def safe_supabase_error(response):
    # Never log or return the authorization key.
    try:
        body = response.text[:1000]
    except Exception:
        body = ""
    return f"HTTP {response.status_code}: {body}"

@app.get("/")
def root():
    return {
        "name": "Hossam State Image Server",
        "status": "ok",
        "upload": "/upload",
        "formats": ["JPG", "PNG", "WEBP", "GIF"],
        "max_mb": 8,
    }

@app.get("/health")
def health():
    result = {
        "status": "ok",
        "storage_configured": config_ok(),
        "bucket": SUPABASE_BUCKET,
    }

    if not config_ok():
        result["status"] = "error"
        result["storage"] = "not_configured"
        return result

    # Verify that the configured bucket is reachable.
    try:
        url = f"{SUPABASE_URL}/storage/v1/bucket/{SUPABASE_BUCKET}"
        headers = {
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
        }
        r = requests.get(url, headers=headers, timeout=15)
        result["bucket_reachable"] = r.ok
        if not r.ok:
            result["status"] = "error"
            result["storage_error"] = safe_supabase_error(r)
    except Exception as e:
        result["status"] = "error"
        result["bucket_reachable"] = False
        result["storage_error"] = str(e)[:500]

    return result

@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    if not config_ok():
        raise HTTPException(
            status_code=500,
            detail="Storage server is not configured."
        )

    content_type = (file.content_type or "").lower().split(";")[0].strip()
    if content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Unsupported format. Use JPG, PNG, WEBP, or GIF."
        )

    data = await file.read()

    if not data:
        raise HTTPException(status_code=400, detail="Empty file.")

    if len(data) > MAX_SIZE:
        raise HTTPException(status_code=413, detail="Maximum file size is 8 MB.")

    # Validate the actual image bytes, not just the MIME type.
    try:
        with Image.open(io.BytesIO(data)) as image:
            detected = (image.format or "").upper()
            allowed_detected = {"JPEG", "PNG", "WEBP", "GIF"}
            if detected not in allowed_detected:
                raise HTTPException(
                    status_code=400,
                    detail="The uploaded file is not a supported image."
                )
            image.verify()
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError):
        raise HTTPException(
            status_code=400,
            detail="Invalid or corrupted image."
        )

    ext = ALLOWED_TYPES[content_type]

    # Prefer the real detected format when a client sends a generic/wrong MIME type.
    try:
        with Image.open(io.BytesIO(data)) as image:
            detected = (image.format or "").upper()
        if detected == "JPEG":
            ext = ".jpg"
            content_type = "image/jpeg"
        elif detected == "PNG":
            ext = ".png"
            content_type = "image/png"
        elif detected == "WEBP":
            ext = ".webp"
            content_type = "image/webp"
        elif detected == "GIF":
            ext = ".gif"
            content_type = "image/gif"
    except Exception:
        pass

    filename = f"{uuid.uuid4().hex}{ext}"
    object_path = f"custom/{filename}"

    upload_url = (
        f"{SUPABASE_URL}/storage/v1/object/"
        f"{SUPABASE_BUCKET}/{object_path}"
    )

    headers = {
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Content-Type": content_type,
        "x-upsert": "false",
        "Cache-Control": "31536000",
    }

    logger.info(
        "Uploading %s (%s, %d bytes) to bucket=%s",
        filename,
        content_type,
        len(data),
        SUPABASE_BUCKET,
    )

    try:
        response = requests.post(
            upload_url,
            headers=headers,
            data=data,
            timeout=45,
        )
    except requests.RequestException as e:
        logger.error("Supabase request failed: %s", str(e)[:500])
        raise HTTPException(
            status_code=502,
            detail="Storage connection failed."
        )

    if not response.ok:
        error_text = safe_supabase_error(response)
        logger.error("Supabase upload failed: %s", error_text)
        raise HTTPException(
            status_code=502,
            detail=f"Storage upload failed: {error_text}"
        )

    public_url = (
        f"{SUPABASE_URL}/storage/v1/object/public/"
        f"{SUPABASE_BUCKET}/{object_path}"
    )

    logger.info("Upload successful: %s", public_url)

    return {
        "success": True,
        "url": public_url,
        "public_url": public_url,
        "filename": filename,
        "content_type": content_type,
        "size": len(data),
    }
