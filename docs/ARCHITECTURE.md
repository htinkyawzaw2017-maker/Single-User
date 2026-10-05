# Architecture

## System overview

```
┌─────────────────────────────────────────────────────────────────┐
│ Browser — React + TypeScript SPA (Vite build)                    │
│  • pages: Dashboard, NewProject, Processing, Editor,             │
│    VoiceReview, LipSyncReview, Export                            │
│  • polls /api/projects/{id} every 2.5s for live pipeline state   │
└───────────────────────────┬─────────────────────────────────────┘
                            │  relative /api/* URLs
┌───────────────────────────▼─────────────────────────────────────┐
│ Backend — FastAPI (ECS Fargate container, serves the SPA too)    │
│  routes: projects / segments / jobs / uploads / media / exports  │
│  auth: single access key middleware (env SINGLE_USER_ACCESS_KEY) │
│                                                                  │
│  runner.py — background worker thread pool = the job workflow    │
│  (local equivalent of the Step Functions state machine)          │
└──────┬───────────────────────────────┬──────────────────────────┘
       │ SQLAlchemy                    │ provider adapters
┌──────▼──────────┐          ┌─────────▼──────────────────────────┐
│ SQLite (local)  │          │ transcription: mock(silencedetect) │
│ RDS Postgres    │          │                 or Amazon Transcribe│
│ (AWS)           │          │ translation:   mock dict / LLM API  │
└─────────────────┘          │ tts:           mock tones / HTTP    │
                             │ lipsync:       mock / SageMaker GPU │
                             └────────────────────────────────────┘
       │ storage abstraction (same S3-style keys in both modes)
┌──────▼──────────────────────────────────────────────────────────┐
│ local dev: backend/data/files/<key>                              │
│ AWS:       S3 input bucket (uploads/*) + output bucket (rest)    │
│            lifecycle rules, presigned PUT/GET, CORS for uploads  │
└──────────────────────────────────────────────────────────────────┘
```

## Upload flow (large files never touch the app server in AWS mode)

1. `POST /api/projects/{id}/upload-url` → storage backend returns either a
   local one-time PUT token URL (dev) or an S3 presigned PUT URL (AWS).
2. Browser XHR-PUTs the file directly with progress events.
3. `POST /api/projects/{id}/upload-complete` verifies the object exists and
   starts the pipeline.

## Job workflow

`backend/app/runner.py` executes steps sequentially in a thread pool,
persisting every transition:

- step list & running statuses in `app/states.py`
- user checkpoints: `AWAITING_USER_REVIEW`, `AWAITING_VOICE_APPROVAL`,
  lip-sync preview approval
- per-step `jobs` rows: pending → running (progress %, timestamped log)
  → completed / failed
- `POST /api/jobs/{id}/retry` restarts exactly that step
- segment voice generation is its own job (`segment_voice:{id}`) so a bad
  segment never blocks or restarts the project
- browser-independent: closing the tab does not stop processing; refresh
  restores full state from the DB

The production Step Functions definition
(`infrastructure/step-functions/pipeline.asl.json`) mirrors the same
states, with callback-pattern waits for user review — for when the tool
needs to scale beyond a single user.

## Timing alignment & mixing rules (spec §9)

For each segment:

1. raw TTS duration `g`, slot duration `s = end − start`
2. if `g ≤ s×1.02` → no stretch
3. else stretch factor `g/s`; capped at `MAX_SPEED_STRETCH` (1.35 default,
   combined with the user's manual speed slider)
4. if it still does not fit → segment flagged `too_long` with an
   actionable warning ("shorten the text or increase speed") — the audio is
   never silently mangled

Mixing: per-segment aligned WAVs are concatenated with silence gaps into a
dub track, then `amix`ed with the original audio attenuated to
`project.bg_volume` (user-controlled). If the source has no audio track,
the dub track becomes the full mix.

## Lip-sync (beta, isolated)

- only runs in `dialogue_lipsync` mode
- face quality check first (mock heuristic / Rekognition in the SageMaker
  adapter) — side-facing, occluded, multi-face → clear failure message
- renders a 10–30 s preview window only; full render waits for approval
- any failure keeps the audio-only pipeline fully available
  (`actions/lipsync-audio-only`)

## Data model (spec §7)

**projects**: id, name, source_language, target_language, mode, status,
source_video_s3_key, output_video_s3_key, error_message, created_at,
updated_at (+ video metadata, bg_volume, lipsync_status, watermark flag)

**segments**: id, project_id, segment_index, speaker_id, start_time,
end_time, source_text, target_text, voice_id, audio_s3_key,
audio_duration, speed_factor, status, approved (+ aligned audio key,
auto_stretch, emotion, warnings)

**jobs**: id, project_id, job_type, status, progress, started_at,
completed_at, error_message, retry_count (+ log, payload)
