import { useEffect, useRef, useState } from 'react'
import { withKey } from '../api/client'

/** Small play button that plays an audio URL (one active at a time). */
let activeAudio: HTMLAudioElement | null = null

export default function AudioButton({
  src,
  title,
  disabled,
  onError,
}: {
  src: string | null
  title?: string
  disabled?: boolean
  onError?: (msg: string) => void
}) {
  const [playing, setPlaying] = useState(false)
  const ref = useRef<HTMLAudioElement | null>(null)

  useEffect(() => {
    return () => {
      ref.current?.pause()
    }
  }, [])

  const toggle = () => {
    if (!src) return
    if (playing) {
      ref.current?.pause()
      return
    }
    if (activeAudio && activeAudio !== ref.current) activeAudio.pause()
    if (!ref.current) {
      const a = new Audio(withKey(src))
      a.onended = () => setPlaying(false)
      a.onerror = () => {
        setPlaying(false)
        onError?.('audio unavailable')
      }
      ref.current = a
      activeAudio = a
    }
    ref.current.play().catch(() => setPlaying(false))
    setPlaying(true)
  }

  return (
    <button
      className="icon-btn"
      title={title || 'play'}
      disabled={disabled || !src}
      onClick={toggle}
      style={{ fontSize: 16, opacity: disabled || !src ? 0.35 : 1 }}
    >
      {playing ? '⏸' : '▶'}
    </button>
  )
}
