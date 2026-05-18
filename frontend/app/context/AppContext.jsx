"use client"
// app/context/AppContext.jsx
/**
 * 全域狀態 Context
 */

import { createContext, useContext, useReducer, useCallback, useEffect, useMemo } from "react"
import {
    readSessionStore,
    writeSessionStore,
    normalizeId,
    MODE_STORAGE_KEY
} from "../utils/formatters"

const AppContext = createContext(null)

function progressValue(value) {
    return typeof value === "number" ? value : null
}

function sameOcrJob(prev, next) {
    if (!prev || !next) return false
    const prevId = prev.local_job_id || prev.lab_job_id || prev.ocr_run_id
    const nextId = next.local_job_id || next.lab_job_id || next.ocr_run_id
    return Boolean(prevId && nextId && String(prevId) === String(nextId))
}

function keepMonotonicProgress(prev, next) {
    if (!sameOcrJob(prev, next)) return next
    const prevProgress = progressValue(prev.progress)
    const nextProgress = progressValue(next?.progress)
    if (prevProgress === null || nextProgress === null || nextProgress >= prevProgress) {
        return next
    }
    return { ...next, progress: prevProgress }
}

function sameExtraction(prev, next) {
    if (!prev || !next) return false
    const prevId = prev.extraction_run_id
    const nextId = next.extraction_run_id
    return Boolean(prevId && nextId && String(prevId) === String(nextId))
}

function keepMonotonicExtractionProgress(prev, next) {
    if (!sameExtraction(prev, next)) return next
    const prevProgress = progressValue(prev.progress)
    const nextProgress = progressValue(next?.progress)
    if (prevProgress === null || nextProgress === null || nextProgress >= prevProgress) {
        return next
    }
    return { ...next, progress: prevProgress }
}

const initialState = {
    // Mode
    mode: "developer", // "developer" | "user"
    modeLoaded: false,

    // Step navigation
    stepIndex: 0,

    // File upload
    file: null,
    pdfUrl: "",
    pdfPageCount: null,
    pdfLoading: false,
    pdfError: "",

    // OCR job
    job: null,
    status: null,
    polling: false,
    busy: false,
    error: "",

    // OCR results
    results: null,
    resultsLoading: false,
    resultsError: "",
    activePageId: null,
    artifactMarkdownById: {},
    artifactJsonById: {},

    // VLM
    activeImageId: null,
    selectedImageIds: [],
    sessionByImage: {},
    messagesBySession: {},
    sessionLocks: {},
    tokensBySession: {},
    vlmInput: "",
    vlmBusy: false,
    vlmError: "",
    sendingVlm: false,
    vlmBatchProgress: null,

    // Review
    reviewPageIndex: 0,

    // Extraction (NEW)
    extractionRun: null,
    extractionStatus: null,
    extractionResult: null,
    extractionPolling: false,
    extractionError: "",
}

