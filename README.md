# Hossam State Image Server — FIXED

Backend for Hossam State Custom Rich Presence image uploads.

## Supported formats
- JPG / JPEG
- PNG
- WEBP
- GIF (animated GIF is preserved)
- Maximum size: 8 MB

## Required Render environment variables

SUPABASE_URL
Example:
https://YOUR_PROJECT.supabase.co

SUPABASE_SERVICE_ROLE_KEY
Use your Supabase server-side service-role key. Never put this key in the Android app or expose it publicly.

SUPABASE_BUCKET
hossam-images

## Supabase setup

1. Open Supabase.
2. Go to Storage.
3. Create a bucket named exactly:
   hossam-images
4. Make the bucket Public.
5. Make sure the bucket allows the image formats you need and does not have a size limit below 8 MB.

The bucket must be public because Discord needs to access the returned image URL without authentication.

## Render

Root Directory: leave empty if these files are at the repository root.

Build Command:
pip install -r requirements.txt

Start Command:
uvicorn main:app --host 0.0.0.0 --port $PORT

Health Check Path:
/health

## Test

Open:
https://YOUR-RENDER-SERVICE.onrender.com/health

A healthy response should include:

{
  "status": "ok",
  "storage_configured": true,
  "bucket": "hossam-images",
  "bucket_reachable": true
}

If bucket_reachable is false, the response includes a safe Supabase error explaining the problem without exposing the secret key.

## Upload endpoint

POST /upload

multipart field:
file

Response:

{
  "success": true,
  "url": "https://.../storage/v1/object/public/hossam-images/custom/....gif"
}

The original bytes are uploaded, so animated GIFs remain animated.

## Security

The service-role key is only used by this backend. Never put it in the Android application.
