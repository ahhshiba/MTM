"use client"
// app/components/steps/ImageSelectionStep.jsx
/**
 * Step 3: Select Images for VLM (Tailwind CSS)
 */

import { ImageIcon, Send, Loader2, AlertCircle } from "lucide-react"
import { useApp } from "../../context/AppContext"
import { useVlmSession } from "../../hooks/useVlmSession"
import { normalizeId } from "../../utils/formatters"
import { API_BASE } from "../../utils/api"
import { cn } from "../../utils/cn"

export default function ImageSelectionStep() {
    const { state, dispatch, computed } = useApp()
    const images = computed.images || []
    const selectedImageIds = state.selectedImageIds || []
    const selectedImageSet = computed.selectedImageSet || new Set()
    const vlmReady = computed.vlmReady
    const { sendingVlm, vlmError } = state
    const { ensureVlmSessions } = useVlmSession()

    const API_ROOT = "/api/ocr"

    return (
        <div className="rounded-xl border border-border bg-card text-card-foreground shadow-sm">
            <div className="flex items-center justify-between p-6 border-b border-border">
                <div className="flex items-center gap-2">
                    <ImageIcon size={20} className="text-muted-foreground" />
                    <h3 className="font-semibold leading-none tracking-tight">Select Images for VLM</h3>
                </div>
                <div className="flex items-center gap-3">
                    <span className="text-sm text-muted-foreground font-medium">
                        Selected: {selectedImageIds.length} / {images.length}
                    </span>
                    {vlmReady && (
                        <span className="inline-flex items-center rounded-full border border-transparent bg-green-500/15 px-2.5 py-0.5 text-xs font-semibold text-green-600">
                            VLM Ready
                        </span>
                    )}
                </div>
            </div>

            <div className="p-6">
                <p className="text-sm text-muted-foreground mb-6 bg-muted/30 p-3 rounded-md border border-border/50">
                    Choose the OCR-detected images to send to Gemini. Sessions are created when you click "Send to VLM" or
                    move to the next step.
                </p>

                {images.length ? (
                    <div className="grid grid-cols-2 xs:grid-cols-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6 xl:grid-cols-8 gap-4 mb-8">
                        {images.map((image) => {
                            const imageId = normalizeId(image.image_id)
                            const imageUrl = `${API_ROOT}/results/images/${imageId}`
                            const selected = selectedImageSet.has(imageId)
                            return (
                                <button
                                    key={imageId}
                                    type="button"
                                    className={cn(
                                        "group relative aspect-square rounded-lg overflow-hidden border-2 transition-all focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2",
                                        selected
                                            ? "border-primary ring-2 ring-primary/20"
                                            : "border-transparent bg-muted hover:border-primary/50"
                                    )}
                                    onClick={() => dispatch({ type: "TOGGLE_IMAGE_SELECTION", payload: imageId })}
                                >
                                    <img
                                        src={imageUrl || "/placeholder.svg"}
                                        alt={`Image ${imageId}`}
                                        className={cn(
                                            "w-full h-full object-cover transition-transform duration-300",
                                            selected ? "scale-105" : "group-hover:scale-105"
                                        )}
                                    />
                                    <div className={cn(
                                        "absolute inset-0 bg-black/0 transition-colors",
                                        selected ? "bg-primary/10" : "group-hover:bg-black/10"
                                    )} />

                                    {selected && (
                                        <div className="absolute top-2 right-2 bg-primary text-primary-foreground rounded-full w-6 h-6 flex items-center justify-center shadow-sm animate-in zoom-in-50 duration-200">
                                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                                                <polyline points="20 6 9 17 4 12"></polyline>
                                            </svg>
                                        </div>
                                    )}
                                </button>
                            )
                        })}
                    </div>
                ) : (
                    <div className="flex flex-col items-center justify-center py-16 text-muted-foreground bg-muted/20 rounded-lg border border-dashed border-border mb-6">
                        <ImageIcon size={32} className="opacity-20 mb-3" />
                        <p>No images detected yet.</p>
                    </div>
                )}

                <div className="flex items-center gap-4">
                    <button
                        className={cn(
                            "inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50",
                            "bg-primary text-primary-foreground shadow hover:bg-primary/90",
                            "h-10 px-6 py-2"
                        )}
                        onClick={ensureVlmSessions}
                        disabled={!selectedImageIds.length || sendingVlm}
                    >
                        {sendingVlm ? (
                            <>
                                <Loader2 size={16} className="mr-2 animate-spin" />
                                Sending to VLM...
                            </>
                        ) : (
                            <>
                                <Send size={16} className="mr-2" />
                                Create VLM Sessions
                            </>
                        )}
                    </button>

                    {vlmError && (
                        <div className="text-destructive text-sm flex items-center gap-2 bg-destructive/10 px-3 py-2 rounded-md">
                            <AlertCircle size={14} />
                            {vlmError}
                        </div>
                    )}
                </div>
            </div>
        </div>
    )
}
