"use client"
// app/components/steps/FinalReviewStep.jsx
/**
 * Step 5: Final Review (Tailwind CSS)
 */

import { FileCheck, ChevronLeft, ChevronRight, File, ImageIcon } from "lucide-react"
import ReactMarkdown from "react-markdown"
import rehypeRaw from "rehype-raw"
import remarkGfm from "remark-gfm"
import { useApp } from "../../context/AppContext"
import { useOcrJob } from "../../hooks/useOcrJob"
import { useVlmSession } from "../../hooks/useVlmSession"
import { formatNumber, normalizeId } from "../../utils/formatters"
import { useEffect } from "react"
import { cn } from "../../utils/cn"

const API_ROOT = "/api/ocr"

export default function FinalReviewStep() {
    const { state, dispatch, computed } = useApp()
    const {
        reviewPageIndex,
        artifactMarkdownById,
        sessionByImage,
        messagesBySession,
        tokensBySession
    } = state
    const { pages } = computed
    const { loadArtifactMarkdown } = useOcrJob()
    const { loadSessionMessages } = useVlmSession()

    const reviewPage = pages[reviewPageIndex]
    const reviewArtifactId = reviewPage?.artifact?.artifact_id
    const reviewMarkdown = reviewArtifactId ? artifactMarkdownById[reviewArtifactId] : ""

    const reviewRenderUrl = reviewPage?.render_image_url
        ? `${API_ROOT}/results/pages/${reviewPage.page_id}/render_image`
        : reviewArtifactId
            ? `${API_ROOT}/results/artifacts/${reviewArtifactId}/vis_image`
            : null

    // Ensure Markdown is loaded
    useEffect(() => {
        if (reviewArtifactId && !reviewMarkdown && !Object.prototype.hasOwnProperty.call(artifactMarkdownById, reviewArtifactId)) {
            loadArtifactMarkdown(reviewArtifactId)
        }
    }, [reviewArtifactId, reviewMarkdown, artifactMarkdownById, loadArtifactMarkdown])

    // Ensure VLM messages are loaded for images on this page
    useEffect(() => {
        if (reviewPage?.images?.length) {
            reviewPage.images.forEach(img => {
                const imageId = normalizeId(img.image_id)
                const sessionId = sessionByImage[imageId]
                if (sessionId && !messagesBySession[sessionId]) {
                    loadSessionMessages(sessionId)
                }
            })
        }
    }, [reviewPage, sessionByImage, messagesBySession, loadSessionMessages])

    return (
        <div className="space-y-6">
            <div className="flex justify-between items-center p-2 bg-card rounded-lg border border-border shadow-sm">
                <button
                    className="inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 border border-input bg-background shadow-sm hover:bg-accent hover:text-accent-foreground h-9 px-4 py-2"
                    onClick={() => dispatch({ type: "SET_REVIEW_PAGE_INDEX", payload: Math.max(reviewPageIndex - 1, 0) })}
                    disabled={reviewPageIndex === 0}
                >
                    <ChevronLeft size={16} className="mr-2" />
                    Previous Page
                </button>
                <div className="flex items-center gap-4">
                    <span className="text-sm font-medium text-muted-foreground">
                        Page <span className="text-foreground">{reviewPage ? reviewPage.page_no + 1 : 0}</span> / {pages.length}
                    </span>
                </div>
                <button
                    className="inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 border border-input bg-background shadow-sm hover:bg-accent hover:text-accent-foreground h-9 px-4 py-2"
                    onClick={() => dispatch({ type: "SET_REVIEW_PAGE_INDEX", payload: Math.min(reviewPageIndex + 1, pages.length - 1) })}
                    disabled={reviewPageIndex >= pages.length - 1}
                >
                    Next Page
                    <ChevronRight size={16} className="ml-2" />
                </button>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <div className="flex flex-col gap-6">
                    {/* Page Preview */}
                    <div className="rounded-xl border border-border bg-card text-card-foreground shadow-sm">
                        <div className="flex flex-col space-y-1.5 p-6 border-b border-border">
                            <h3 className="font-semibold leading-none tracking-tight">Page Preview</h3>
                        </div>
                        <div className="p-6 flex justify-center bg-muted/20 min-h-[300px] items-center">
                            {reviewRenderUrl ? (
                                <img
                                    src={reviewRenderUrl || "/placeholder.svg"}
                                    alt="Review page"
                                    className="max-w-full max-h-[500px] object-contain shadow-sm border border-border/50 rounded-sm"
                                />
                            ) : (
                                <div className="flex flex-col items-center justify-center text-muted-foreground opacity-50">
                                    <File size={40} className="mb-2" />
                                    <p>No render image available.</p>
                                </div>
                            )}
                        </div>
                    </div>

                    {/* OCR Markdown */}
                    <div className="rounded-xl border border-border bg-card text-card-foreground shadow-sm flex-1 flex flex-col">
                        <div className="flex flex-col space-y-1.5 p-6 border-b border-border">
                            <h3 className="font-semibold leading-none tracking-tight">OCR Markdown</h3>
                        </div>
                        <div className="p-6 flex-1 overflow-y-auto max-h-[500px]">
                            {reviewMarkdown ? (
                                <article className="prose prose-sm max-w-none dark:prose-invert prose-headings:font-semibold prose-a:text-primary hover:prose-a:underline">
                                    <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]}>
                                        {reviewMarkdown}
                                    </ReactMarkdown>
                                </article>
                            ) : (
                                <div className="flex flex-col items-center justify-center text-muted-foreground opacity-50 h-32">
                                    <File size={32} className="mb-2" />
                                    <p>No Markdown available for this page.</p>
                                </div>
                            )}
                        </div>
                    </div>
                </div>

                {/* VLM Conversations */}
                <div className="rounded-xl border border-border bg-card text-card-foreground shadow-sm h-full flex flex-col">
                    <div className="flex flex-col space-y-1.5 p-6 border-b border-border">
                        <h3 className="font-semibold leading-none tracking-tight">Image Conversations</h3>
                    </div>
                    <div className="p-6 flex-1 overflow-y-auto max-h-[calc(100vh-250px)] space-y-6">
                        {reviewPage?.images?.length ? (
                            reviewPage.images.map((image) => {
                                const imageId = normalizeId(image.image_id)
                                const sessionId = sessionByImage[imageId]
                                const messages = sessionId ? messagesBySession[sessionId] || [] : []
                                const sessionTokens = sessionId ? tokensBySession[sessionId]?.total_tokens : null
                                return (
                                    <div
                                        key={imageId}
                                        className="rounded-lg border border-border bg-muted/30 overflow-hidden"
                                    >
                                        <div className="p-4 grid grid-cols-[120px_1fr] gap-4">
                                            <div className="flex flex-col gap-2">
                                                <div className="aspect-square rounded-md overflow-hidden border border-border bg-background">
                                                    <img
                                                        src={`${API_ROOT}/results/images/${imageId}`}
                                                        alt={`Image ${imageId}`}
                                                        className="w-full h-full object-cover"
                                                    />
                                                </div>
                                                <div className="text-xs text-muted-foreground text-center bg-background px-2 py-1 rounded border border-border">
                                                    {sessionTokens ? `${formatNumber(sessionTokens)} toks` : "-"}
                                                </div>
                                            </div>

                                            <div className="flex flex-col gap-3">
                                                {sessionId ? (
                                                    messages.length ? (
                                                        <div className="flex flex-col gap-3">
                                                            {messages.map((msg, i) => (
                                                                <div
                                                                    key={i}
                                                                    className={cn(
                                                                        "rounded-lg px-3 py-2 text-sm shadow-sm max-w-full",
                                                                        msg.role === "user"
                                                                            ? "bg-primary text-primary-foreground ml-auto rounded-br-sm text-right"
                                                                            : "bg-background border border-border text-foreground mr-auto rounded-bl-sm"
                                                                    )}
                                                                >
                                                                    {msg.content}
                                                                </div>
                                                            ))}
                                                        </div>
                                                    ) : (
                                                        <div className="text-muted-foreground text-xs italic flex items-center h-full">No messages for this image.</div>
                                                    )
                                                ) : (
                                                    <div className="text-muted-foreground text-xs italic flex items-center h-full">Not sent to VLM.</div>
                                                )}
                                            </div>
                                        </div>
                                    </div>
                                )
                            })
                        ) : (
                            <div className="flex flex-col items-center justify-center py-12 text-muted-foreground opacity-50">
                                <ImageIcon size={48} className="mb-3" />
                                <p>No images on this page.</p>
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    )
}
