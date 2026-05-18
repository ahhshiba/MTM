"use client"

import { useEffect, useMemo, useRef, useState } from "react"
import { PDFDocument } from "pdf-lib"
import ReactMarkdown from "react-markdown"
import rehypeRaw from "rehype-raw"
import remarkGfm from "remark-gfm"
import {
  Upload,
  Play,
  RefreshCw,
  ImageIcon,
  MessageSquare,
  FileCheck,
  ChevronLeft,
  ChevronRight,
  Lock,
  Unlock,
  Send,
  File,
  CheckCircle2,
  Loader2,
  AlertCircle,
} from "lucide-react"

const API_BASE = "/api/ocr"
const SESSION_STORAGE_KEY = "mtm_vlm_sessions"
const MODE_STORAGE_KEY = "mtm_pipeline_mode"

function formatBytes(bytes) {
  if (!bytes && bytes !== 0) return "-"
  const sizes = ["B", "KB", "MB", "GB"]
  let value = bytes
  let idx = 0
  while (value >= 1024 && idx < sizes.length - 1) {
    value /= 1024
    idx += 1
  }
  return `${value.toFixed(1)} ${sizes[idx]}`
}

function formatTimestamp(ts) {
  if (!ts) return "-"
  const date = new Date(ts * 1000)
  return date.toLocaleString()
}

function formatNumber(value) {
  if (value === null || value === undefined) return "-"
  return Number(value).toLocaleString()
}

async function readJson(response) {
  const text = await response.text()
  if (!text) return {}
  try {
    return JSON.parse(text)
  } catch {
    return {}
  }
}

function readSessionStore() {
  if (typeof window === "undefined") return {}
  try {
    const raw = window.localStorage.getItem(SESSION_STORAGE_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw)
    return typeof parsed === "object" && parsed ? parsed : {}
  } catch {
    return {}
  }
}

function writeSessionStore(map) {
  if (typeof window === "undefined") return
  window.localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(map))
}

function normalizeId(value) {
  return String(value)
}

