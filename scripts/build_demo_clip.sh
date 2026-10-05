#!/usr/bin/env bash
# Regenerate the bundled demo clip (14s, speech-burst audio pattern).
# Requires ffmpeg on PATH (or the backend venv's imageio-ffmpeg).
set -euo pipefail
cd "$(dirname "$0")/.."

FFM="$(command -v ffmpeg || true)"
if [ -z "$FFM" ] && [ -x backend/.venv/bin/python ]; then
  FFM="$(backend/.venv/bin/python -c 'import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())')"
fi
if [ -z "$FFM" ]; then
  echo "ffmpeg not found — install ffmpeg or run: python3 -m venv backend/.venv && backend/.venv/bin/pip install -r backend/requirements.txt" >&2
  exit 1
fi

mkdir -p backend/assets
"$FFM" -hide_banner -y \
  -f lavfi -i "testsrc2=s=712x400:r=24:d=14" \
  -f lavfi -i "aevalsrc='if(lt(mod(t,3.5),2.2), 0.4*sin(300*2*PI*t)+0.3*sin(450*2*PI*t)+0.2*sin(600*2*PI*t), 0)':s=22050:d=14" \
  -vf "format=yuv420p" \
  -c:v libx264 -preset veryfast -crf 26 -c:a aac -b:a 96k -shortest \
  -movflags +faststart backend/assets/demo_clip.mp4
echo "✓ backend/assets/demo_clip.mp4 regenerated"
