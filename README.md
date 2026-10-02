# LaunchFlow AI

LaunchFlow turns one product brief and product image into coordinated campaign copy and platform-sized marketing compositions for Instagram, YouTube, Facebook, X, and WhatsApp. Campaign Brain and OpenRouter text generation remain server-side. Images default to local Pillow compositions built around the uploaded product photo; generated artwork is a designed marketing asset, not a generated photograph.

## Project structure

- `backend/main.py`: FastAPI campaign, caption, image, and script endpoints.
- `backend/services/campaign_brain.py`: Campaign Brain text generation.
- `backend/services/image_generator.py`: contain-fit product image composition and optional image-provider adapter.
- `backend/services/media_storage.py`: local media storage abstraction.
- `frontend-react/`: the React/Vite application.

## Run locally

Backend terminal:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Set OPENROUTER_API_KEY in backend/.env for Campaign Brain and text generation.
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Frontend terminal:

```bash
cd frontend-react
npm ci
npm run dev -- --host 127.0.0.1
```

Open `http://127.0.0.1:5173`. Vite proxies `/api` and `/uploads` to the backend. Build the frontend with `npm run build`.

## Environment variables

Copy `backend/.env.example` to `backend/.env`. Keep secrets server-side; never put API keys in a `VITE_` variable. `.env` files are ignored by Git.

| Variable | Default | Purpose |
| --- | --- | --- |
| `OPENROUTER_API_KEY` | empty | Server-side key for Campaign Brain, captions, and scripts. |
| `OPENROUTER_MODEL` | free Llama model | Text-generation model. |
| `VISUAL_PROVIDER` | `local` | `local` creates Pillow compositions without paid image credits; `openrouter` enables the optional image adapter. |
| `OPENROUTER_IMAGE_MODEL` | configured image model | Used only by the optional OpenRouter image adapter. |
| `MEDIA_STORAGE` | `local` | Local media adapter. Cloud storage can be added behind the existing storage service. |
| `MEDIA_LOCAL_DIR` | `uploads` | Media directory relative to `backend/`; use a persistent mount in deployment. |
| `CORS_ORIGINS` | local Vite origins | Comma-separated exact frontend origins. |
| `VITE_API_URL` | same-origin relative URLs | Frontend build-time API origin when frontend and backend are separate. |

The deployed default does not use OpenRouter image/video credits. Reel/Short script generation remains text-only and uses Campaign Brain text generation.

## Production deployment

1. Install backend dependencies from `backend/requirements.txt` and frontend dependencies from `frontend-react/package-lock.json`.
2. Set server-side `OPENROUTER_API_KEY`, `VISUAL_PROVIDER=local`, `MEDIA_STORAGE=local`, `MEDIA_LOCAL_DIR` to a persistent writable mount, and `CORS_ORIGINS` to the exact frontend origin(s).
3. Build with `cd frontend-react && npm ci && VITE_API_URL=https://your-api.example npm run build` when using separate origins.
4. Start the API from `backend/` using `uvicorn main:app --host 0.0.0.0 --port 8000` (configure the host's assigned port as required).

Local media uses `/uploads/{filename}`. Ephemeral filesystems lose media on restart; multi-instance deployments need persistent shared storage or a cloud storage adapter implemented behind `media_storage.py`. The local storage adapter is the only implemented media backend today.

## Campaign and assets

- Campaign generation returns text even if an individual platform image fails. Image failures are reported per asset.
- Local layouts contain-fit the uploaded product without stretching or cropping opaque product pixels. Transparent padding is removed safely; opaque source images are kept intact. Each of the eight platform formats has its own product placement, typography, background, and CTA layout, with checks for safe product/text bounds and exact PNG dimensions.
- Exact image presets: Instagram Post 1080×1350 (4:5), Instagram Story/Reel 1080×1920 (9:16), YouTube Thumbnail 1280×720 (16:9), YouTube Short 1080×1920 (9:16), Facebook Post 1080×1080 (1:1), X Post 1600×900 (16:9), WhatsApp Message 1080×1080 (1:1), and WhatsApp Status 1080×1920 (9:16).
- The UI previews the entire image, displays its dimensions, downloads the actual generated PNG, and provides per-platform caption/script copy controls.
- Restart clears the current brief and campaign in the app. Human approval is a review state only; it does not publish to social media.
- `/api/generate-video-script` remains for script-only Instagram Reel and YouTube Short ideation. Actual video generation and `/api/generate-video` have been removed.

## API endpoints

| Method and path | Purpose |
| --- | --- |
| `GET /api/health` | Health check. |
| `POST /api/generate-campaign` | Campaign Brain, platform copy, platform assets, and quality report. |
| `POST /api/quality-check` | Rechecks campaign content. |
| `POST /api/regenerate-caption` | Regenerates one platform's caption. |
| `POST /api/generate-video-script` | Generates a script idea only; no video or MP4 is produced. |
| `GET /uploads/{filename}` | Serves local media. |

The quality checker checks required content, product name, price, USP coverage, and X's 280-character limit. Audience and tone checks are heuristic warnings. The app has no authentication; add access controls before exposing generation endpoints publicly.