export default function Home() {
  // Mode state: "developer" or "user" - starts with default to avoid SSR hydration mismatch
  const [mode, setMode] = useState("developer")
  const [modeLoaded, setModeLoaded] = useState(false)
  const isUserMode = mode === "user"

  const [stepIndex, setStepIndex] = useState(0)
  const [file, setFile] = useState(null)
  const [pdfUrl, setPdfUrl] = useState("")
  const [pdfPageCount, setPdfPageCount] = useState(null)
  const [pdfLoading, setPdfLoading] = useState(false)
  const [pdfError, setPdfError] = useState("")
  const fileInputRef = useRef(null)

  // VLM batch processing state for User Mode
  const [vlmBatchProgress, setVlmBatchProgress] = useState(null) // { total, completed, errors }

  const [job, setJob] = useState(null)
  const [status, setStatus] = useState(null)
  const [polling, setPolling] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")

  const [results, setResults] = useState(null)
  const [resultsLoading, setResultsLoading] = useState(false)
  const [resultsError, setResultsError] = useState("")
  const [activePageId, setActivePageId] = useState(null)
  const [artifactMarkdownById, setArtifactMarkdownById] = useState({})

  const [activeImageId, setActiveImageId] = useState(null)
  const [selectedImageIds, setSelectedImageIds] = useState([])
  const [sessionByImage, setSessionByImage] = useState({})
  const [messagesBySession, setMessagesBySession] = useState({})
  const [sessionLocks, setSessionLocks] = useState({})
  const [tokensBySession, setTokensBySession] = useState({})
  const [vlmInput, setVlmInput] = useState("")
  const [vlmBusy, setVlmBusy] = useState(false)
  const [vlmError, setVlmError] = useState("")
  const [sendingVlm, setSendingVlm] = useState(false)
  const [reviewPageIndex, setReviewPageIndex] = useState(0)

  const merged = status || job
  const normalizedStatus = (merged?.status || "").toLowerCase()
  const normalizedStep = (merged?.step || "").toLowerCase()
  const progress = typeof merged?.progress === "number" ? merged.progress : 0

  const ocrDone =
    ["succeeded", "done", "completed", "finished"].includes(normalizedStatus) ||
    normalizedStep === "done" ||
    progress >= 1
  const ocrFailed = ["failed", "error"].includes(normalizedStatus)

  const pages = results?.pages || []
  const images = useMemo(() => pages.flatMap((page) => page.images?.map((img) => ({ ...img, page })) || []), [pages])

  const allSteps = useMemo(
    () => [
      {
        title: "Upload PDF",
        note: "Choose a file and preview basic metadata before starting OCR.",
        icon: Upload,
        originalIndex: 0,
      },
      {
        title: "Start OCR",
        note: "Create a local job and send the PDF to the Lab OCR API.",
        icon: Play,
        originalIndex: 1,
      },
      {
        title: "OCR Progress",
        note: "Track status, then preview Markdown and page images when done.",
        icon: RefreshCw,
        originalIndex: 2,
      },
      {
        title: "Select Images",
        note: "Pick images to send to Gemini, then generate VLM sessions in batch.",
        icon: ImageIcon,
        originalIndex: 3,
      },
      {
        title: "VLM Chat",
        note: "Review each image session, chat, and lock when confirmed.",
        icon: MessageSquare,
        originalIndex: 4,
      },
      // User mode only: Processing step (before Final Review)
      {
        title: "Processing",
        note: "Processing OCR and VLM image analysis...",
        icon: Loader2,
        originalIndex: 100,
      },
      {
        title: "Final Review",
        note: "Review each page with OCR Markdown and locked VLM notes.",
        icon: FileCheck,
        originalIndex: 5,
      },
    ],
    [],
  )

  // Filtered steps based on mode
  const steps = useMemo(() => {
    if (isUserMode) {
      // User mode: Upload -> Processing -> Final Review
      return allSteps.filter((s) => s.originalIndex === 0 || s.originalIndex === 100 || s.originalIndex === 5)
    }
    // Developer mode: exclude Processing step
    return allSteps.filter((s) => s.originalIndex < 100)
  }, [allSteps, isUserMode])

  const selectedImageSet = useMemo(() => new Set(selectedImageIds), [selectedImageIds])
  const selectedImages = useMemo(
    () => images.filter((image) => selectedImageSet.has(normalizeId(image.image_id))),
    [images, selectedImageSet],
  )

  const activeImage = images.find((image) => normalizeId(image.image_id) === activeImageId)
  const activeSessionId = activeImageId ? sessionByImage[activeImageId] : null
  const activeMessages = activeSessionId ? messagesBySession[activeSessionId] || [] : []
  const activeLocked = activeSessionId ? sessionLocks[activeSessionId] === true : false

  const vlmReady = selectedImageIds.length > 0 && selectedImageIds.every((imageId) => Boolean(sessionByImage[imageId]))
  const allSessionsConfirmed =
    vlmReady && selectedImageIds.every((imageId) => sessionLocks[sessionByImage[imageId]] === true)

  const currentStep = steps[stepIndex] || steps[0]

  // Handle mode change - reset to step 0 and save preference
  const handleModeChange = (newMode) => {
    setMode(newMode)
    setStepIndex(0)
    if (typeof window !== "undefined") {
      window.localStorage.setItem(MODE_STORAGE_KEY, newMode)
    }
  }

  const getSessionTokenInfo = (sessionId) => {
    if (!sessionId) return null
    return tokensBySession[sessionId] || null
  }

  const getSessionTokens = (sessionId) => {
    const info = getSessionTokenInfo(sessionId)
    if (!info || typeof info.total_tokens !== "number") return null
    return info.total_tokens
  }

  const overallTokenMeta = useMemo(() => {
    let total = 0
    let unknown = false
    selectedImageIds.forEach((imageId) => {
      const sessionId = sessionByImage[imageId]
      if (!sessionId) {
        unknown = true
        return
      }
      const sessionTotal = getSessionTokens(sessionId)
      if (sessionTotal === null) {
        unknown = true
        return
      }
      total += sessionTotal
    })
    return { total, unknown }
  }, [selectedImageIds, sessionByImage, tokensBySession])

  const resetWorkflow = ({ keepFile = false } = {}) => {
    if (!keepFile) {
      setFile(null)
      setPdfUrl("")
      setPdfPageCount(null)
      setPdfError("")
      if (fileInputRef.current) {
        fileInputRef.current.value = ""
      }
    }
    setJob(null)
    setStatus(null)
    setPolling(false)
    setBusy(false)
    setError("")
    setResults(null)
    setResultsLoading(false)
    setResultsError("")
    setActivePageId(null)
    setArtifactMarkdownById({})
    setActiveImageId(null)
    setSelectedImageIds([])
    setSessionByImage({})
    writeSessionStore({})
    setMessagesBySession({})
    setSessionLocks({})
    setTokensBySession({})
    setVlmInput("")
    setVlmBusy(false)
    setVlmError("")
    setSendingVlm(false)
    setReviewPageIndex(0)
    setStepIndex(0)
  }

  const handleFileChange = (event) => {
    const selected = event.target.files?.[0] || null
    resetWorkflow({ keepFile: true })
    setFile(selected)
  }

  const handleStartOcr = async () => {
    if (!file || busy) return
    setBusy(true)
    setError("")
    setResults(null)
    setResultsError("")
    setSelectedImageIds([])
    setSessionByImage({})
    writeSessionStore({})
    setMessagesBySession({})
    setSessionLocks({})
    setVlmError("")
    try {
      const formData = new FormData()
      formData.append("file", file)
      const resp = await fetch(`${API_BASE}/jobs`, {
        method: "POST",
        body: formData,
      })
      const data = await readJson(resp)
      if (!resp.ok) {
        setError(data?.detail || "Upload failed.")
        setBusy(false)
        return
      }
      if (!data?.local_job_id || data.local_job_id === "undefined") {
        setError("Missing local_job_id from server response.")
        setBusy(false)
        return
      }
      setJob(data)
      setStatus(data)
      setPolling(true)
      setStepIndex(2)
    } catch (err) {
      setError("Upload failed. Check server logs.")
    } finally {
      setBusy(false)
    }
  }

  // Batch VLM session creation for User Mode
  const createBatchVlmSessions = async (imageIds) => {
    if (!imageIds.length) return { success: true, sessions: [], errors: [] }

    setVlmBatchProgress({ total: imageIds.length, completed: 0, errors: [] })
    setSendingVlm(true)
    setVlmError("")

    try {
      const resp = await fetch(`${API_BASE}/vlm/sessions/batch`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ image_ids: imageIds.map(String) }),
      })
      const data = await readJson(resp)

      if (!resp.ok) {
        setVlmError(data?.detail || "Batch VLM session creation failed.")
        setVlmBatchProgress((prev) => ({ ...prev, errors: [{ error: data?.detail }] }))
        setSendingVlm(false)
        return { success: false, sessions: [], errors: [{ error: data?.detail }] }
      }

      const sessions = data.sessions || []
      const errors = data.errors || []

      // Update session mappings and auto-lock for User mode
      for (const session of sessions) {
        const imageId = session.image_id
        const sessionId = session.session_id
        setSessionByImage((prev) => {
          const next = { ...prev, [imageId]: sessionId }
          writeSessionStore(next)
          return next
        })
        setSessionLocks((prev) => ({ ...prev, [sessionId]: true }))
      }

      setVlmBatchProgress({ total: imageIds.length, completed: sessions.length, errors })

      // Load tokens and messages for created sessions
      const sessionIds = sessions.map((s) => s.session_id)
      if (sessionIds.length) {
        await loadTokensForSessions(sessionIds)
        await Promise.all(sessionIds.map((sid) => loadSessionMessages(sid)))
      }

      setSendingVlm(false)
      return { success: errors.length === 0, sessions, errors }
    } catch (err) {
      setVlmError("Batch VLM session creation failed.")
      setVlmBatchProgress((prev) => ({ ...prev, errors: [{ error: String(err) }] }))
      setSendingVlm(false)
      return { success: false, sessions: [], errors: [{ error: String(err) }] }
    }
  }

  const handleRefresh = async () => {
    if (!job?.local_job_id || job.local_job_id === "undefined") return
    setError("")
    try {
      const resp = await fetch(`${API_BASE}/jobs/${job.local_job_id}`)
      const data = await readJson(resp)
      if (!resp.ok) {
        setError(data?.detail || "Failed to fetch status.")
        return
      }
      setStatus(data)
    } catch (err) {
      setError("Network error while fetching status.")
    }
  }

  const ensureArtifactMarkdown = async (artifactId) => {
    if (!artifactId || Object.prototype.hasOwnProperty.call(artifactMarkdownById, artifactId)) return
    try {
      const resp = await fetch(`${API_BASE}/results/artifacts/${artifactId}/result_md`)
      const text = await resp.text()
      setArtifactMarkdownById((prev) => ({
        ...prev,
        [artifactId]: resp.ok ? text : "",
      }))
    } catch {
      setArtifactMarkdownById((prev) => ({
        ...prev,
        [artifactId]: "",
      }))
    }
  }

  const loadSessionMessages = async (sessionId) => {
    if (!sessionId) return
    try {
      const resp = await fetch(`${API_BASE}/vlm/sessions/${sessionId}`)
      const data = await readJson(resp)
      if (!resp.ok) return
      setMessagesBySession((prev) => ({ ...prev, [sessionId]: data.messages || [] }))
    } catch {
      return
    }
  }

  const loadSessionTokens = async (sessionId) => {
    if (!sessionId) return
    try {
      const resp = await fetch(`${API_BASE}/vlm/sessions/${sessionId}/tokens`)
      const data = await readJson(resp)
      if (!resp.ok) return
      setTokensBySession((prev) => ({
        ...prev,
        [sessionId]: {
          prompt_tokens: data.prompt_tokens,
          candidate_tokens: data.candidate_tokens,
          total_tokens: data.total_tokens,
        },
      }))
    } catch {
      return
    }
  }

  const loadTokensForSessions = async (sessionIds) => {
    if (!sessionIds.length) return
    try {
      const resp = await fetch(`${API_BASE}/vlm/tokens`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ session_ids: sessionIds }),
      })
      const data = await readJson(resp)
      if (!resp.ok || !data.sessions) return
      setTokensBySession((prev) => {
        const next = { ...prev }
        data.sessions.forEach((session) => {
          next[session.session_id] = {
            prompt_tokens: session.prompt_tokens,
            candidate_tokens: session.candidate_tokens,
            total_tokens: session.total_tokens,
          }
        })
        return next
      })
    } catch {
      return
    }
  }

  const ensureVlmSessions = async () => {
    if (!selectedImageIds.length) {
      setVlmError("Select at least one image before sending to VLM.")
      return false
    }
    setSendingVlm(true)
    setVlmError("")
    for (const imageId of selectedImageIds) {
      if (sessionByImage[imageId]) continue
      try {
        const resp = await fetch(`${API_BASE}/vlm/sessions`, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ image_id: String(imageId) }),
        })
        const data = await readJson(resp)
        if (!resp.ok || !data.session_id) {
          setVlmError(data?.detail || "Failed to create VLM session.")
          setSendingVlm(false)
          return false
        }
        const sessionId = data.session_id
        setSessionByImage((prev) => {
          const next = { ...prev, [imageId]: sessionId }
          writeSessionStore(next)
          return next
        })
        if (data.messages) {
          setMessagesBySession((prev) => ({ ...prev, [sessionId]: data.messages }))
        }
        await loadSessionMessages(sessionId)
        await loadSessionTokens(sessionId)
      } catch {
        setVlmError("Failed to create VLM session.")
        setSendingVlm(false)
        return false
      }
    }
    setSendingVlm(false)
    return true
  }

  const handleToggleImageSelection = (imageId) => {
    setSelectedImageIds((prev) => {
      if (prev.includes(imageId)) {
        return prev.filter((item) => item !== imageId)
      }
      return [...prev, imageId]
    })
  }

  const handleSelectSessionImage = async (imageId) => {
    setActiveImageId(imageId)
    const sessionId = sessionByImage[imageId]
    if (sessionId) {
      await loadSessionMessages(sessionId)
      await loadSessionTokens(sessionId)
    }
  }

  const handleSendMessage = async () => {
    if (!activeSessionId || !vlmInput.trim() || vlmBusy || activeLocked) return
    setVlmBusy(true)
    try {
      const resp = await fetch(`${API_BASE}/vlm/sessions/${activeSessionId}/messages`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ role: "user", content: vlmInput.trim() }),
      })
      const data = await readJson(resp)
      if (resp.ok && data.messages) {
        setMessagesBySession((prev) => ({ ...prev, [activeSessionId]: data.messages }))
      }
      setVlmInput("")
      await loadSessionMessages(activeSessionId)
      await loadSessionTokens(activeSessionId)
    } finally {
      setVlmBusy(false)
    }
  }

  const handleLockSession = (locked) => {
    if (!activeSessionId) return
    setSessionLocks((prev) => ({ ...prev, [activeSessionId]: locked }))
  }

  const handlePrev = () => {
    setStepIndex((prev) => Math.max(prev - 1, 0))
  }

  const handleNext = async () => {
    const lastIndex = steps.length - 1
    if (stepIndex >= lastIndex) return

    const currentOriginalIndex = currentStep.originalIndex

    // User mode: Navigate from Upload to Processing step
    if (isUserMode && currentOriginalIndex === 0 && file) {
      setStepIndex((prev) => Math.min(prev + 1, lastIndex))
      return
    }

    // Developer mode checks
    if (currentOriginalIndex === 3 && !vlmReady) {
      const ok = await ensureVlmSessions()
      if (!ok) return
    }
    if (currentOriginalIndex === 4 && !allSessionsConfirmed) {
      setVlmError("Confirm all sessions before moving on.")
      return
    }
    setStepIndex((prev) => Math.min(prev + 1, lastIndex))
  }

  const canGoNext = useMemo(() => {
    const idx = currentStep?.originalIndex
    switch (idx) {
      case 0:
        return Boolean(file)
      case 1:
        return Boolean(job?.local_job_id)
      case 2:
        return Boolean(ocrDone && results)
      case 3:
        return selectedImageIds.length > 0 && !sendingVlm
      case 4:
        return allSessionsConfirmed
      case 5:
        return false // Final step
      case 100: {
        // Processing step: require all processing complete
        const vlmComplete = vlmBatchProgress &&
          vlmBatchProgress.completed === vlmBatchProgress.total &&
          vlmBatchProgress.total > 0 &&
          vlmBatchProgress.errors.length === 0
        return Boolean(ocrDone && results && vlmComplete && !sendingVlm)
      }
      default:
        return false
    }
  }, [currentStep?.originalIndex, file, job, ocrDone, results, selectedImageIds.length, allSessionsConfirmed, sendingVlm, vlmBatchProgress])

  useEffect(() => {
    let cancelled = false
    if (!file) {
      setPdfUrl("")
      setPdfPageCount(null)
      setPdfError("")
      return undefined
    }
    const url = URL.createObjectURL(file)
    setPdfUrl(url)
    setPdfPageCount(null)
    setPdfError("")
    setPdfLoading(true)
    const parsePdf = async () => {
      try {
        const arrayBuffer = await file.arrayBuffer()
        const doc = await PDFDocument.load(arrayBuffer, { ignoreEncryption: true })
        if (!cancelled) {
          setPdfPageCount(doc.getPageCount())
          setPdfLoading(false)
        }
      } catch (err) {
        if (!cancelled) {
          setPdfError("Unable to parse PDF pages.")
          setPdfLoading(false)
        }
      }
    }
    parsePdf()
    return () => {
      cancelled = true
      URL.revokeObjectURL(url)
    }
  }, [file])

  useEffect(() => {
    if (!polling || !job?.local_job_id || job.local_job_id === "undefined") return undefined

    const tick = async () => {
      try {
        const resp = await fetch(`${API_BASE}/jobs/${job.local_job_id}`)
        const data = await readJson(resp)
        if (!resp.ok) {
          setError(data?.detail || "Failed to fetch status.")
          setPolling(false)
          return
        }
        setStatus(data)
        const done =
          ["succeeded", "done", "completed", "failed", "error", "canceled"].includes(
            (data?.status || "").toLowerCase(),
          ) || data?.progress >= 1
        if (done) {
          setPolling(false)
        }
      } catch {
        setError("Network error while polling.")
        setPolling(false)
      }
    }

    tick()
    const timer = setInterval(tick, 2000)
    return () => clearInterval(timer)
  }, [polling, job?.local_job_id])

  useEffect(() => {
    const cached = readSessionStore()
    setSessionByImage(cached)
  }, [])

  // Load mode from localStorage after mount to avoid SSR hydration mismatch
  useEffect(() => {
    const savedMode = window.localStorage.getItem(MODE_STORAGE_KEY)
    if (savedMode && (savedMode === "developer" || savedMode === "user")) {
      setMode(savedMode)
    }
    setModeLoaded(true)
  }, [])

  useEffect(() => {
    if (!ocrDone || !job?.local_job_id || job.local_job_id === "undefined" || resultsLoading || results) return

    const loadResults = async () => {
      setResultsLoading(true)
      setResultsError("")
      try {
        const resp = await fetch(`${API_BASE}/jobs/${job.local_job_id}/results`)
        const data = await readJson(resp)
        if (!resp.ok) {
          setResultsError(data?.detail || "Failed to fetch OCR results.")
          setResultsLoading(false)
          return
        }
        setResults(data)
        if (data?.pages?.length) {
          setActivePageId(data.pages[0].page_id)
        }
      } catch {
        setResultsError("Network error while fetching results.")
      } finally {
        setResultsLoading(false)
      }
    }

    loadResults()
  }, [ocrDone, job?.local_job_id, resultsLoading, results])

  // User Mode: Auto-start OCR when entering Processing step (originalIndex 100)
  useEffect(() => {
    if (!isUserMode || currentStep?.originalIndex !== 100) return
    if (job || busy) return // Already started or starting
    if (!file) return

    handleStartOcr()
  }, [isUserMode, currentStep?.originalIndex, job, busy, file])

  // User Mode: Auto-process all images when OCR results are loaded
  useEffect(() => {
    if (!isUserMode || !results) return
    if (currentStep?.originalIndex !== 100) return
    if (!images.length || sendingVlm || selectedImageIds.length > 0) return

    const autoProcessImages = async () => {
      const allImageIds = images.map((img) => normalizeId(img.image_id))
      setSelectedImageIds(allImageIds)
      await createBatchVlmSessions(allImageIds)
    }

    autoProcessImages()
  }, [isUserMode, currentStep?.originalIndex, results, images.length, sendingVlm, selectedImageIds.length])

  useEffect(() => {
    if (!pages.length) return
    if (!activePageId) {
      setActivePageId(pages[0].page_id)
    }
  }, [pages, activePageId])

  useEffect(() => {
    const page = pages.find((item) => item.page_id === activePageId)
    const artifactId = page?.artifact?.artifact_id
    if (artifactId) {
      ensureArtifactMarkdown(artifactId)
    }
  }, [activePageId, pages])

  useEffect(() => {
    if (!pages.length) return
    if (reviewPageIndex >= pages.length) {
      setReviewPageIndex(0)
    }
  }, [pages, reviewPageIndex])

  useEffect(() => {
    const page = pages[reviewPageIndex]
    const artifactId = page?.artifact?.artifact_id
    if (artifactId) {
      ensureArtifactMarkdown(artifactId)
    }
  }, [reviewPageIndex, pages])

  useEffect(() => {
    if (stepIndex !== 4) return
    if (!selectedImageIds.length) return
    if (!activeImageId || !selectedImageSet.has(activeImageId)) {
      setActiveImageId(selectedImageIds[0])
    }
  }, [stepIndex, selectedImageIds, activeImageId, selectedImageSet])

  useEffect(() => {
    if (stepIndex !== 4) return
    const sessionIds = selectedImageIds.map((imageId) => sessionByImage[imageId]).filter(Boolean)
    if (!sessionIds.length) return
    loadTokensForSessions(sessionIds)
  }, [stepIndex, selectedImageIds, sessionByImage])

  useEffect(() => {
    if (!activeSessionId) return
    if (!messagesBySession[activeSessionId]) {
      loadSessionMessages(activeSessionId)
    }
    if (!tokensBySession[activeSessionId]) {
      loadSessionTokens(activeSessionId)
    }
  }, [activeSessionId, messagesBySession, tokensBySession])

  useEffect(() => {
    if (stepIndex !== 5) return
    selectedImageIds.forEach((imageId) => {
      const sessionId = sessionByImage[imageId]
      if (sessionId && !messagesBySession[sessionId]) {
        loadSessionMessages(sessionId)
      }
    })
  }, [stepIndex, selectedImageIds, sessionByImage, messagesBySession])

  useEffect(() => {
    if (stepIndex !== 5) return
    const sessionIds = selectedImageIds.map((imageId) => sessionByImage[imageId]).filter(Boolean)
    if (!sessionIds.length) return
    loadTokensForSessions(sessionIds)
  }, [stepIndex, selectedImageIds, sessionByImage])

  const activePage = pages.find((page) => page.page_id === activePageId)
  const activeArtifactId = activePage?.artifact?.artifact_id
  const activeMarkdown = activeArtifactId ? artifactMarkdownById[activeArtifactId] : ""
  const activeRenderUrl = activePage?.render_image_url
    ? `${API_BASE}/results/pages/${activePage.page_id}/render_image`
    : activeArtifactId
      ? `${API_BASE}/results/artifacts/${activeArtifactId}/vis_image`
      : null

  const reviewPage = pages[reviewPageIndex]
  const reviewArtifactId = reviewPage?.artifact?.artifact_id
  const reviewMarkdown = reviewArtifactId ? artifactMarkdownById[reviewArtifactId] : ""
  const reviewRenderUrl = reviewPage?.render_image_url
    ? `${API_BASE}/results/pages/${reviewPage.page_id}/render_image`
    : reviewArtifactId
      ? `${API_BASE}/results/artifacts/${reviewArtifactId}/vis_image`
      : null

  const stepStatus = (index) => {
    if (index < stepIndex) return "completed"
    if (index === stepIndex) return "active"
    return "inactive"
  }

  return (
    <div className="app-layout">
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="sidebar-header">
          <div className="sidebar-logo">
            <div className="sidebar-logo-icon">M</div>
            <span className="sidebar-logo-text">MTM Pipeline POC</span>
          </div>
        </div>

        {/* Mode Toggle */}
        <div className="mode-toggle">
          <span className={`mode-toggle-label ${!isUserMode ? 'active' : ''}`}>開發者</span>
          <button
            type="button"
            className={`mode-toggle-switch ${isUserMode ? 'active' : ''}`}
            onClick={() => handleModeChange(isUserMode ? "developer" : "user")}
            title={isUserMode ? "切換到開發者模式" : "切換到使用者模式"}
          />
          <span className={`mode-toggle-label ${isUserMode ? 'active' : ''}`}>使用者</span>
        </div>

        <nav className="sidebar-nav">
          <div className="nav-section-title">Pipeline Steps</div>
          {steps.map((step, index) => {
            const status = stepStatus(index)
            return (
              <button
                key={step.title}
                className={`nav-item ${status}`}
                onClick={() => setStepIndex(index)}
                type="button"
              >
                <span className={`nav-item-number`}>
                  {status === "completed" ? <CheckCircle2 size={14} /> : index + 1}
                </span>
                <span className="nav-item-label">{step.title}</span>
              </button>
            )
          })}
        </nav>

        <div className="sidebar-footer">Document OCR &amp; VLM Pipeline Console</div>
      </aside>

      {/* Main Content */}
      <main className="main-content">
        <header className="main-header">
          <div className="main-header-title">
            <h1>{currentStep.title}</h1>
            <p>{currentStep.note}</p>
          </div>
          <div className="main-header-actions">
            <button className="btn btn-secondary" onClick={handlePrev} disabled={stepIndex === 0}>
              <ChevronLeft size={16} />
              Previous
            </button>
            {stepIndex < steps.length - 1 && (
              <button className="btn btn-primary" onClick={handleNext} disabled={!canGoNext}>
                Next
                <ChevronRight size={16} />
              </button>
            )}
          </div>
        </header>

        <div className="main-workspace">
          {/* Step 0: Upload PDF */}
          {currentStep.originalIndex === 0 && (
            <div className="workspace-grid workspace-grid-2">
              <div className="card">
                <div className="card-header">
                  <h2>
                    <Upload size={18} className="card-header-icon" />
                    Upload Document
                  </h2>
                </div>
                <div className="card-body">
                  <label className="upload-zone">
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept="application/pdf"
                      onClick={(event) => {
                        event.currentTarget.value = ""
                      }}
                      onChange={handleFileChange}
                    />
                    <Upload className="upload-zone-icon" />
                    <div className="upload-zone-title">Drop your PDF here or click to browse</div>
                    <div className="upload-zone-subtitle">Supports PDF documents up to 10MB</div>
                  </label>

                  {file && (
                    <div className="file-info">
                      <div className="file-info-icon">
                        <File size={20} />
                      </div>
                      <div className="file-info-details">
                        <div className="file-info-name">{file.name}</div>
                        <div className="file-info-meta">
                          {formatBytes(file.size)} •{" "}
                          {pdfLoading ? "Loading..." : pdfPageCount ? `${pdfPageCount} pages` : "-"}
                        </div>
                      </div>
                      <button className="btn btn-ghost btn-icon" onClick={() => resetWorkflow()} title="Remove file">
                        ×
                      </button>
                    </div>
                  )}

                  {pdfError && (
                    <div className="text-error text-sm" style={{ marginTop: 12 }}>
                      <AlertCircle size={14} style={{ display: "inline", marginRight: 4 }} />
                      {pdfError}
                    </div>
                  )}
                </div>
              </div>

              <div className="card">
                <div className="card-header">
                  <h2>
                    <File size={18} className="card-header-icon" />
                    PDF Preview
                  </h2>
                </div>
                <div className="card-body">
                  <div className="pdf-preview">
                    {pdfUrl ? (
                      <embed src={pdfUrl} type="application/pdf" />
                    ) : (
                      <div className="pdf-preview-placeholder">No document selected</div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Step 1: Start OCR */}
          {currentStep.originalIndex === 1 && (
            <div className="workspace-grid workspace-grid-2">
              <div className="card">
                <div className="card-header">
                  <h2>
                    <Play size={18} className="card-header-icon" />
                    Start OCR Processing
                  </h2>
                </div>
                <div className="card-body">
                  <p className="text-muted text-sm" style={{ marginBottom: 20 }}>
                    Send the PDF to the Lab OCR API. The local backend will create a job ID and start polling for
                    results.
                  </p>

                  <div style={{ display: "flex", gap: 10 }}>
                    <button className="btn btn-primary" onClick={handleStartOcr} disabled={!file || busy}>
                      {busy ? (
                        <>
                          <Loader2 size={16} className="animate-spin" />
                          Uploading...
                        </>
                      ) : (
                        <>
                          <Play size={16} />
                          Start OCR
                        </>
                      )}
                    </button>
                    <button className="btn btn-secondary" onClick={() => resetWorkflow()} disabled={busy}>
                      Reset
                    </button>
                  </div>

                  {error && (
                    <div className="text-error text-sm" style={{ marginTop: 16 }}>
                      <AlertCircle size={14} style={{ display: "inline", marginRight: 4 }} />
                      {error}
                    </div>
                  )}
                </div>
              </div>

              <div className="card">
                <div className="card-header">
                  <h2>Job Status</h2>
                </div>
                <div className="card-body">
                  <div className="status-list">
                    <div className="status-item">
                      <span className="status-item-label">Local Job ID</span>
                      <span className="status-item-value">{merged?.local_job_id || "-"}</span>
                    </div>
                    <div className="status-item">
                      <span className="status-item-label">Lab Job ID</span>
                      <span className="status-item-value">{merged?.lab_job_id || "-"}</span>
                    </div>
                    <div className="status-item">
                      <span className="status-item-label">Version</span>
                      <span className="status-item-value">{merged?.document_version_no ?? "-"}</span>
                    </div>
                    <div className="status-item">
                      <span className="status-item-label">Status</span>
                      <span className="status-item-value">{merged?.status || "-"}</span>
                    </div>
                    <div className="status-item">
                      <span className="status-item-label">Updated</span>
                      <span className="status-item-value">{formatTimestamp(merged?.updated_at)}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Step 2: OCR Progress & Results */}
          {currentStep.originalIndex === 2 && (
            <div className="workspace-grid workspace-grid-2">
              <div className="card">
                <div className="card-header">
                  <h2>
                    <RefreshCw size={18} className="card-header-icon" />
                    OCR Progress
                  </h2>
                  <div style={{ display: "flex", gap: 8 }}>
                    <button
                      className="btn btn-ghost btn-icon"
                      onClick={handleRefresh}
                      disabled={!job}
                      title="Refresh status"
                    >
                      <RefreshCw size={16} />
                    </button>
                    <button className="btn btn-secondary" onClick={() => setPolling((prev) => !prev)} disabled={!job}>
                      {polling ? "Stop Polling" : "Start Polling"}
                    </button>
                  </div>
                </div>
                <div className="card-body">
                  <div className="progress-container">
                    <div className="progress-bar">
                      <div className="progress-bar-fill" style={{ width: `${Math.min(progress * 100, 100)}%` }} />
                    </div>
                    <div className="progress-label">
                      <span>{Math.round(progress * 100)}% complete</span>
                      <span>
                        {ocrDone ? (
                          <span className="badge badge-success">Complete</span>
                        ) : ocrFailed ? (
                          <span className="badge badge-error">Failed</span>
                        ) : polling ? (
                          <span className="badge badge-accent">Processing</span>
                        ) : (
                          <span className="badge badge-warning">Paused</span>
                        )}
                      </span>
                    </div>
                  </div>

                  <div className="status-list" style={{ marginTop: 20 }}>
                    <div className="status-item">
                      <span className="status-item-label">Status</span>
                      <span className="status-item-value">{merged?.status || "-"}</span>
                    </div>
                    <div className="status-item">
                      <span className="status-item-label">Step</span>
                      <span className="status-item-value">{merged?.step || "-"}</span>
                    </div>
                    <div className="status-item">
                      <span className="status-item-label">Updated</span>
                      <span className="status-item-value">{formatTimestamp(merged?.updated_at)}</span>
                    </div>
                    <div className="status-item">
                      <span className="status-item-label">Output Dir</span>
                      <span className="status-item-value">{merged?.output_dir || "-"}</span>
                    </div>
                  </div>

                  {ocrFailed && (
                    <div className="text-error text-sm" style={{ marginTop: 16 }}>
                      <AlertCircle size={14} style={{ display: "inline", marginRight: 4 }} />
                      OCR failed. Check backend logs.
                    </div>
                  )}
                </div>
              </div>

              <div className="card">
                <div className="card-header">
                  <h2>OCR Results</h2>
                </div>
                <div className="card-body">
                  {resultsLoading ? (
                    <div className="empty-state">
                      <Loader2 size={32} className="empty-state-icon animate-spin" />
                      <p>Loading OCR results...</p>
                    </div>
                  ) : resultsError ? (
                    <div className="text-error text-sm">
                      <AlertCircle size={14} style={{ display: "inline", marginRight: 4 }} />
                      {resultsError}
                    </div>
                  ) : pages.length ? (
                    <>
                      <div className="thumb-grid" style={{ marginBottom: 16 }}>
                        {pages.map((page) => {
                          const artifactId = page?.artifact?.artifact_id
                          const visUrl = artifactId ? `${API_BASE}/results/artifacts/${artifactId}/vis_image` : null
                          return (
                            <button
                              key={page.page_id}
                              type="button"
                              className={`thumb ${activePageId === page.page_id ? "active" : ""}`}
                              onClick={() => setActivePageId(page.page_id)}
                            >
                              {visUrl ? (
                                <img src={visUrl || "/placeholder.svg"} alt={`Page ${page.page_no + 1}`} />
                              ) : (
                                <span className="thumb-placeholder">Page {page.page_no + 1}</span>
                              )}
                            </button>
                          )
                        })}
                      </div>

                      {activeMarkdown ? (
                        <div className="markdown-content">
                          <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]}>
                            {activeMarkdown}
                          </ReactMarkdown>
                        </div>
                      ) : (
                        <div className="text-muted text-sm">Select a page to see OCR Markdown.</div>
                      )}

                      {activeRenderUrl && (
                        <div className="image-preview" style={{ marginTop: 16 }}>
                          <img src={activeRenderUrl || "/placeholder.svg"} alt="OCR page preview" />
                        </div>
                      )}
                    </>
                  ) : (
                    <div className="empty-state">
                      <File size={32} className="empty-state-icon" />
                      <p>No OCR pages yet.</p>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Step 3: Select Images for VLM */}
          {currentStep.originalIndex === 3 && (
            <div className="card">
              <div className="card-header">
                <h2>
                  <ImageIcon size={18} className="card-header-icon" />
                  Select Images for VLM
                </h2>
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <span className="text-muted text-sm">
                    Selected: {selectedImageIds.length} / {images.length}
                  </span>
                  {vlmReady && <span className="badge badge-success">VLM Ready</span>}
                </div>
              </div>
              <div className="card-body">
                <p className="text-muted text-sm" style={{ marginBottom: 20 }}>
                  Choose the OCR-detected images to send to Gemini. Sessions are created when you click "Send to VLM" or
                  move to the next step.
                </p>

                {images.length ? (
                  <div className="thumb-grid" style={{ marginBottom: 20 }}>
                    {images.map((image) => {
                      const imageId = normalizeId(image.image_id)
                      const imageUrl = `${API_BASE}/results/images/${imageId}`
                      const selected = selectedImageSet.has(imageId)
                      return (
                        <button
                          key={imageId}
                          type="button"
                          className={`thumb ${selected ? "selected" : ""}`}
                          onClick={() => handleToggleImageSelection(imageId)}
                        >
                          <img src={imageUrl || "/placeholder.svg"} alt={`Image ${imageId}`} />
                          {selected && <span className="thumb-check">✓</span>}
                        </button>
                      )
                    })}
                  </div>
                ) : (
                  <div className="empty-state">
                    <ImageIcon size={32} className="empty-state-icon" />
                    <p>No images detected yet.</p>
                  </div>
                )}

                <div style={{ display: "flex", gap: 10 }}>
                  <button
                    className="btn btn-primary"
                    onClick={ensureVlmSessions}
                    disabled={!selectedImageIds.length || sendingVlm}
                  >
                    {sendingVlm ? (
                      <>
                        <Loader2 size={16} className="animate-spin" />
                        Sending...
                      </>
                    ) : (
                      <>
                        <Send size={16} />
                        Send to VLM
                      </>
                    )}
                  </button>
                </div>

                {vlmError && (
                  <div className="text-error text-sm" style={{ marginTop: 16 }}>
                    <AlertCircle size={14} style={{ display: "inline", marginRight: 4 }} />
                    {vlmError}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Step 4: Gemini VLM Chat */}
          {currentStep.originalIndex === 4 && (
            <div className="workspace-grid workspace-grid-sidebar">
              <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                <div className="card">
                  <div className="card-header">
                    <h2>Selected Image</h2>
                  </div>
                  <div className="card-body">
                    {activeImage ? (
                      <div className="image-preview">
                        <img src={`${API_BASE}/results/images/${normalizeId(activeImage.image_id)}`} alt="Selected" />
                      </div>
                    ) : (
                      <div className="empty-state">
                        <ImageIcon size={32} className="empty-state-icon" />
                        <p>Select an image session.</p>
                      </div>
                    )}
                  </div>
                </div>

                <div className="card">
                  <div className="card-header">
                    <h2>Sessions</h2>
                  </div>
                  <div className="card-body">
                    <div className="session-list">
                      {selectedImages.length ? (
                        selectedImages.map((image) => {
                          const imageId = normalizeId(image.image_id)
                          const sessionId = sessionByImage[imageId]
                          const locked = sessionId ? sessionLocks[sessionId] : false
                          const sessionTokens = sessionId ? getSessionTokens(sessionId) : null
                          return (
                            <button
                              key={imageId}
                              type="button"
                              className={`session-item ${activeImageId === imageId ? "active" : ""} ${locked ? "locked" : ""}`}
                              onClick={() => handleSelectSessionImage(imageId)}
                            >
                              <img
                                className="session-thumb"
                                src={`${API_BASE}/results/images/${imageId}`}
                                alt={`Image ${imageId}`}
                              />
                              <div className="session-meta">
                                <div className="session-meta-title">Image {imageId}</div>
                                <div className="session-meta-info">
                                  <span>{locked ? " Locked" : " Editable"}</span>
                                  <span>Tokens: {formatNumber(sessionTokens)}</span>
                                </div>
                              </div>
                            </button>
                          )
                        })
                      ) : (
                        <div className="text-muted text-sm">No selected images.</div>
                      )}
                    </div>
                  </div>
                </div>
              </div>

              <div className="card">
                <div className="card-header">
                  <h2>
                    <MessageSquare size={18} className="card-header-icon" />
                    Gemini Conversation
                  </h2>
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <span className="token-badge">Tokens: {formatNumber(getSessionTokens(activeSessionId))}</span>
                    <button
                      className="btn btn-success"
                      onClick={() => handleLockSession(true)}
                      disabled={!activeSessionId}
                    >
                      <Lock size={14} />
                      Confirm
                    </button>
                    <button
                      className="btn btn-secondary"
                      onClick={() => handleLockSession(false)}
                      disabled={!activeSessionId}
                    >
                      <Unlock size={14} />
                      Unlock
                    </button>
                  </div>
                </div>
                <div className="card-body" style={{ padding: 0 }}>
                  <div className="chat-container">
                    <div className="chat-messages">
                      {activeMessages.length ? (
                        activeMessages.map((msg) => (
                          <div key={msg.id} className={`chat-bubble ${msg.role}`}>
                            {msg.content}
                          </div>
                        ))
                      ) : (
                        <div className="empty-state">
                          <MessageSquare size={32} className="empty-state-icon" />
                          <p>No messages yet. Ask Gemini to review the image.</p>
                        </div>
                      )}
                    </div>

                    <div className="chat-input-area">
                      <textarea
                        rows={2}
                        value={vlmInput}
                        onChange={(event) => setVlmInput(event.target.value)}
                        placeholder="Ask Gemini to verify or improve OCR results..."
                        disabled={!activeSessionId || activeLocked}
                      />
                      <button
                        className="btn btn-primary"
                        onClick={handleSendMessage}
                        disabled={vlmBusy || !activeSessionId || activeLocked}
                      >
                        {vlmBusy ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
                      </button>
                    </div>
                  </div>
                </div>
                <div className="card-footer">
                  {activeLocked && <span className="badge badge-success">Session Locked</span>}
                  {!allSessionsConfirmed && (
                    <span className="text-muted text-sm" style={{ marginLeft: 12 }}>
                      Confirm all sessions to continue.
                    </span>
                  )}
                  {vlmError && (
                    <span className="text-error text-sm" style={{ marginLeft: 12 }}>
                      {vlmError}
                    </span>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Processing Step (User Mode) */}
          {currentStep.originalIndex === 100 && (
            <div className="card" style={{ maxWidth: 600, margin: "0 auto" }}>
              <div className="card-header">
                <h2>
                  <Loader2 size={18} className={`card-header-icon ${(busy || polling || sendingVlm) ? 'animate-spin' : ''}`} />
                  Processing status
                </h2>
              </div>
              <div className="card-body">
                <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>

                  {/* Step 1: OCR Processing */}
                  <div style={{ display: "flex", alignItems: "flex-start", gap: 16 }}>
                    <div style={{
                      width: 48, height: 48, borderRadius: "50%",
                      background: ocrDone ? "var(--color-success)" : ocrFailed ? "var(--color-error)" : (busy || polling) ? "var(--color-accent)" : "var(--color-bg-3)",
                      display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0
                    }}>
                      {ocrDone ? <CheckCircle2 size={24} color="white" /> : ocrFailed ? <AlertCircle size={24} color="white" /> : (busy || polling) ? <Loader2 size={24} color="white" className="animate-spin" /> : <span style={{ color: "var(--color-text-2)", fontWeight: 600 }}>1</span>}
                    </div>
                    <div style={{ flex: 1, paddingTop: 8 }}>
                      <div style={{ fontWeight: 600, fontSize: 16, color: "var(--color-text-2)", marginBottom: 4 }}>OCR Processing</div>
                      <div style={{ fontSize: 13, color: "var(--color-text-2)", marginBottom: 8 }}>
                        {ocrDone ? "OCR Processing completed" : ocrFailed ? `Error: ${error}` : (busy || polling) ? `Processing ${Math.round(progress * 100)}%` : "Waiting to start..."}
                      </div>
                      {(busy || polling) && (
                        <div className="progress-bar" style={{ height: 8 }}>
                          <div className="progress-bar-fill" style={{ width: `${Math.min(progress * 100, 100)}%` }} />
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Connector Line */}
                  <div style={{ marginLeft: 23, width: 2, height: 24, background: ocrDone ? "var(--color-success)" : "var(--color-bg-3)" }} />

                  {/* Step 2: VLM Processing */}
                  <div style={{ display: "flex", alignItems: "flex-start", gap: 16 }}>
                    <div style={{
                      width: 48, height: 48, borderRadius: "50%",
                      background: vlmBatchProgress?.completed === vlmBatchProgress?.total && vlmBatchProgress?.total > 0 && vlmBatchProgress?.errors?.length === 0 ? "var(--color-success)" : vlmBatchProgress?.errors?.length > 0 ? "var(--color-error)" : sendingVlm ? "var(--color-accent)" : "var(--color-bg-3)",
                      display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0
                    }}>
                      {vlmBatchProgress?.completed === vlmBatchProgress?.total && vlmBatchProgress?.total > 0 && vlmBatchProgress?.errors?.length === 0 ? <CheckCircle2 size={24} color="white" /> : vlmBatchProgress?.errors?.length > 0 ? <AlertCircle size={24} color="white" /> : sendingVlm ? <Loader2 size={24} color="white" className="animate-spin" /> : <span style={{ color: "var(--color-text-2)", fontWeight: 600 }}>2</span>}
                    </div>
                    <div style={{ flex: 1, paddingTop: 8 }}>
                      <div style={{ fontWeight: 600, fontSize: 16, color: "var(--color-text-2)", marginBottom: 4 }}>VLM Processing</div>
                      <div style={{ fontSize: 13, color: "var(--color-text-2)", marginBottom: 8 }}>
                        {vlmBatchProgress?.completed === vlmBatchProgress?.total && vlmBatchProgress?.total > 0 && vlmBatchProgress?.errors?.length === 0
                          ? `${vlmBatchProgress.completed} images processed`
                          : vlmBatchProgress?.errors?.length > 0 ? `${vlmBatchProgress.errors.length} errors`
                            : sendingVlm && vlmBatchProgress ? `Processing ${vlmBatchProgress.completed}/${vlmBatchProgress.total} images`
                              : ocrDone ? "Preparing to analyze..." : "Waiting for OCR completion..."}
                      </div>
                      {sendingVlm && vlmBatchProgress && vlmBatchProgress.total > 0 && (
                        <div className="progress-bar" style={{ height: 8 }}>
                          <div className="progress-bar-fill" style={{ width: `${(vlmBatchProgress.completed / vlmBatchProgress.total) * 100}%` }} />
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Error Display */}
                  {(error || vlmError) && (
                    <div style={{ padding: 16, background: "rgba(241, 76, 76, 0.1)", borderRadius: "var(--radius-md)", border: "1px solid var(--color-error)" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--color-error)" }}>
                        <AlertCircle size={16} />
                        <span style={{ fontWeight: 500 }}>Error</span>
                      </div>
                      <div style={{ fontSize: 13, marginTop: 8, color: "var(--color-text-1)" }}>{error || vlmError}</div>
                    </div>
                  )}

                  {/* Completion Message */}
                  {vlmBatchProgress?.completed === vlmBatchProgress?.total && vlmBatchProgress?.total > 0 && vlmBatchProgress?.errors?.length === 0 && (
                    <div style={{ padding: 16, background: "rgba(78, 201, 176, 0.1)", borderRadius: "var(--radius-md)", border: "1px solid var(--color-success)", textAlign: "center" }}>
                      <CheckCircle2 size={24} style={{ color: "var(--color-success)", marginBottom: 8 }} />
                      <div style={{ fontWeight: 500, color: "var(--color-success)" }}>Processing completed!</div>
                      <div style={{ fontSize: 13, color: "var(--color-text-2)", marginTop: 4 }}>Click the "Next" button to view the final results</div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Step 5: Final Review */}
          {currentStep.originalIndex === 5 && (
            <>
              <div className="review-nav">
                <button
                  className="btn btn-secondary"
                  onClick={() => setReviewPageIndex((prev) => Math.max(prev - 1, 0))}
                  disabled={reviewPageIndex === 0}
                >
                  <ChevronLeft size={16} />
                  Previous Page
                </button>
                <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
                  <span className="text-muted">
                    Page {reviewPage ? reviewPage.page_no + 1 : 0} / {pages.length}
                  </span>
                  <span className="token-badge">
                    Total tokens:{" "}
                    {overallTokenMeta.unknown
                      ? `${formatNumber(overallTokenMeta.total)}+`
                      : formatNumber(overallTokenMeta.total)}
                  </span>
                </div>
                <button
                  className="btn btn-secondary"
                  onClick={() => setReviewPageIndex((prev) => Math.min(prev + 1, Math.max(pages.length - 1, 0)))}
                  disabled={reviewPageIndex >= pages.length - 1}
                >
                  Next Page
                  <ChevronRight size={16} />
                </button>
              </div>

              <div className="workspace-grid workspace-grid-2" style={{ marginBottom: 20 }}>
                <div className="card">
                  <div className="card-header">
                    <h2>Page Preview</h2>
                  </div>
                  <div className="card-body">
                    {reviewRenderUrl ? (
                      <div className="image-preview">
                        <img src={reviewRenderUrl || "/placeholder.svg"} alt="Review page" />
                      </div>
                    ) : (
                      <div className="empty-state">
                        <File size={32} className="empty-state-icon" />
                        <p>No render image available.</p>
                      </div>
                    )}
                  </div>
                </div>

                <div className="card">
                  <div className="card-header">
                    <h2>OCR Markdown</h2>
                  </div>
                  <div className="card-body">
                    {reviewMarkdown ? (
                      <div className="markdown-content">
                        <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]}>
                          {reviewMarkdown}
                        </ReactMarkdown>
                      </div>
                    ) : (
                      <div className="empty-state">
                        <File size={32} className="empty-state-icon" />
                        <p>No Markdown available for this page.</p>
                      </div>
                    )}
                  </div>
                </div>
              </div>

              <div className="card">
                <div className="card-header">
                  <h2>
                    <MessageSquare size={18} className="card-header-icon" />
                    Image Conversations (Read-only)
                  </h2>
                </div>
                <div className="card-body">
                  {reviewPage?.images?.length ? (
                    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
                      {reviewPage.images.map((image) => {
                        const imageId = normalizeId(image.image_id)
                        const sessionId = sessionByImage[imageId]
                        const messages = sessionId ? messagesBySession[sessionId] || [] : []
                        const sessionTokens = sessionId ? getSessionTokens(sessionId) : null
                        return (
                          <div
                            key={imageId}
                            style={{
                              display: "grid",
                              gridTemplateColumns: "200px 1fr",
                              gap: 16,
                              padding: 16,
                              background: "var(--color-bg-2)",
                              borderRadius: "var(--radius-md)",
                            }}
                          >
                            <div>
                              <div className="image-preview" style={{ marginBottom: 8 }}>
                                <img src={`${API_BASE}/results/images/${imageId}`} alt={`Image ${imageId}`} />
                              </div>
                              <span className="token-badge">Tokens: {formatNumber(sessionTokens)}</span>
                            </div>
                            <div>
                              {sessionId ? (
                                <div style={{ opacity: 0.8 }}>
                                  {messages.length ? (
                                    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                                      {messages.map((msg) => (
                                        <div
                                          key={msg.id}
                                          className={`chat-bubble ${msg.role}`}
                                          style={{ maxWidth: "100%" }}
                                        >
                                          {msg.content}
                                        </div>
                                      ))}
                                    </div>
                                  ) : (
                                    <div className="text-muted text-sm">No messages for this image.</div>
                                  )}
                                </div>
                              ) : (
                                <div className="text-muted text-sm">Not sent to VLM.</div>
                              )}
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  ) : (
                    <div className="empty-state">
                      <ImageIcon size={32} className="empty-state-icon" />
                      <p>No images on this page.</p>
                    </div>
                  )}
                </div>
              </div>
            </>
          )}
        </div>
      </main>
    </div>
  )
}
