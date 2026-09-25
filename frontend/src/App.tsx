import { useEffect, useRef, useState } from 'react'
import { detect, health, MAX_UPLOAD_BYTES, type DetectResponse } from './api'
import { Viewer } from './Viewer'

const SAMPLES = ['sample_1.png', 'sample_2.jpg', 'sample_3.png', 'sample_4.png']

type State =
  | { status: 'idle' }
  | { status: 'loading'; phase: 'fetching' | 'detecting' }
  | { status: 'done'; result: DetectResponse; ms: number; serverMs?: number }
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

  async function run(name: string, getFile: (signal: AbortSignal) => Promise<Blob>) {
    controller.current?.abort()
    const current = new AbortController()
    controller.current = current
    setImage(undefined)
    setState({ status: 'loading', phase: 'fetching' })
    try {
      const file = await getFile(current.signal)
      setImage({ url: URL.createObjectURL(file), name })
      if (file.size > MAX_UPLOAD_BYTES) throw new Error(`File is over ${MAX_UPLOAD_BYTES / 1024 / 1024} MB.`)
      setState({ status: 'loading', phase: 'detecting' })
      const [{ result, serverMs }, ms] = await timed(detect(file, current.signal))
      setState({ status: 'done', result, ms, serverMs })
    } catch (e) {
      if (!current.signal.aborted) setState({ status: 'error', message: (e as Error).message })
    }
  }

  function runSample(name: string) {
    run(name, async (signal) => {
      const response = await fetch(`/samples/${name}`, { signal })
      if (!response.ok) throw new Error(`Could not load ${name} (${response.status})`)
      return response.blob()
    })
  }

  function onFiles(files: FileList | null) {
    const file = files?.[0]
    if (file) run(file.name, async () => file)
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

      {state.status === 'loading' && (
        <p className="status" role="status">
          <span className="spinner" />
          {state.phase === 'fetching' ? 'Loading sample…' : 'Detecting checkboxes…'}
        </p>
      )}
      {state.status === 'error' && <p className="status error">{state.message}</p>}
      {state.status === 'done' && (
        <section className="summary">
          <span>
            <strong>{boxes.length}</strong> boxes · <strong>{checked}</strong> checked ·{' '}
            <strong>{boxes.length - checked}</strong> unchecked ·{' '}
            {state.serverMs !== undefined && <>detection {Math.round(state.serverMs)} ms · </>}
            total {Math.round(state.ms)} ms
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
          scanning={state.status === 'loading'}
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
