"use client"
// app/components/steps/VlmChatStep.jsx
/**
 * Step 4: Gemini VLM Chat (Tailwind CSS)
 */

import { ImageIcon, MessageSquare, Send, Lock, Unlock } from "lucide-react"
import { useApp } from "../../context/AppContext"
import { useVlmSession } from "../../hooks/useVlmSession"
import { normalizeId, formatNumber } from "../../utils/formatters"
import { cn } from "../../utils/cn"

// API_ROOT for image URLs
const API_ROOT = "/api/ocr"

export default function VlmChatStep() {
    const { state, dispatch, computed } = useApp()
    const {
        activeImage,
        activeSessionId,
        activeMessages,
        activeLocked,
        allSessionsConfirmed,
        selectedImages
    } = computed
    const { vlmBusy, vlmInput } = state
    const { sendMessage, selectSessionImage, lockSession } = useVlmSession()

    const handleKeyDown = (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault()
            sendMessage(vlmInput)
        }
    }

    const sessionTokens = activeSessionId
        ? state.tokensBySession[activeSessionId]?.total_tokens
        : 0

    return (
        <div className="grid grid-cols-1 lg:grid-cols-[300px_1fr] gap-6 h-[calc(100vh-140px)]">
            <div className="flex flex-col gap-4 h-full overflow-hidden">
                {/* Active Image Preview Card */}
                <div className="rounded-xl border border-border bg-card text-card-foreground shadow-sm shrink-0">
                    <div className="p-4 border-b border-border">
                        <h3 className="font-semibold text-sm">Selected Image</h3>
                    </div>
                    <div className="p-4 flex justify-center bg-muted/20">
                        {activeImage ? (
                            <div className="relative rounded-lg overflow-hidden border border-border shadow-sm max-h-[200px]">
                                <img
                                    src={`${API_ROOT}/results/images/${normalizeId(activeImage.image_id)}`}
                                    alt="Selected"
                                    className="max-w-full max-h-[200px] object-contain bg-background/50"
                                />
                            </div>
                        ) : (
                            <div className="flex flex-col items-center justify-center h-[120px] text-muted-foreground bg-muted/10 rounded-lg w-full border border-dashed border-border">
                                <ImageIcon size={24} className="opacity-20 mb-2" />
                                <span className="text-xs">Select session</span>
                            </div>
                        )}
                    </div>
                </div>

                {/* Session List Card */}
                <div className="rounded-xl border border-border bg-card text-card-foreground shadow-sm flex flex-col flex-1 overflow-hidden">
                    <div className="p-4 border-b border-border flex items-center justify-between bg-muted/5">
                        <h3 className="font-semibold text-sm">Sessions</h3>
                        {allSessionsConfirmed && (
                            <span className="inline-flex items-center rounded-full border border-transparent bg-green-500/15 px-2 py-0.5 text-[10px] font-semibold text-green-600">
                                All Confirmed
                            </span>
                        )}
                    </div>
                    <div className="flex-1 overflow-y-auto p-2 scrollbar-thin">
                        <div className="space-y-1">
                            {selectedImages.map((img) => {
                                const imageId = normalizeId(img.image_id)
                                const isActive = activeImage && normalizeId(activeImage.image_id) === imageId
                                const sessionId = state.sessionByImage[imageId]
                                const isLocked = state.sessionLocks[sessionId] === true

                                return (
                                    <button
                                        key={imageId}
                                        className={cn(
                                            "w-full flex items-center gap-3 p-2 rounded-lg text-left transition-all text-sm group border border-transparent",
                                            isActive
                                                ? "bg-primary/10 text-primary border-primary/20 shadow-sm"
                                                : "hover:bg-muted text-muted-foreground hover:text-foreground",
                                            isLocked && !isActive && "opacity-60 bg-muted/20"
                                        )}
                                        onClick={() => selectSessionImage(imageId)}
                                    >
                                        <div className={cn(
                                            "w-10 h-10 rounded-md overflow-hidden bg-muted flex-shrink-0 border border-border",
                                            isActive && "ring-1 ring-primary/30"
                                        )}>
                                            <img
                                                src={`${API_ROOT}/results/images/${imageId}`}
                                                alt="thumb"
                                                className="w-full h-full object-cover"
                                            />
                                        </div>
                                        <div className="flex-1 min-w-0">
                                            <div className="font-medium truncate">{img.image_type || "Image"}</div>
                                            <div className="text-[10px] opacity-70 truncate">{sessionId ? "Active" : "Pending"}</div>
                                        </div>
                                        {isLocked && <Lock size={12} className="ml-auto text-muted-foreground" />}
                                        {!isLocked && sessionId && <span className="w-2 h-2 rounded-full bg-green-500 ml-auto shadow-[0_0_4px_rgba(34,197,94,0.5)]"></span>}
                                    </button>
                                )
                            })}
                        </div>
                    </div>
                </div>
            </div>

            {/* Chat Area */}
            <div className="rounded-xl border border-border bg-card text-card-foreground shadow-sm flex flex-col h-full overflow-hidden">
                <div className="h-14 px-6 border-b border-border flex items-center justify-between shrink-0 bg-muted/5">
                    <div className="flex items-center gap-2">
                        <MessageSquare size={18} className="text-primary hidden sm:block" />
                        <h2 className="font-semibold tracking-tight">Gemini Chat</h2>
                    </div>
                    <div className="flex items-center gap-3">
                        <span className="text-xs font-mono text-muted-foreground bg-muted px-2 py-1 rounded-md border border-border">
                            {formatNumber(sessionTokens)} toks
                        </span>
                        {activeSessionId && (
                            <button
                                className={cn(
                                    "inline-flex items-center justify-center rounded-md text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 h-8 px-3",
                                    activeLocked
                                        ? "bg-secondary text-secondary-foreground hover:bg-secondary/80"
                                        : "bg-primary text-primary-foreground hover:bg-primary/90 shadow-sm"
                                )}
                                onClick={() => lockSession(!activeLocked)}
                            >
                                {activeLocked ? (
                                    <>
                                        <Unlock size={12} className="mr-1.5" />
                                        Unlock
                                    </>
                                ) : (
                                    <>
                                        <Lock size={12} className="mr-1.5" />
                                        Confirm
                                    </>
                                )}
                            </button>
                        )}
                    </div>
                </div>

                <div className="flex-1 overflow-y-auto p-6 space-y-6 bg-muted/5">
                    {activeMessages.length ? (
                        activeMessages.map((msg, idx) => (
                            <div
                                key={idx}
                                className={cn(
                                    "flex flex-col max-w-[85%] rounded-2xl px-5 py-3 text-sm shadow-sm",
                                    msg.role === "user"
                                        ? "bg-primary text-primary-foreground ml-auto rounded-br-sm"
                                        : "bg-card border border-border text-card-foreground mr-auto rounded-bl-sm"
                                )}
                            >
                                <span className={cn(
                                    "text-[10px] font-bold uppercase tracking-wider mb-1 opacity-70",
                                    msg.role === "user" ? "text-primary-foreground" : "text-muted-foreground"
                                )}>
                                    {msg.role === "user" ? "You" : "Gemini"}
                                </span>
                                <p className="leading-relaxed whitespace-pre-wrap">{msg.content}</p>
                            </div>
                        ))
                    ) : (
                        <div className="h-full flex flex-col items-center justify-center text-muted-foreground opacity-50">
                            <MessageSquare size={48} className="mb-4 text-muted-foreground/30" />
                            <p className="text-sm">No messages yet. Ask Gemini about this image.</p>
                        </div>
                    )}
                </div>

                <div className="p-4 bg-card border-t border-border shrink-0">
                    <div className="flex gap-2 relative">
                        <textarea
                            className="flex min-h-[50px] w-full rounded-md border border-input bg-background px-3 py-3 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 resize-none pr-12 scrollbar-hide"
                            placeholder={activeSessionId ? "Ask a question about this image..." : "Select a session to start chatting"}
                            value={vlmInput}
                            onChange={(e) => dispatch({ type: "SET_VLM_INPUT", payload: e.target.value })}
                            onKeyDown={handleKeyDown}
                            disabled={vlmBusy || activeLocked || !activeSessionId}
                            rows={1}
                        />
                        <button
                            className={cn(
                                "absolute right-2 bottom-2 inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50",
                                "bg-primary text-primary-foreground shadow hover:bg-primary/90",
                                "h-8 w-8 p-0"
                            )}
                            onClick={() => sendMessage(vlmInput)}
                            disabled={vlmBusy || !vlmInput.trim() || activeLocked || !activeSessionId}
                        >
                            <Send size={14} />
                        </button>
                    </div>
                    {activeLocked && (
                        <div className="text-xs text-muted-foreground text-center mt-2 flex items-center justify-center gap-1">
                            <Lock size={10} />
                            Session locked. Unlock to continue chatting.
                        </div>
                    )}
                </div>
            </div>
        </div>
    )
}