function appReducer(state, action) {
    switch (action.type) {
        case "SET_MODE":
            return { ...state, mode: action.payload, modeLoaded: true }
        case "SET_MODE_LOADED":
            return { ...state, modeLoaded: true }
        case "SET_STEP_INDEX":
            return { ...state, stepIndex: action.payload }
        case "SET_FILE":
            return { ...state, file: action.payload }
        case "SET_PDF_INFO":
            return { ...state, ...action.payload }
        case "SET_JOB":
            return { ...state, job: action.payload }
        case "SET_STATUS":
            return { ...state, status: keepMonotonicProgress(state.status || state.job, action.payload) }
        case "SET_POLLING":
            return { ...state, polling: action.payload }
        case "SET_BUSY":
            return { ...state, busy: action.payload }
        case "SET_ERROR":
            return { ...state, error: action.payload }
        case "SET_RESULTS":
            return { ...state, results: action.payload }
        case "SET_RESULTS_LOADING":
            return { ...state, resultsLoading: action.payload }
        case "SET_RESULTS_ERROR":
            return { ...state, resultsError: action.payload }
        case "SET_ACTIVE_PAGE_ID":
            return { ...state, activePageId: action.payload }
        case "SET_ARTIFACT_MARKDOWN":
            return {
                ...state,
                artifactMarkdownById: {
                    ...state.artifactMarkdownById,
                    [action.payload.id]: action.payload.markdown
                }
            }
        case "SET_ARTIFACT_JSON":
            return {
                ...state,
                artifactJsonById: {
                    ...state.artifactJsonById,
                    [action.payload.id]: action.payload.json
                }
            }
        case "SET_ACTIVE_IMAGE_ID":
            return { ...state, activeImageId: action.payload }
        case "SET_SELECTED_IMAGE_IDS":
            return { ...state, selectedImageIds: action.payload }
        case "TOGGLE_IMAGE_SELECTION": {
            const imageId = action.payload
            const prev = state.selectedImageIds
            const next = prev.includes(imageId)
                ? prev.filter((id) => id !== imageId)
                : [...prev, imageId]
            return { ...state, selectedImageIds: next }
        }
        case "SET_SESSION_BY_IMAGE":
            return { ...state, sessionByImage: action.payload }
        case "ADD_SESSION_BY_IMAGE": {
            const { imageId, sessionId } = action.payload
            const next = { ...state.sessionByImage, [imageId]: sessionId }
            writeSessionStore(next)
            return { ...state, sessionByImage: next }
        }
        case "SET_MESSAGES_BY_SESSION":
            return { ...state, messagesBySession: action.payload }
        case "ADD_MESSAGES_BY_SESSION": {
            const { sessionId, messages } = action.payload
            return {
                ...state,
                messagesBySession: { ...state.messagesBySession, [sessionId]: messages }
            }
        }
        case "SET_SESSION_LOCKS":
            return { ...state, sessionLocks: action.payload }
        case "SET_SESSION_LOCK": {
            const { sessionId, locked } = action.payload
            return {
                ...state,
                sessionLocks: { ...state.sessionLocks, [sessionId]: locked }
            }
        }
        case "SET_TOKENS_BY_SESSION":
            return { ...state, tokensBySession: action.payload }
        case "ADD_TOKENS_BY_SESSION": {
            const { sessionId, tokens } = action.payload
            return {
                ...state,
                tokensBySession: { ...state.tokensBySession, [sessionId]: tokens }
            }
        }
        case "MERGE_TOKENS_BY_SESSION": {
            const sessions = action.payload
            const next = { ...state.tokensBySession }
            sessions.forEach((s) => {
                next[s.session_id] = {
                    prompt_tokens: s.prompt_tokens,
                    candidate_tokens: s.candidate_tokens,
                    total_tokens: s.total_tokens,
                }
            })
            return { ...state, tokensBySession: next }
        }
        case "SET_VLM_INPUT":
            return { ...state, vlmInput: action.payload }
        case "SET_VLM_BUSY":
            return { ...state, vlmBusy: action.payload }
        case "SET_VLM_ERROR":
            return { ...state, vlmError: action.payload }
        case "SET_SENDING_VLM":
            return { ...state, sendingVlm: action.payload }
        case "SET_VLM_BATCH_PROGRESS": {
            const prev = state.vlmBatchProgress
            const next = action.payload
            if (next?.completed === 0) {
                return { ...state, vlmBatchProgress: next }
            }
            if (prev && next && prev.total === next.total) {
                return {
                    ...state,
                    vlmBatchProgress: {
                        ...next,
                        completed: Math.max(prev.completed || 0, next.completed || 0),
                    }
                }
            }
            return { ...state, vlmBatchProgress: next }
        }
        case "SET_REVIEW_PAGE_INDEX":
            return { ...state, reviewPageIndex: action.payload }
        // Extraction
        case "SET_EXTRACTION_RUN":
            return { ...state, extractionRun: action.payload }
        case "SET_EXTRACTION_STATUS":
            return {
                ...state,
                extractionStatus: keepMonotonicExtractionProgress(state.extractionStatus, action.payload)
            }
        case "SET_EXTRACTION_RESULT":
            return { ...state, extractionResult: action.payload }
        case "SET_EXTRACTION_POLLING":
            return { ...state, extractionPolling: action.payload }
        case "SET_EXTRACTION_ERROR":
            return { ...state, extractionError: action.payload }
        case "RESTORE_HISTORY_RUN": {
            // Restore a historical run — sets all state needed for Preview
            const { job: hJob, status: hStatus, extractionRun: hExtRun, extractionStatus: hExtStatus, extractionResult: hExtResult, stepIndex: hStep } = action.payload
            return {
                ...state,
                job: hJob || state.job,
                status: hStatus || state.status,
                extractionRun: hExtRun || state.extractionRun,
                extractionStatus: hExtStatus || state.extractionStatus,
                extractionResult: hExtResult || state.extractionResult,
                extractionPolling: false,
                extractionError: "",
                stepIndex: hStep ?? state.stepIndex,
                polling: false,
                busy: false,
                error: "",
            }
        }
        case "RESET_WORKFLOW": {
            const keepFile = action.payload?.keepFile
            return {
                ...initialState,
                mode: state.mode,
                modeLoaded: state.modeLoaded,
                file: keepFile ? state.file : null,
                pdfUrl: keepFile ? state.pdfUrl : "",
                pdfPageCount: keepFile ? state.pdfPageCount : null,
            }
        }
        default:
            return state
    }
}

