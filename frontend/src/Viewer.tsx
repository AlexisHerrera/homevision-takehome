import { useState, type MouseEvent } from 'react'
import type { Box } from './api'
import { BoxDetail } from './BoxDetail'

interface Props {
  src: string
  boxes: Box[]
  showChecked: boolean
  showUnchecked: boolean
}

export interface Size {
  width: number
  height: number
}

interface Cursor {
  x: number
  y: number
  left: number
  top: number
  flip: boolean
}

export function Viewer({ src, boxes, showChecked, showUnchecked }: Props) {
  const [size, setSize] = useState<Size>()
  const [cursor, setCursor] = useState<Cursor>()
  const [hovered, setHovered] = useState<Box>()
  const [selected, setSelected] = useState<Box>()

  function onMouseMove(e: MouseEvent<SVGSVGElement>) {
    if (!size) return
    const rect = e.currentTarget.getBoundingClientRect()
    const left = e.clientX - rect.left
    const top = e.clientY - rect.top
    setCursor({
      x: Math.floor((left * size.width) / rect.width),
      y: Math.floor((top * size.height) / rect.height),
      left,
      top,
      flip: left > rect.width * 0.7,
    })
  }

  function onMouseLeave() {
    setCursor(undefined)
    setHovered(undefined)
  }

  return (
    <div className="viewer">
      <img
        src={src}
        alt="Uploaded document"
        onLoad={(e) => setSize({ width: e.currentTarget.naturalWidth, height: e.currentTarget.naturalHeight })}
      />
      {size && (
        <svg viewBox={`0 0 ${size.width} ${size.height}`} onMouseMove={onMouseMove} onMouseLeave={onMouseLeave}>
          {cursor && (
            <g className="crosshair">
              <line x1={cursor.x} x2={cursor.x} y1={0} y2={size.height} />
              <line x1={0} x2={size.width} y1={cursor.y} y2={cursor.y} />
            </g>
          )}
          {boxes
            .filter((b) => (b.is_checked ? showChecked : showUnchecked))
            .map((box) => {
              const [x1, y1, x2, y2] = box.bbox
              return (
                <rect
                  key={`${x1},${y1}`}
                  className={`${box.is_checked ? 'checked' : 'unchecked'}${box === selected ? ' selected' : ''}`}
                  x={x1}
                  y={y1}
                  width={x2 - x1}
                  height={y2 - y1}
                  onMouseEnter={() => setHovered(box)}
                  onMouseLeave={() => setHovered(undefined)}
                  onClick={() => setSelected(box)}
                />
              )
            })}
        </svg>
      )}
      {cursor && (
        <div
          className={`tooltip${cursor.flip ? ' flip' : ''}`}
          style={{ left: cursor.left + (cursor.flip ? -16 : 16), top: cursor.top + 16 }}
        >
          <div>
            x {cursor.x}, y {cursor.y}
          </div>
          {hovered && (
            <div className={hovered.is_checked ? 'checked' : 'unchecked'}>
              {hovered.is_checked ? 'Checked' : 'Unchecked'} [{hovered.bbox.join(', ')}] · click to inspect
            </div>
          )}
        </div>
      )}
      {selected && size && (
        <BoxDetail src={src} box={selected} image={size} onClose={() => setSelected(undefined)} />
      )}
    </div>
  )
}
