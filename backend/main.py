import io
import os
import uuid

import requests
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, ImageSequence

APP_NAME = "Hossam State Image Server"
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_DIMENSION = 1024

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "hossam-images").strip()

app = FastAPI(title=APP_NAME, version="1.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"]
)


def require_storage_config():
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise HTTPException(status_code=503, detail="Image storage is not configured")


def read_and_validate_image(data: bytes) -> tuple[Image.Image, bool, int]:
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
        is_gif = image.format == "GIF"
        frame_count = getattr(image, "n_frames", 1)
        return image, is_gif, frame_count
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid image file") from exc


def encode_static_image(image: Image.Image) -> tuple[bytes, str, int, int]:
    image = image.copy()
    image.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.Resampling.LANCZOS)

    if image.mode in ("RGBA", "LA") or "transparency" in image.info:
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, (20, 20, 20))
        background.paste(rgba, mask=rgba.getchannel("A"))
        image = background
    else:
        image = image.convert("RGB")

    out = io.BytesIO()
    image.save(out, format="JPEG", quality=90, optimize=True, progressive=True)
    return out.getvalue(), "image/jpeg", image.width, image.height


def encode_gif(image: Image.Image) -> tuple[bytes, str, int, int]:
    """Preserve GIF animation while limiting the largest dimension to 1024px."""
    frames = []
    durations = []
    disposal = []
    loop = image.info.get("loop", 0)
    needs_resize = max(image.size) > MAX_DIMENSION

    try:
        for frame in ImageSequence.Iterator(image):
            frame_rgba = frame.convert("RGBA")
            if needs_resize:
                frame_rgba.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.Resampling.LANCZOS)
            frames.append(frame_rgba.copy())
            durations.append(frame.info.get("duration", image.info.get("duration", 100)))
            disposal.append(frame.info.get("disposal", 0))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid animated GIF") from exc

    if not frames:
        raise HTTPException(status_code=400, detail="GIF contains no frames")

    out = io.BytesIO()
    first, *rest = frames
    save_kwargs = {
        "format": "GIF",
        "save_all": True,
        "append_images": rest,
        "duration": durations,
        "loop": loop,
        "disposal": disposal,
        "optimize": True,
    }
    try:
        first.save(out, **save_kwargs)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Could not encode GIF") from exc

    return out.getvalue(), "image/gif", frames[0].width, frames[0].height


def prepare_image(data: bytes) -> tuple[bytes, str, int, int, bool, int]:
    image, is_gif, frame_count = read_and_validate_image(data)

    if is_gif:
        encoded, content_type, width, height = encode_gif(image)
        return encoded, content_type, width, height, True, frame_count

    encoded, content_type, width, height = encode_static_image(image)
    return encoded, content_type, width, height, False, 1


def upload_to_supabase(data: bytes, object_path: str, content_type: str) -> str:
    url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}/{object_path}"
    headers = {
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Content-Type": content_type,
        "Cache-Control": "public, max-age=31536000, immutable",
        "x-upsert": "false",
    }
    try:
        response = requests.post(url, headers=headers, data=data, timeout=30)
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail="Storage service unavailable") from exc

    if response.status_code not in (200, 201):
        raise HTTPException(status_code=502, detail="Image storage upload failed")

    return f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_BUCKET}/{object_path}"


@app.get("/")
def root():
    return {"status": "ok", "service": APP_NAME}


@app.get("/health")
def health():
    configured = bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)
    return {"status": "ok", "storage_configured": configured, "gif_supported": True}


@app.post("/upload")
async def upload_image(file: UploadFile = File(...)):
    require_storage_config()

    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=415, detail="Only image files are allowed")

    data = await file.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image is too large (max 8 MB)")

    encoded, content_type, width, height, is_gif, frame_count = prepare_image(data)
    extension = "gif" if is_gif else "jpg"
    object_path = f"custom/{uuid.uuid4().hex}.{extension}"
    public_url = upload_to_supabase(encoded, object_path, content_type)

    return {
        "ok": True,
        "url": public_url,
        "content_type": content_type,
        "width": width,
        "height": height,
        "animated": is_gif,
        "frames": frame_count,
    }
