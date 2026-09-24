import { useEffect, useRef } from 'react'
import type { Box } from './api'
import type { Size } from './Viewer'

const CROP_PX = 280
const GUTTER_PX = 44

interface Props {
  src: string
  box: Box
  image: Size
  onClose: () => void
}

export function BoxDetail({ src, box, image, onClose }: Props) {
  const ref = useRef<HTMLElement>(null)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    const onPointerDown = (e: PointerEvent) => !ref.current?.contains(e.target as Node) && onClose()
    window.addEventListener('keydown', onKey)
    window.addEventListener('pointerdown', onPointerDown)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('pointerdown', onPointerDown)
    }
  }, [onClose])

  const [x1, y1, x2, y2] = box.bbox
  const width = x2 - x1
  const height = y2 - y1
  const margin = Math.max(width, height)
  const cropX = x1 - margin
  const cropY = y1 - margin
  const cropW = width + 2 * margin
  const cropH = height + 2 * margin
  const k = cropW / CROP_PX
  const gutter = GUTTER_PX * k
  const state = box.is_checked ? 'checked' : 'unchecked'

  return (
    <aside className="detail" ref={ref}>
      <header>
        <strong className={state}>{box.is_checked ? 'Checked' : 'Unchecked'}</strong>
        <button onClick={onClose} aria-label="Close">
          ×
        </button>
      </header>
      <svg
        width={CROP_PX + GUTTER_PX}
        height={cropH / k + GUTTER_PX}
        viewBox={`${cropX - gutter} ${cropY - gutter} ${cropW + gutter} ${cropH + gutter}`}
        fontSize={11 * k}
      >
        <image href={src} width={image.width} height={image.height} />
        <rect className="gutter" x={cropX - gutter} y={cropY - gutter} width={cropW + gutter} height={gutter} />
        <rect className="gutter" x={cropX - gutter} y={cropY - gutter} width={gutter} height={cropH + gutter} />
        {[x1, x2].map((x) => (
          <g key={`x${x}`}>
            <line className="guide" x1={x} x2={x} y1={cropY - gutter * 0.3} y2={cropY + cropH} />
            <text x={x} y={cropY - gutter * 0.45} textAnchor="middle">
              {x}
            </text>
          </g>
        ))}
        {[y1, y2].map((y) => (
          <g key={`y${y}`}>
            <line className="guide" x1={cropX - gutter * 0.15} x2={cropX + cropW} y1={y} y2={y} />
            <text x={cropX - gutter * 0.2} y={y} textAnchor="end" dominantBaseline="middle">
              {y}
            </text>
          </g>
        ))}
        <rect className={`box ${state}`} x={x1} y={y1} width={width} height={height} />
      </svg>
      <p>
        bbox [{box.bbox.join(', ')}] · {width} × {height} px
      </p>
    </aside>
  )
}
