"""Pipeline runner — the background job workflow.

This is the local equivalent of the AWS Step Functions workflow
(see infrastructure/step-functions/pipeline.asl.json). It executes pipeline
steps in a small thread pool, persists every state transition to the
database (so refreshing the browser or closing it never loses progress),
supports per-step retry, per-segment voice regeneration, cancellation, and
detailed per-job logs.

Design rules from the spec:
  * one failed segment never restarts the whole project
  * every step logs to its Job row and can be retried independently
  * processing continues after the browser is closed
"""
from __future__ import annotations

import os
import shutil
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sqlalchemy.orm import Session

from . import states
from .config import settings
from .db import SessionLocal
from .models import Job, Project, Segment, new_id, utcnow
from .services import ffmpeg_env, rendering, subtitles
from .services.audio import (
    align_segment_file,
    build_dubbed_track,
    compute_alignment,
    mix_audio,
)
from .services.lipsync import FaceQualityError, get_lipsync
from .services.storage import get_storage
from .services.translation import get_translator
from .services.transcription import get_transcriber
from .services.tts import (
    default_voice_for,
    get_tts,
    get_voice,
)

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="sdm-worker")


# --------------------------------------------------------------------- utils
def enqueue(fn, *args, **kwargs):
    return _executor.submit(_safe_run, fn, *args, **kwargs)