export function AppProvider({ children }) {
    const [state, dispatch] = useReducer(appReducer, initialState)

    // Load mode and sessions from localStorage
    useEffect(() => {
        const savedMode = window.localStorage.getItem(MODE_STORAGE_KEY)
        if (savedMode && (savedMode === "developer" || savedMode === "user")) {
            dispatch({ type: "SET_MODE", payload: savedMode })
        } else {
            dispatch({ type: "SET_MODE_LOADED" })
        }

        const cached = readSessionStore()
        dispatch({ type: "SET_SESSION_BY_IMAGE", payload: cached })
    }, [])

    // Computed values
    const computed = useMemo(() => {
        const merged = state.status || state.job
        const normalizedStatus = (merged?.status || "").toLowerCase()
        const normalizedStep = (merged?.step || "").toLowerCase()
        const progress = typeof merged?.progress === "number" ? merged.progress : 0

        const ocrDone =
            ["succeeded", "done", "completed", "finished"].includes(normalizedStatus) ||
            normalizedStep === "done" ||
            progress >= 1
        const ocrFailed = ["failed", "error"].includes(normalizedStatus)

        const pages = state.results?.pages || []
        const images = pages.flatMap((page) =>
            page.images?.map((img) => ({ ...img, page })) || []
        )

        const selectedImageSet = new Set(state.selectedImageIds)
        const selectedImages = images.filter((img) =>
            selectedImageSet.has(normalizeId(img.image_id))
        )

        const activeImage = images.find((img) =>
            normalizeId(img.image_id) === state.activeImageId
        )
        const activeSessionId = state.activeImageId
            ? state.sessionByImage[state.activeImageId]
            : null
        const activeMessages = activeSessionId
            ? state.messagesBySession[activeSessionId] || []
            : []
        const activeLocked = activeSessionId
            ? state.sessionLocks[activeSessionId] === true
            : false

        const vlmReady = state.selectedImageIds.length > 0 &&
            state.selectedImageIds.every((id) => Boolean(state.sessionByImage[id]))
        const allSessionsConfirmed = vlmReady &&
            state.selectedImageIds.every((id) =>
                state.sessionLocks[state.sessionByImage[id]] === true
            )

        return {
            merged,
            normalizedStatus,
            normalizedStep,
            progress,
            ocrDone,
            ocrFailed,
            pages,
            images,
            selectedImageSet,
            selectedImages,
            activeImage,
            activeSessionId,
            activeMessages,
            activeLocked,
            vlmReady,
            allSessionsConfirmed,
            isUserMode: state.mode === "user",
        }
    }, [state])

    return (
        <AppContext.Provider value={{ state, dispatch, computed }}>
            {children}
        </AppContext.Provider>
    )
}

export function useApp() {
    const context = useContext(AppContext)
    if (!context) {
        throw new Error("useApp must be used within AppProvider")
    }
    return context
}
