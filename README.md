# Hossam State — Image Upload Server

Server for the Hossam State Android app to upload custom Rich Presence images.

### Supported files

- JPG / JPEG
- PNG
- WEBP
- GIF, including animated GIFs

Static images are normalized to JPEG. GIF files stay GIF so their animation is preserved.

Flow:

Gallery → Android → POST /upload → FastAPI → Supabase Storage → public HTTPS URL → Discord Rich Presence

## 1. Supabase Storage

Create a Supabase project and create a Storage bucket named:

`hossam-images`

Make the bucket **Public**. Public bucket assets can then be read directly by the public object URL.

Create no client-side Supabase key in the Android app. The server uses the **service-role key only as an environment secret**.

## 2. Render

Create a Render Web Service from this `backend/` directory.

Build:

`pip install -r requirements.txt`

Start:

`uvicorn main:app --host 0.0.0.0 --port $PORT`

Environment variables:

- `SUPABASE_URL` = your Supabase project URL
- `SUPABASE_SERVICE_ROLE_KEY` = Supabase server-side service-role key
- `SUPABASE_BUCKET` = `hossam-images`

Render provides a public HTTPS `onrender.com` URL for a web service.

## 3. Test

Open:

`https://YOUR-SERVICE.onrender.com/health`

It should return JSON with `storage_configured: true` and `gif_supported: true`.

Then test an upload as multipart form field named `file`.

The response contains `url`, which is the exact URL the Android app can send to Discord as `largeImage`.

For a GIF, the response also returns `animated: true`, the frame count, and `content_type: image/gif`.

## Limits

- Maximum input size: 8 MB.
- Maximum image dimension after processing: 1024px.
- GIF animation is preserved.
- Static images are converted to JPEG.
- Uploaded objects use random names under `custom/`.

## Security

- Never put `SUPABASE_SERVICE_ROLE_KEY` in the Android app.
- The endpoint only accepts image files.
- The returned object path is random.
- Because the Supabase bucket is public, uploaded images are publicly readable by URL.