def _safe_run(fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except Exception:
        traceback.print_exc()


def _check_cancel(db: Session, project_id: str) -> Project:
    db.commit()
    db.expire_all()
    project = db.get(Project, project_id)
    if project is None:
        raise states.StepCancelled("project deleted")
    if project.status == states.CANCELLED:
        raise states.StepCancelled("cancelled by user")
    return project


def get_or_create_job(db: Session, project: Project, job_type: str) -> Job:
    job = (
        db.query(Job)
        .filter(Job.project_id == project.id, Job.job_type == job_type)
        .first()
    )
    if not job:
        job = Job(id=new_id(), project_id=project.id, job_type=job_type,
                  status="pending", payload={})
        db.add(job)
        db.commit()
    return job


def _local_copy(key: str, dest: str) -> str:
    storage = get_storage()
    p = storage.local_path(key)
    if p:
        return p
    Path(dest).parent.mkdir(parents=True, exist_ok=True)
    return storage.download(key, dest)


def _output_key(project: Project, name: str) -> str:
    return f"projects/{project.id}/output/{name}"


# ------------------------------------------------------------- entry points
def start_pipeline(project_id: str, from_step: str, force_all: bool = False) -> None:
    """Kick off the pipeline from a given step in a worker thread."""
    if from_step not in states.STEP_ORDER:
        raise ValueError(f"unknown step: {from_step}")
    enqueue(run_pipeline, project_id, from_step, force_all)


def run_pipeline(project_id: str, from_step: str, force_all: bool = False) -> None:
    steps = states.STEP_ORDER[states.STEP_ORDER.index(from_step):]
    with SessionLocal() as db:
        project = db.get(Project, project_id)
        if project is None:
            return
        # mark lip_sync job as skipped when the feature is off
        if "lip_sync" in steps and not project.lipsync_enabled:
            job = get_or_create_job(db, project, "lip_sync")
            if job.status in ("pending",):
                job.status = "cancelled"
                job.append_log("skipped: lip-sync not enabled for this project")
                db.commit()

    for step in steps:
        if step == "lip_sync":
            with SessionLocal() as db:
                project = db.get(Project, project_id)
                if project and not project.lipsync_enabled:
                    continue  # skip silently, go to render
        with SessionLocal() as db:
            project = db.get(Project, project_id)
            if project is None or project.status == states.CANCELLED:
                return
            job = get_or_create_job(db, project, step)
            if job.status == "running":  # avoid double-start
                return
            job.status = "running"
            job.progress = 0
            job.error_message = None
            job.started_at = utcnow()
            job.completed_at = None
            job.append_log(f"step '{step}' started")
            project.status = states.STEP_RUNNING_STATUS[step]
            project.error_message = None
            project.touch()
            db.commit()

            try:
                impl = STEP_IMPLS[step]
                if step == "generate_voice":
                    impl(db, project, job, force_all)
                else:
                    impl(db, project, job)
                job.status = "completed"
                job.progress = 100
                job.completed_at = utcnow()
                job.append_log(f"step '{step}' completed")
                project.touch()
                db.commit()
                if step in _PAUSE_AFTER:
                    # user-review checkpoint: stop the pipeline here
                    project.status = _PAUSE_AFTER[step]
                    project.error_message = None
                    project.touch()
                    job.append_log(
                        f"paused at {project.status} — waiting for user review"
                    )
                    db.commit()
                    return
            except states.StepPause as pause:
                # lip-sync that degraded gracefully should still show a
                # failed job (retryable) without failing the whole project
                job_failed = (
                    step == "lip_sync"
                    and getattr(project, "lipsync_status", "") == "failed"
                )
                job.status = "failed" if job_failed else "completed"
                job.progress = 100 if not job_failed else job.progress
                job.completed_at = utcnow()
                job.append_log(f"step '{step}' paused — {pause.status}")
                project.status = pause.status
                project.error_message = None
                project.touch()
                db.commit()
                return
            except states.StepCancelled as cancel:
                job.status = "cancelled"
                job.completed_at = utcnow()
                job.append_log(f"step '{step}' cancelled: {cancel}")
                db.commit()
                return
            except Exception as exc:
                job.status = "failed"
                job.error_message = str(exc)[:2000]
                job.completed_at = utcnow()
                job.append_log("ERROR " + traceback.format_exc()[-3000:])
                project.status = states.FAILED
                project.error_message = f"{step}: {exc}"[:2000]
                project.touch()
                db.commit()
                return


# ------------------------------------------------------------------- steps
def step_validate(db: Session, project: Project, job: Job) -> None:
    if not project.source_video_s3_key:
        raise RuntimeError("No source video uploaded yet")
    storage = get_storage()
    if not storage.exists(project.source_video_s3_key):
        raise RuntimeError(
            f"Source video not found in storage ({project.source_video_s3_key})"
        )
    dest = os.path.join(ffmpeg_env.workdir("validate"), "source.tmp")
    local = _local_copy(project.source_video_s3_key, dest)
    info = ffmpeg_env.probe(local)
    if not info["has_video"]:
        raise RuntimeError("The uploaded file has no video stream")
    project.video_duration = round(info["duration"], 3)
    project.video_width = info["width"]
    project.video_height = info["height"]
    project.video_has_audio = info["has_audio"]
    job.append_log(
        f"video ok: {info['width']}x{info['height']}, "
        f"{info['duration']:.1f}s, audio={info['has_audio']}"
    )
    if not info["has_audio"]:
        job.append_log(
            "WARNING: no audio track in source — dubbing will create a new track"
        )
    db.commit()


def step_extract_audio(db: Session, project: Project, job: Job) -> None:
    if not ffmpeg_env.has_ffmpeg():
        raise RuntimeError("ffmpeg is not available on the server")
    tmp = ffmpeg_env.workdir("extract")
    local_video = _local_copy(
        project.source_video_s3_key, os.path.join(tmp, "source.mp4")
    )
    storage = get_storage()
    if project.video_has_audio:
        key48 = f"projects/{project.id}/audio/source_48k.wav"
        wav48 = os.path.join(tmp, "source_48k.wav")
        ffmpeg_env.extract_audio(local_video, wav48, 48000, mono=False)
        storage.put_file(wav48, key48)
        job.append_log("extracted 48kHz stereo audio")
        job.progress = 60
        db.commit()

        key16 = f"projects/{project.id}/audio/source_16k.wav"
        wav16 = os.path.join(tmp, "source_16k.wav")
        ffmpeg_env.extract_audio(local_video, wav16, 16000, mono=True)
        storage.put_file(wav16, key16)
        job.append_log("extracted 16kHz mono audio for transcription")
    else:
        job.append_log("source has no audio track — skipping extraction")
    job.progress = 100
    db.commit()


def step_transcribe(db: Session, project: Project, job: Job) -> None:
    transcriber = get_transcriber()
    job.append_log(f"transcription provider: {transcriber.provider}")
    tmp = ffmpeg_env.workdir("transcribe")

    audio_key = f"projects/{project.id}/audio/source_16k.wav"
    if get_storage().exists(audio_key):
        audio = _local_copy(audio_key, os.path.join(tmp, "a16k.wav"))
    elif project.video_has_audio:
        audio = _local_copy(
            f"projects/{project.id}/audio/source_48k.wav",
            os.path.join(tmp, "a48k.wav"),
        )
    else:
        audio = None

    if audio:
        drafts = transcriber.transcribe(audio, project.source_language,
                                        hint=project.name)
    else:
        job.append_log("no audio available — creating empty placeholder timeline")
        drafts = []

    if not drafts:
        # graceful fallback: evenly spaced placeholder segments
        from .services.transcription import SegmentDraft

        duration = project.video_duration or 30.0
        step = 8.0
        count = max(1, min(200, int(duration // step)))
        drafts = [
            SegmentDraft(
                start=round(i * step, 3),
                end=round(min((i + 1) * step - 0.4, duration), 3),
                text="",
                speaker="SPEAKER_00",
            )
            for i in range(count)
        ]

    # wipe previous segments (fresh transcription / retry)
    db.query(Segment).filter(Segment.project_id == project.id).delete()
    db.commit()

    default_voice = default_voice_for(project.target_language)
    for i, d in enumerate(drafts):
        seg = Segment(
            id=new_id(),
            project_id=project.id,
            segment_index=i,
            speaker_id=d.speaker or "SPEAKER_00",
            start_time=d.start,
            end_time=max(d.start + 0.2, d.end),
            source_text=d.text or "",
            target_text="",
            voice_id=default_voice,
            status="draft",
        )
        db.add(seg)
        job.progress = int((i + 1) / len(drafts) * 100)
        if i % 10 == 0:
            db.commit()
    job.append_log(f"created {len(drafts)} timestamped segments")
    db.commit()


def step_translate(db: Session, project: Project, job: Job) -> None:
    segments = (
        db.query(Segment)
        .filter(Segment.project_id == project.id)
        .order_by(Segment.segment_index)
        .all()
    )
    if not segments:
        raise RuntimeError("No segments to translate — transcribe first")
    translator = get_translator()
    job.append_log(f"translation provider: {translator.provider}")

    texts = [s.source_text or "" for s in segments]
    translated = translator.translate(
        texts, project.source_language, project.target_language,
        style=project.voice_style or "natural",
        instructions=project.instructions or "",
    )
    for seg, new_text in zip(segments, translated):
        seg.target_text = new_text or ""
        seg.status = "translated"
    job.progress = 100
    job.append_log(f"translated {len(segments)} segments "
                   f"({project.source_language} → {project.target_language})")
    project.touch()
    db.commit()


def _voice_segment(db: Session, project: Project, seg: Segment,
                   job: Job | None = None, log_prefix: str = "") -> None:
    """Generate + align the voice of ONE segment (shared by step & regen)."""
    seg.status = "generating"
    seg.error_message = None
    seg.warning = None
    db.commit()

    text = (seg.target_text or seg.source_text or "").strip()
    if not text:
        raise RuntimeError("segment has no text to speak")

    voice = get_voice(seg.voice_id or "")
    language = voice["language"] if voice else project.target_language

    tts = get_tts()
    result = tts.synthesize(
        text=text,
        voice_id=seg.voice_id or default_voice_for(language),
        speed=1.0,  # speed applied later via stretch, keeps raw audio natural
        language=language,
        emotion=seg.emotion or "neutral",
    )

    storage = get_storage()
    raw_key = f"projects/{project.id}/audio/raw_{seg.segment_index:04d}.{result.ext}"
    storage.put_bytes(raw_key, result.audio)
    seg.audio_s3_key = raw_key
    seg.audio_duration = result.duration

    # timing alignment
    alignment = compute_alignment(seg.slot_duration, result.duration,
                                  seg.speed_factor or 1.0)
    tmp = ffmpeg_env.workdir(f"seg{seg.id[:6]}")
    raw_local = _local_copy(raw_key, os.path.join(tmp, "raw." + result.ext))
    aligned_key = f"projects/{project.id}/audio/aligned_{seg.segment_index:04d}.wav"
    aligned_local = os.path.join(tmp, "aligned.wav")
    align_segment_file(raw_local, aligned_local,
                       alignment["auto_stretch"], seg.speed_factor or 1.0)
    storage.put_file(aligned_local, aligned_key)
    seg.aligned_audio_key = aligned_key
    seg.aligned_duration = round(ffmpeg_env.probe(aligned_local)["duration"], 3)
    seg.auto_stretch = alignment["auto_stretch"]
    seg.status = "aligned" if alignment["fits"] else "too_long"
    seg.warning = alignment["warning"]
    project.audio_version += 1
    project.touch()
    db.commit()
    if job:
        job.append_log(
            f"{log_prefix}segment #{seg.segment_index}: {result.duration:.2f}s raw → "
            f"{seg.aligned_duration:.2f}s aligned (slot {seg.slot_duration:.2f}s)"
            + (f" WARNING: {seg.warning}" if seg.warning else "")
        )


def step_generate_voice(db: Session, project: Project, job: Job,
                        force_all: bool = False) -> None:
    segments = (
        db.query(Segment)
        .filter(Segment.project_id == project.id)
        .order_by(Segment.segment_index)
        .all()
    )
    if not segments:
        raise RuntimeError("No segments — run transcription first")

    # assign default voices per speaker if missing
    speakers: dict[str, str] = {}
    for seg in segments:
        if not seg.voice_id:
            if seg.speaker_id not in speakers:
                gender = "female" if len(speakers) % 2 == 0 else "male"
                speakers[seg.speaker_id] = default_voice_for(
                    project.target_language, gender
                )
            seg.voice_id = speakers[seg.speaker_id]
    db.commit()

    todo = [
        s for s in segments
        if force_all or s.audio_s3_key is None or s.status == "failed"
    ]
    job.append_log(
        f"generating voice for {len(todo)}/{len(segments)} segments"
        + (" (force regenerate all)" if force_all else "")
    )
    job.progress = 1
    db.commit()

    failures = 0
    done = 0
    for seg in todo:
        project = _check_cancel(db, project.id)
        try:
            _voice_segment(db, project, seg, job, log_prefix="")
        except Exception as exc:
            seg.status = "failed"
            seg.error_message = str(exc)[:1000]
            failures += 1
            if job:
                job.append_log(
                    f"segment #{seg.segment_index} FAILED: {exc} "
                    "(other segments continue; you can regenerate this one)"
                )
            db.commit()
        done += 1
        job.progress = int(done / max(1, len(todo)) * 100)
        db.commit()

    if failures and not any(s.audio_s3_key for s in todo):
        raise RuntimeError(f"voice generation failed for all {failures} segments")
    if failures:
        job.append_log(
            f"{failures} segment(s) failed — continue reviewing others and "
            "regenerate the failed ones individually"
        )


def step_align_timing(db: Session, project: Project, job: Job) -> None:
    segments = (
        db.query(Segment)
        .filter(Segment.project_id == project.id)
        .order_by(Segment.segment_index)
        .all()
    )
    with_audio = [s for s in segments if s.audio_s3_key]
    if not with_audio:
        raise RuntimeError("No generated audio to align — generate voices first")
    tmp = ffmpeg_env.workdir("align")
    storage = get_storage()

    n = 0
    for seg in with_audio:
        alignment = compute_alignment(
            seg.slot_duration, seg.audio_duration or 0.0, seg.speed_factor or 1.0
        )
        raw_local = _local_copy(
            seg.audio_s3_key,
            os.path.join(tmp, f"raw_{seg.segment_index:04d}"),
        )
        aligned_key = f"projects/{project.id}/audio/aligned_{seg.segment_index:04d}.wav"
        aligned_local = os.path.join(tmp, f"aligned_{seg.segment_index:04d}.wav")
        align_segment_file(raw_local, aligned_local,
                           alignment["auto_stretch"], seg.speed_factor or 1.0)
        storage.put_file(aligned_local, aligned_key)
        seg.aligned_audio_key = aligned_key
        seg.aligned_duration = round(
            ffmpeg_env.probe(aligned_local)["duration"], 3
        )
        seg.auto_stretch = alignment["auto_stretch"]
        seg.status = "aligned" if alignment["fits"] else "too_long"
        seg.warning = alignment["warning"]
        n += 1
        job.progress = int(n / len(with_audio) * 100)
        if n % 5 == 0:
            db.commit()
    project.audio_version += 1
    project.touch()
    job.append_log(f"aligned {n} segments to original dialogue timing")
    db.commit()


def _ensure_mix(db: Session, project: Project) -> str:
    """Build (and cache) the full dubbed mix: dub track + original background."""
    storage = get_storage()
    if (
        project.mix_audio_key
        and project.mix_audio_version == project.audio_version
        and storage.exists(project.mix_audio_key)
    ):
        return project.mix_audio_key

    tmp = ffmpeg_env.workdir("mix")
    segments = (
        db.query(Segment)
        .filter(Segment.project_id == project.id)
        .order_by(Segment.segment_index)
        .all()
    )
    pieces = []
    for seg in segments:
        if seg.aligned_audio_key and seg.status != "failed":
            local = _local_copy(
                seg.aligned_audio_key,
                os.path.join(tmp, f"aligned_{seg.segment_index:04d}.wav"),
            )
            pieces.append(
                {"start": seg.start_time, "end": seg.end_time, "local_audio": local}
            )
    duration = project.video_duration or max(
        (s.end_time for s in segments), default=30.0
    )
    dub_track = os.path.join(tmp, "dub_track.wav")
    build_dubbed_track(pieces, duration, dub_track, tmp)

    original = None
    if project.video_has_audio:
        orig_key = f"projects/{project.id}/audio/source_48k.wav"
        if storage.exists(orig_key):
            original = _local_copy(orig_key, os.path.join(tmp, "orig.wav"))

    mix_wav = os.path.join(tmp, "mix.wav")
    mix_audio(original, dub_track, mix_wav, project.bg_volume or 0.15, tmp)

    mix_key = f"projects/{project.id}/audio/mix_v{project.audio_version}.wav"
    storage.put_file(mix_wav, mix_key)
    project.mix_audio_key = mix_key
    project.mix_audio_version = project.audio_version
    project.touch()
    db.commit()
    return mix_key


def _lipsync_window(db: Session, project: Project) -> tuple[float, float]:
    """Pick a 10–30s preview window around the first voiced segment(s)."""
    segments = (
        db.query(Segment)
        .filter(Segment.project_id == project.id)
        .order_by(Segment.segment_index)
        .all()
    )
    voiced = [s for s in segments if s.aligned_audio_key]
    if not voiced:
        raise RuntimeError("no voiced segments available for lip-sync preview")
    start = voiced[0].start_time
    end = start + 0.0
    for seg in voiced:
        if seg.start_time - start < settings.lipsync_preview_max_s:
            end = max(end, seg.end_time)
        else:
            break
    end = min(end, start + settings.lipsync_preview_max_s)
    if end - start < settings.lipsync_preview_min_s:
        end = start + settings.lipsync_preview_min_s
    end = min(end, project.video_duration or end)
    return round(start, 3), round(end, 3)


def step_lip_sync(db: Session, project: Project, job: Job) -> None:
    project.lipsync_status = "running"
    db.commit()
    tmp = ffmpeg_env.workdir("lipsync")
    storage = get_storage()

    start, end = _lipsync_window(db, project)
    project.lipsync_window_start, project.lipsync_window_end = start, end
    job.append_log(f"preview window: {start:.1f}s → {end:.1f}s")
    db.commit()

    local_video = _local_copy(
        project.source_video_s3_key, os.path.join(tmp, "source.mp4")
    )
    lipsync = get_lipsync()
    job.append_log(f"lip-sync provider: {lipsync.provider}")

    try:
        # 1) face quality validation
        quality = lipsync.check_face(local_video, start, end)
        project.face_quality = quality.get("message", "")
        job.append_log(
            f"face check: {quality.get('quality')} — {project.face_quality}"
        )
        db.commit()

        # 2) build window audio (dubbed mix slice)
        mix_key = _ensure_mix(db, project)
        mix_local = _local_copy(mix_key, os.path.join(tmp, "mix.wav"))
        window_audio = os.path.join(tmp, "window.wav")
        ffmpeg_env.run_ffmpeg(
            ["-ss", f"{start:.3f}", "-t", f"{end - start:.3f}", "-i", mix_local,
             "-acodec", "pcm_s16le", window_audio],
            label="lip-sync window audio",
        )

        # 3) render the preview clip
        preview_local = os.path.join(tmp, "preview.mp4")
        lipsync.render_preview(local_video, start, end, window_audio, preview_local)
        preview_key = f"projects/{project.id}/lipsync/preview.mp4"
        storage.put_file(preview_local, preview_key)
        project.lipsync_preview_key = preview_key
        project.lipsync_status = "preview_ready"
        project.touch()
        job.append_log(
            "lip-sync preview ready — review it before rendering the full output"
        )
        db.commit()
        raise states.StepPause(
            states.LIP_SYNCING,
            "lip-sync preview ready — awaiting user approval",
        )
    except FaceQualityError as exc:
        # graceful failure: keep the audio-dubbed pipeline fully available
        project.lipsync_status = "failed"
        project.face_quality = str(exc)
        project.touch()
        job.append_log(f"lip-sync FAILED (face quality): {exc}")
        job.error_message = str(exc)
        db.commit()
        raise states.StepPause(
            states.LIP_SYNCING,
            "lip-sync failed — user can retry or continue with audio-only",
        ) from exc
    except states.StepPause:
        raise
    except states.StepCancelled:
        raise
    except Exception as exc:
        # any other lip-sync error (GPU endpoint down, render error, …)
        # also degrades gracefully instead of failing the project
        project.lipsync_status = "failed"
        project.face_quality = f"lip-sync error: {exc}"
        project.touch()
        job.append_log(f"lip-sync FAILED: {exc}")
        job.error_message = str(exc)[:1000]
        db.commit()
        raise states.StepPause(
            states.LIP_SYNCING,
            "lip-sync failed — user can retry or continue with audio-only",
        ) from exc


def step_render(db: Session, project: Project, job: Job) -> None:
    if project.lipsync_enabled and project.lipsync_status == "preview_ready":
        project.lipsync_status = "approved"
        db.commit()
    tmp = ffmpeg_env.workdir("render")
    storage = get_storage()

    job.append_log("building dubbed audio mix…")
    mix_key = _ensure_mix(db, project)
    mix_local = _local_copy(mix_key, os.path.join(tmp, "mix.wav"))
    job.progress = 30
    db.commit()

    local_video = _local_copy(
        project.source_video_s3_key, os.path.join(tmp, "source.mp4")
    )
    out_local = os.path.join(tmp, "final.mp4")
    rendering.render_video(local_video, mix_local, out_local,
                           label="final render")
    out_key = _output_key(project, "final_1080.mp4")
    storage.put_file(out_local, out_key)
    project.output_video_s3_key = out_key
    job.progress = 80
    job.append_log(f"final video rendered → {out_key}")
    db.commit()

    # subtitle sidecars
    segments = [
        {
            "start": s.start_time,
            "end": s.end_time,
            "source_text": s.source_text,
            "target_text": s.target_text,
        }
        for s in db.query(Segment)
        .filter(Segment.project_id == project.id)
        .order_by(Segment.segment_index)
    ]
    lang = {True: "my", False: "en"}
    src_lang = project.source_language
    tgt_lang = project.target_language
    subs = {
        f"subs_{src_lang}.srt": subtitles.build_srt(segments, "source_text"),
        f"subs_{tgt_lang}.srt": subtitles.build_srt(segments, "target_text"),
        f"subs_{src_lang}.vtt": subtitles.build_vtt(segments, "source_text"),
        f"subs_{tgt_lang}.vtt": subtitles.build_vtt(segments, "target_text"),
    }
    for name, content in subs.items():
        if content.strip():
            storage.put_bytes(_output_key(project, name), content.encode("utf-8"))
    job.append_log("subtitle files written (SRT + VTT, source & target)")
    project.status = states.COMPLETED
    project.error_message = None
    project.touch()
    db.commit()


STEP_IMPLS = {
    "validate": step_validate,
    "extract_audio": step_extract_audio,
    "transcribe": step_transcribe,
    "translate": step_translate,
    "generate_voice": step_generate_voice,
    "align_timing": step_align_timing,
    "lip_sync": step_lip_sync,
    "render": step_render,
}

# pause-after map: steps that stop for user review
_PAUSE_AFTER = {
    "translate": states.AWAITING_USER_REVIEW,
    "align_timing": states.AWAITING_VOICE_APPROVAL,
}


# ------------------------------------------------------ segment regeneration
def regenerate_segment_voice(segment_id: str, job_id: str | None = None) -> None:
    """Regenerate exactly ONE segment's voice (never the whole project)."""
    with SessionLocal() as db:
        seg = db.get(Segment, segment_id)
        if not seg:
            return
        project = db.get(Project, seg.project_id)
        job = db.get(Job, job_id) if job_id else None
        if job:
            job.status = "running"
            job.progress = 10
            job.started_at = utcnow()
            job.append_log(f"regenerating segment #{seg.segment_index}")
            db.commit()
        try:
            _voice_segment(db, project, seg, job, log_prefix="regen: ")
            if job:
                job.status = "completed"
                job.progress = 100
                job.completed_at = utcnow()
                job.append_log("segment regenerated")
        except Exception as exc:
            seg.status = "failed"
            seg.error_message = str(exc)[:1000]
            if job:
                job.status = "failed"
                job.error_message = str(exc)[:2000]
                job.append_log("ERROR " + traceback.format_exc()[-2000:])
            db.commit()
        db.commit()


# ----------------------------------------------------------------- exports
def run_export(project_id: str, kind: str, job_id: str) -> None:
    with SessionLocal() as db:
        project = db.get(Project, project_id)
        job = db.get(Job, job_id)
        if not project or not job:
            return
        job.status = "running"
        job.started_at = utcnow()
        job.append_log(f"export '{kind}' started")
        db.commit()
        try:
            _export_impl(db, project, job, kind)
            job.status = "completed"
            job.progress = 100
            job.completed_at = utcnow()
            job.append_log(f"export '{kind}' completed")
            db.commit()
        except states.StepCancelled:
            job.status = "cancelled"
            db.commit()
        except Exception as exc:
            job.status = "failed"
            job.error_message = str(exc)[:2000]
            job.append_log("ERROR " + traceback.format_exc()[-2000:])
            db.commit()


def _export_impl(db: Session, project: Project, job: Job, kind: str) -> None:
    storage = get_storage()
    tmp = ffmpeg_env.workdir(f"export_{kind}")

    def segments_dicts() -> list[dict]:
        return [
            {"start": s.start_time, "end": s.end_time,
             "source_text": s.source_text, "target_text": s.target_text}
            for s in db.query(Segment)
            .filter(Segment.project_id == project.id)
            .order_by(Segment.segment_index)
        ]

    # -------- instant subtitle exports --------
    if kind.startswith(("srt_", "vtt_")):
        segs = segments_dicts()
        field = "source_text" if kind.endswith("source") else "target_text"
        ext, lang = kind.split("_")
        content = (
            subtitles.build_srt(segs, field)
            if ext == "srt" else subtitles.build_vtt(segs, field)
        )
        key = _output_key(project, f"subs_{lang}.{ext}")
        storage.put_bytes(key, content.encode("utf-8"))
        job.append_log(f"wrote {key}")
        return

    if not project.video_duration:
        raise RuntimeError("project has no source video")

    mix_key = _ensure_mix(db, project)
    mix_local = _local_copy(mix_key, os.path.join(tmp, "mix.wav"))
    local_video = _local_copy(
        project.source_video_s3_key, os.path.join(tmp, "source.mp4")
    )
    job.progress = 30
    db.commit()

    if kind == "audio_wav":
        key = _output_key(project, "dubbed_audio.wav")
        storage.put_file(mix_local, key)
        job.append_log(f"wrote {key}")
        return

    if kind == "audio_mp3":
        out = os.path.join(tmp, "dubbed_audio.mp3")
        rendering.export_audio(mix_local, out, "mp3")
        key = _output_key(project, "dubbed_audio.mp3")
        storage.put_file(out, key)
        job.append_log(f"wrote {key}")
        return

    if kind == "final_mp4":
        out = os.path.join(tmp, "final.mp4")
        rendering.render_video(local_video, mix_local, out, label="final_mp4")
        key = _output_key(project, "final_1080.mp4")
        storage.put_file(out, key)
        project.output_video_s3_key = key
        db.commit()
        return

    if kind == "final_mp4_720p":
        out = os.path.join(tmp, "preview720.mp4")
        notes: list[str] = []
        rendering.render_video(
            local_video, mix_local, out, height=720,
            watermark=project.watermark_preview, label="720p preview render",
            notes=notes,
        )
        name = ("final_720p_preview_wm.mp4" if project.watermark_preview
                else "final_720p_preview.mp4")
        key = _output_key(project, name)
        storage.put_file(out, key)
        for note in notes:
            job.append_log(f"note: {note}")
        return

    if kind == "final_mp4_subs":
        segs = segments_dicts()
        srt_local = os.path.join(tmp, "burn.srt")
        Path(srt_local).write_text(
            subtitles.build_srt(segs, "target_text"), encoding="utf-8"
        )
        out = os.path.join(tmp, "burned.mp4")
        rendering.render_video(
            local_video, mix_local, out, burn_srt=srt_local,
            label="burned-subtitle render",
        )
        key = _output_key(project, f"final_subs_{project.target_language}.mp4")
        storage.put_file(out, key)
        return

    if kind == "dual_audio_mp4":
        original = None
        orig_key = f"projects/{project.id}/audio/source_48k.wav"
        if project.video_has_audio and storage.exists(orig_key):
            original = _local_copy(orig_key, os.path.join(tmp, "orig.wav"))
        out = os.path.join(tmp, "dual.mp4")
        rendering.render_video(
            local_video, mix_local, out, extra_audio=original,
            label="dual-audio render",
        )
        key = _output_key(project, "final_dual_audio.mp4")
        storage.put_file(out, key)
        return

    raise RuntimeError(f"unknown export kind: {kind}")


# ------------------------------------------------------------- demo seeding
def seed_demo_project(project_id: str) -> None:
    """Attach the bundled demo clip to a project and start the pipeline."""
    with SessionLocal() as db:
        project = db.get(Project, project_id)
        if not project:
            return
        if not os.path.exists(settings.demo_clip_path):
            project.status = states.FAILED
            project.error_message = "demo clip not found on server"
            db.commit()
            return
        key = f"uploads/{project.id}/demo_clip.mp4"
        get_storage().put_file(settings.demo_clip_path, key)
        project.source_video_s3_key = key
        project.source_video_filename = "demo_clip.mp4"
        project.status = states.UPLOADED
        project.touch()
        db.commit()
    start_pipeline(project_id, "validate")
