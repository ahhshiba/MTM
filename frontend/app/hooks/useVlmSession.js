"use client"
// app/hooks/useVlmSession.js
/**
 * VLM Session 處理 Hook
 */

import { useCallback } from "react"
import { useApp } from "../context/AppContext"
import {
    createVlmSession,
    createVlmSessionsBatch,
    fetchVlmSession,
    postVlmMessage,
    fetchVlmTokens
} from "../utils/api"
import { writeSessionStore } from "../utils/formatters"

export function useVlmSession() {
    const { state, dispatch, computed } = useApp()
    const { sessionByImage, selectedImageIds } = state
    const { activeSessionId } = computed

    // 載入 session 訊息
    const loadSessionMessages = useCallback(async (sessionId) => {
        if (!sessionId) return

        const { ok, data } = await fetchVlmSession(sessionId)
        if (ok && data.messages) {
            dispatch({
                type: "ADD_MESSAGES_BY_SESSION",
                payload: { sessionId, messages: data.messages }
            })
        }
    }, [dispatch])

    // 載入 session token 統計
    const loadSessionTokens = useCallback(async (sessionId) => {
        if (!sessionId) return

        const { ok, data } = await fetchVlmTokens([sessionId])
        if (ok && data.sessions) {
            dispatch({ type: "MERGE_TOKENS_BY_SESSION", payload: data.sessions })
        }
    }, [dispatch])

    // 批量載入 tokens
    const loadTokensForSessions = useCallback(async (sessionIds) => {
        if (!sessionIds.length) return

        const { ok, data } = await fetchVlmTokens(sessionIds)
        if (ok && data.sessions) {
            dispatch({ type: "MERGE_TOKENS_BY_SESSION", payload: data.sessions })
        }
    }, [dispatch])

    // 建立單一 VLM session
    const createSession = useCallback(async (imageId) => {
        if (sessionByImage[imageId]) return true

        const { ok, data } = await createVlmSession(imageId)
        if (!ok || !data.session_id) {
            dispatch({ type: "SET_VLM_ERROR", payload: data?.detail || "Failed to create VLM session." })
            return false
        }

        const sessionId = data.session_id
        dispatch({ type: "ADD_SESSION_BY_IMAGE", payload: { imageId, sessionId } })

        if (data.messages) {
            dispatch({
                type: "ADD_MESSAGES_BY_SESSION",
                payload: { sessionId, messages: data.messages }
            })
        }

        await loadSessionMessages(sessionId)
        await loadSessionTokens(sessionId)
        return true
    }, [sessionByImage, dispatch, loadSessionMessages, loadSessionTokens])

    // 確保所有選中圖片都有 session
    const ensureVlmSessions = useCallback(async () => {
        if (!selectedImageIds.length) {
            dispatch({ type: "SET_VLM_ERROR", payload: "Select at least one image before sending to VLM." })
            return false
        }

        dispatch({ type: "SET_SENDING_VLM", payload: true })
        dispatch({ type: "SET_VLM_ERROR", payload: "" })

        for (const imageId of selectedImageIds) {
            if (sessionByImage[imageId]) continue

            const success = await createSession(imageId)
            if (!success) {
                dispatch({ type: "SET_SENDING_VLM", payload: false })
                return false
            }
        }

        dispatch({ type: "SET_SENDING_VLM", payload: false })
        return true
    }, [selectedImageIds, sessionByImage, createSession, dispatch])

    // 批量建立 VLM sessions (User Mode)
    const createBatchSessions = useCallback(async (imageIds) => {
        if (!imageIds.length) return { success: true, sessions: [], errors: [] }

        dispatch({
            type: "SET_VLM_BATCH_PROGRESS",
            payload: { total: imageIds.length, completed: 0, errors: [] }
        })
        dispatch({ type: "SET_SENDING_VLM", payload: true })
        dispatch({ type: "SET_VLM_ERROR", payload: "" })

        const { ok, data } = await createVlmSessionsBatch(imageIds)

        if (!ok) {
            dispatch({ type: "SET_VLM_ERROR", payload: data?.detail || "Batch VLM session creation failed." })
            dispatch({
                type: "SET_VLM_BATCH_PROGRESS",
                payload: { total: imageIds.length, completed: 0, errors: [{ error: data?.detail }] }
            })
            dispatch({ type: "SET_SENDING_VLM", payload: false })
            return { success: false, sessions: [], errors: [{ error: data?.detail }] }
        }

        const sessions = data.sessions || []
        const errors = data.errors || []

        // 更新 session mappings 和自動鎖定
        for (const session of sessions) {
            const imageId = session.image_id
            const sessionId = session.session_id
            dispatch({ type: "ADD_SESSION_BY_IMAGE", payload: { imageId, sessionId } })
            dispatch({ type: "SET_SESSION_LOCK", payload: { sessionId, locked: true } })
        }

        dispatch({
            type: "SET_VLM_BATCH_PROGRESS",
            payload: { total: imageIds.length, completed: sessions.length, errors }
        })

        // 載入 tokens 和 messages
        const sessionIds = sessions.map((s) => s.session_id)
        if (sessionIds.length) {
            await loadTokensForSessions(sessionIds)
            await Promise.all(sessionIds.map((sid) => loadSessionMessages(sid)))
        }

        dispatch({ type: "SET_SENDING_VLM", payload: false })
        return { success: errors.length === 0, sessions, errors }
    }, [dispatch, loadTokensForSessions, loadSessionMessages])

    // 發送訊息
    const sendMessage = useCallback(async (content) => {
        if (!activeSessionId || !content.trim() || state.vlmBusy || computed.activeLocked) {
            return false
        }

        dispatch({ type: "SET_VLM_BUSY", payload: true })

        try {
            const { ok, data } = await postVlmMessage(activeSessionId, content.trim())
            if (ok && data.messages) {
                dispatch({
                    type: "ADD_MESSAGES_BY_SESSION",
                    payload: { sessionId: activeSessionId, messages: data.messages }
                })
            }
            dispatch({ type: "SET_VLM_INPUT", payload: "" })
            await loadSessionMessages(activeSessionId)
            await loadSessionTokens(activeSessionId)
            return true
        } finally {
            dispatch({ type: "SET_VLM_BUSY", payload: false })
        }
    }, [activeSessionId, state.vlmBusy, computed.activeLocked, dispatch, loadSessionMessages, loadSessionTokens])

    // 選擇 session 圖片
    const selectSessionImage = useCallback(async (imageId) => {
        dispatch({ type: "SET_ACTIVE_IMAGE_ID", payload: imageId })
        const sessionId = sessionByImage[imageId]
        if (sessionId) {
            await loadSessionMessages(sessionId)
            await loadSessionTokens(sessionId)
        }
    }, [sessionByImage, dispatch, loadSessionMessages, loadSessionTokens])

    // 鎖定/解鎖 session
    const lockSession = useCallback((locked) => {
        if (!activeSessionId) return
        dispatch({ type: "SET_SESSION_LOCK", payload: { sessionId: activeSessionId, locked } })
    }, [activeSessionId, dispatch])

    return {
        loadSessionMessages,
        loadSessionTokens,
        loadTokensForSessions,
        createSession,
        ensureVlmSessions,
        createBatchSessions,
        sendMessage,
        selectSessionImage,
        lockSession,
    }
}
