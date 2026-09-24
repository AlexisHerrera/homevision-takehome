import { useEffect, useRef, useState } from 'react'
import { detect, health, MAX_UPLOAD_BYTES, type DetectResponse } from './api'
import { Viewer } from './Viewer'

const SAMPLES = ['sample_1.png', 'sample_2.jpg', 'sample_3.png', 'sample_4.png']

type State =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'done'; result: DetectResponse; ms: number }
  | { status: 'error'; message: string }

async function timed<T>(promise: Promise<T>): Promise<[T, number]> {
  const start = performance.now()
  const value = await promise
  return [value, performance.now() - start]
}

export default function App() {
  const [image, setImage] = useState<{ url: string; name: string }>()
  const [state, setState] = useState<State>({ status: 'idle' })
  const [showChecked, setShowChecked] = useState(true)
  const [showUnchecked, setShowUnchecked] = useState(true)
  const [modelVersion, setModelVersion] = useState<string>()
  const [dragging, setDragging] = useState(false)
  const controller = useRef<AbortController>(null)

  useEffect(() => {
    health()
      .then((h) => setModelVersion(h.model_version))
      .catch(() => {})
  }, [])

  useEffect(() => () => image && URL.revokeObjectURL(image.url), [image])

  async function run(file: Blob, name: string) {
    controller.current?.abort()
    setImage({ url: URL.createObjectURL(file), name })
    if (file.size > MAX_UPLOAD_BYTES) {
      setState({ status: 'error', message: `File is over ${MAX_UPLOAD_BYTES / 1024 / 1024} MB.` })
      return
    }
    const current = new AbortController()
    controller.current = current
    setState({ status: 'loading' })
    try {
      const [result, ms] = await timed(detect(file, current.signal))
      setState({ status: 'done', result, ms })
    } catch (e) {
      if (!current.signal.aborted) setState({ status: 'error', message: (e as Error).message })
    }
  }

  async function runSample(name: string) {
    const response = await fetch(`/samples/${name}`)
    run(await response.blob(), name)
  }

  function onFiles(files: FileList | null) {
    const file = files?.[0]
    if (file) run(file, file.name)
  }

  function downloadJson(result: DetectResponse) {
    const url = URL.createObjectURL(new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' }))
    const a = document.createElement('a')
    a.href = url
    a.download = `${image?.name.replace(/\.\w+$/, '') ?? 'result'}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  const boxes = state.status === 'done' ? state.result.boxes : []
  const checked = boxes.filter((b) => b.is_checked).length

  return (
    <main>
      <header>
        <h1>Checkbox detection</h1>
        <p>
          Upload a page of an appraisal form (URAR 1004, 1004MC, ...) to find its checkboxes and whether each one is
          checked. Images are processed in memory and not stored.
        </p>
      </header>

      <section className="inputs">
        <label
          className={`dropzone${dragging ? ' dragging' : ''}`}
          onDragOver={(e) => {
            e.preventDefault()
            setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault()
            setDragging(false)
            onFiles(e.dataTransfer.files)
          }}
        >
          <input
            type="file"
            accept="image/png,image/jpeg,image/webp"
            onChange={(e) => {
              onFiles(e.target.files)
              e.target.value = ''
            }}
          />
          Drop an image here or <u>choose a file</u> (PNG, JPEG or WebP, up to 4 MB)
        </label>
        <div className="samples">
          Or try a sample:
          {SAMPLES.map((name, i) => (
            <button key={name} onClick={() => runSample(name)} disabled={state.status === 'loading'}>
              Sample {i + 1}
            </button>
          ))}
        </div>
      </section>

      {state.status === 'loading' && <p className="status">Detecting…</p>}
      {state.status === 'error' && <p className="status error">{state.message}</p>}
      {state.status === 'done' && (
        <section className="summary">
          <span>
            <strong>{boxes.length}</strong> boxes · <strong>{checked}</strong> checked ·{' '}
            <strong>{boxes.length - checked}</strong> unchecked · {Math.round(state.ms)} ms
          </span>
          <label className="checked">
            <input type="checkbox" checked={showChecked} onChange={(e) => setShowChecked(e.target.checked)} />
            Checked
          </label>
          <label className="unchecked">
            <input type="checkbox" checked={showUnchecked} onChange={(e) => setShowUnchecked(e.target.checked)} />
            Unchecked
          </label>
          <button onClick={() => downloadJson(state.result)}>Download JSON</button>
        </section>
      )}

      {image && (
        <Viewer
          key={image.url}
          src={image.url}
          boxes={boxes}
          showChecked={showChecked}
          showUnchecked={showUnchecked}
        />
      )}

      {state.status === 'done' && (
        <details>
          <summary>Response JSON</summary>
          <pre>{JSON.stringify(state.result, null, 2)}</pre>
        </details>
      )}

      <footer>
        <a href="/api/docs">API docs</a>
        {modelVersion && <span>Model {modelVersion}</span>}
      </footer>
    </main>
  )
}
