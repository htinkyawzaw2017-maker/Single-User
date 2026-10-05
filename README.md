# 🎬 Single-User Burmese/English Movie Dubbing Tool

A private, single-user web application for a Burmese/English movie recap
creator: upload a clip, transcribe, translate, review & edit every segment,
generate dubbed voices, align them to the original timing, optionally
lip-sync, and export the final video — MP4, audio tracks and SRT/VTT
subtitles.

**မြန်မာအသုံးပြုပုံ အသေးစိတ်** → [`docs/GUIDE_MY.md`](docs/GUIDE_MY.md)
**AWS တင်ပုံ CMD guide (မြန်မာ)** → [`docs/AWS_DEPLOY_GUIDE_MY.md`](docs/AWS_DEPLOY_GUIDE_MY.md)

---

## Feature checklist (MVP)

| Feature | Status |
|---|---|
| Single private user (optional access key) | ✅ |
| EN ⇄ MY direction | ✅ |
| Video upload from browser (progress + presigned URL) | ✅ |
| Project list / detail, statuses, delete | ✅ |
| Audio extraction (ffmpeg) | ✅ |
| Timestamped transcription (silence detection / Amazon Transcribe adapter) | ✅ |
| Translation + natural rewrite (mock / LLM adapter) | ✅ |
| Manual transcript & translation editor (video + timeline + segment panel) | ✅ |
| Voice selection per speaker (voice catalog) | ✅ |
| Segment-by-segment TTS generation | ✅ |
| Regenerate ONE segment without touching the project | ✅ |
| Timing alignment with stretch cap + warnings | ✅ |
| Background audio volume control | ✅ |
| MY + EN subtitle export (SRT/VTT) | ✅ |
| Dubbed audio preview | ✅ |
| Final MP4 export (+720p preview, watermark, burned subs, dual audio) | ✅ |
| Processing progress, per-step logs, retry, cancel | ✅ |
| AWS S3 storage (local disk fallback for dev) | ✅ |
| Background job workflow (built-in worker; Step Functions ASL included) | ✅ |
| Lip-sync beta (isolated optional worker, preview-first, graceful failure) | ✅ (mock provider) |

Not in MVP (by design): multi-user, social features, billing, mobile,
live dubbing.

## Quick start (local)

```bash
# 1. backend
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 2. frontend
cd ../frontend
npm install
npm run build          # the backend serves frontend/dist

# 3. run
cd ../backend
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
# → open http://localhost:8000
```

or `./scripts/dev.sh` for hot-reload development (Vite :5173 + API :8000).

The app boots with **offline mock providers** (mock transcription, mock
dictionary translation, tone-based mock TTS) so the entire pipeline works
with zero API keys. A bundled demo clip lets you exercise the full flow
in one click ("Use bundled demo clip").

## Switching to real providers

| Concern | Env vars |
|---|---|
| Real translation / rewrite | `TRANSLATION_PROVIDER=llm`, `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` |
| Real Burmese/English TTS | `TTS_PROVIDER=http`, `TTS_HTTP_URL`, `TTS_HTTP_KEY` (any JSON-in / audio-out service) |
| Amazon Transcribe | `TRANSCRIPTION_PROVIDER=aws` (needs S3 storage + IAM) |
| GPU lip-sync | `LIPSYNC_PROVIDER=sagemaker`, `LIPSYNC_ENDPOINT_NAME` |
| Private access key | `SINGLE_USER_ACCESS_KEY=<random string>` |
| Postgres | `DATABASE_URL=postgresql+psycopg2://user:pass@host/db` |
| S3 storage | `STORAGE_BACKEND=s3`, `S3_INPUT_BUCKET`, `S3_OUTPUT_BUCKET`, `AWS_REGION` |

API keys are read from env or AWS Secrets Manager — never from frontend code.

## Repository layout

```
frontend/            React + TypeScript (Vite)
  src/pages/           Dashboard, NewProject, Processing, Editor,
                       VoiceReview, LipSyncReview, Export, ProjectShell
  src/components/      Layout, Pipeline, VideoPlayer, LogViewer, …
  src/editor/          SegmentTimeline, SegmentPanel
  src/api/             typed fetch client + presigned upload w/ progress
  src/types/           shared types

backend/             FastAPI (Python 3.11)
  app/routes/          projects, segments, jobs, uploads, media, exports
  app/services/
    storage/           local disk + S3 backends (same key layout)
    transcription/     silence-detect mock + Amazon Transcribe adapter
    translation/       dictionary mock + LLM (OpenAI-compatible) adapter
    tts/               tone mock + HTTP provider adapter + voice catalog
    lipsync/           mock + SageMaker async endpoint adapter
    rendering.py       ffmpeg composition, watermark, burn-in, dual audio
    audio.py           alignment/stretch/mixing
    subtitles.py       SRT/VTT
  app/runner.py        background job workflow (state machine executor)
  app/models.py        projects / segments / jobs (SQLAlchemy)
  app/workflows/…      (see infrastructure/step-functions for the AWS ASL)

infrastructure/      AWS deployment
  deploy.sh            one-shot CLI deployment (S3 → ECR → RDS → ECS → ALB)
  template.yaml        CloudFormation equivalent
  s3/                  lifecycle + CORS policies
  ecs/                 example task definition
  step-functions/      production ASL workflow (optional)
  sagemaker/           GPU lip-sync endpoint template (optional)
  cloudfront/          HTTPS/WAF hardening notes (optional)

scripts/             dev.sh, build_demo_clip.sh
docs/                Burmese user guide + AWS deploy guide + architecture
Dockerfile           multi-stage: builds frontend, serves it from FastAPI
```

## Pipeline / state machine

```
CREATED → UPLOADED → EXTRACTING_AUDIO → TRANSCRIBING → TRANSLATING
        → AWAITING_USER_REVIEW            ← user edits text
        → GENERATING_VOICE → ALIGNING_TIMING
        → AWAITING_VOICE_APPROVAL          ← user reviews voices
        → LIP_SYNCING (optional, preview-first)
        → RENDERING → COMPLETED
any step ↘ FAILED (retryable per step) / CANCELLED
```

Every step is a `jobs` row with status/progress/log/retry_count. One failed
segment never restarts the project — segments regenerate individually.

## License / usage

Private single-user tool. Only dub content you have the rights to use.
