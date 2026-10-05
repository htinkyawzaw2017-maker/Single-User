import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from 'react'
import { withKey } from '../api/client'

export interface VideoPlayerHandle {
  seek: (seconds: number, play?: boolean) => void
  play: () => void
  pause: () => void
  get time(): number
}

interface Props {
  src: string
  muted?: boolean
  onTime?: (t: number) => void
  label?: string
}

/** Video player that reports playhead time (drives the editor timeline). */
const VideoPlayer = forwardRef<VideoPlayerHandle, Props>(function VideoPlayer(
  { src, muted, onTime, label },
  ref,
) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [mutedState, setMutedState] = useState(!!muted)

  useImperativeHandle(ref, () => ({
    seek(seconds: number, play = true) {
      const v = videoRef.current
      if (!v) return
      v.currentTime = seconds
      if (play) v.play().catch(() => {})
      else v.pause()
    },
    play() {
      videoRef.current?.play().catch(() => {})
    },
    pause() {
      videoRef.current?.pause()
    },
    get time() {
      return videoRef.current?.currentTime ?? 0
    },
  }))

  useEffect(() => {
    const v = videoRef.current
    if (!v || !onTime) return
    const handler = () => onTime(v.currentTime)
    v.addEventListener('timeupdate', handler)
    return () => v.removeEventListener('timeupdate', handler)
  }, [onTime])

  return (
    <div className="stack" style={{ gap: 6 }}>
      <video
        ref={videoRef}
        src={withKey(src)}
        controls
        muted={mutedState}
        preload="metadata"
      />
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <span className="faint" style={{ fontSize: 11.5 }}>
          {label}
        </span>
        <button
          className="btn small ghost"
          onClick={() => setMutedState((m) => !m)}
        >
          {mutedState ? '🔇 original muted' : '🔊 original audio on'}
        </button>
      </div>
    </div>
  )
})

export default VideoPlayer
