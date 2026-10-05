// Types mirroring the backend API schemas.

export type Language = 'en' | 'my'
export type Mode = 'recap_narration' | 'dialogue_dubbing' | 'dialogue_lipsync'

export type ProjectStatus =
  | 'CREATED' | 'UPLOADED' | 'EXTRACTING_AUDIO' | 'TRANSCRIBING'
  | 'TRANSLATING' | 'AWAITING_USER_REVIEW' | 'GENERATING_VOICE'
  | 'ALIGNING_TIMING' | 'AWAITING_VOICE_APPROVAL' | 'LIP_SYNCING'
  | 'RENDERING' | 'COMPLETED' | 'FAILED' | 'CANCELLED'

export interface Voice {
  id: string
  name: string
  language: Language
  gender: 'male' | 'female'
}

export interface AppConfig {
  app_env: string
  auth_required: boolean
  upload_mode: 'local' | 's3'
  max_upload_mb: number
  languages: { code: string; label: string }[]
  modes: { code: Mode; label: string; description: string }[]
  voice_styles: string[]
  emotions: string[]
  voices: Voice[]
  providers: Record<string, string>
  demo_clip_available: boolean
  ffmpeg_available: boolean
}

export interface Segment {
  id: string
  segment_index: number
  speaker_id: string
  start_time: number
  end_time: number
  source_text: string
  target_text: string
  voice_id: string | null
  audio_s3_key: string | null
  aligned_audio_key: string | null
  audio_duration: number | null
  aligned_duration: number | null
  speed_factor: number
  auto_stretch: number
  status:
    | 'draft' | 'translated' | 'pending' | 'generating' | 'generated'
    | 'aligned' | 'too_long' | 'failed' | 'approved'
  approved: boolean
  emotion: string
  warning: string | null
  error_message: string | null
  slot_duration: number
  duration_diff: number | null
}

export interface Job {
  id: string
  project_id: string
  job_type: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
  progress: number
  log: string
  started_at: string | null
  completed_at: string | null
  error_message: string | null
  retry_count: number
  created_at: string | null
}

export interface Project {
  id: string
  name: string
  source_language: Language
  target_language: Language
  mode: Mode
  voice_style: string
  instructions: string
  status: ProjectStatus
  source_video_s3_key: string | null
  source_video_filename: string | null
  video_duration: number | null
  video_width: number | null
  video_height: number | null
  video_has_audio: boolean
  output_video_s3_key: string | null
  error_message: string | null
  bg_volume: number
  audio_version: number
  watermark_preview: boolean
  lipsync_status:
    | 'not_started' | 'running' | 'preview_ready' | 'failed'
    | 'approved' | 'skipped'
  lipsync_preview_key: string | null
  lipsync_window_start: number | null
  lipsync_window_end: number | null
  face_quality: string | null
  created_at: string | null
  updated_at: string | null
  segments: Segment[]
  jobs: Job[]
}

export interface ProjectSummary {
  id: string
  name: string
  source_language: Language
  target_language: Language
  mode: Mode
  status: ProjectStatus
  error_message: string | null
  created_at: string | null
  updated_at: string | null
  segment_count: number
  approved_count: number
}

export interface UploadTicket {
  mode: 'local' | 's3'
  url: string
  method: string
  key: string
  headers: Record<string, string>
  expires_in: number
}

export interface ExportItem {
  kind: string
  label: string
  group: string
  instant: boolean
  available: boolean
  url: string | null
  job_id: string | null
  job_status: string | null
  note: string | null
}
