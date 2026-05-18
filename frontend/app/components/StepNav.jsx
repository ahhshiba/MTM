"use client"
// app/components/StepNav.jsx
/**
 * 步驟導航元件 (Tailwind CSS)
 */

import {
  Upload,
  Play,
  RefreshCw,
  ImageIcon,
  MessageSquare,
  FileCheck,
  Loader2,
  Cpu,
  Eye
} from "lucide-react"
import { cn } from "../utils/cn"

// Step 定義
export const ALL_STEPS = [
  {
    id: "upload",
    title: "Upload PDF",
    note: "Choose a file and preview basic metadata before starting OCR.",
    icon: Upload,
    originalIndex: 0,
  },
  {
    id: "start-ocr",
    title: "Start OCR",
    note: "Create a local job and send the PDF to the Lab OCR API.",
    icon: Play,
    originalIndex: 1,
  },
  {
    id: "ocr-progress",
    title: "OCR Progress",
    note: "Track status, then preview Markdown and page images when done.",
    icon: RefreshCw,
    originalIndex: 2,
  },
  {
    id: "select-images",
    title: "Select Images",
    note: "Pick images to send to Gemini, then generate VLM sessions in batch.",
    icon: ImageIcon,
    originalIndex: 3,
  },
  {
    id: "vlm-chat",
    title: "VLM Chat",
    note: "Review each image session, chat, and lock when confirmed.",
    icon: MessageSquare,
    originalIndex: 4,
  },
  {
    id: "extraction",
    title: "Extraction",
    note: "Extract structured data (BOM, Measurements) from OCR results.",
    icon: Cpu,
    originalIndex: 6,
  },
  {
    id: "preview",
    title: "Data Preview",
    note: "Preview structured data and jump to source pages.",
    icon: Eye,
    originalIndex: 7,
  },
  // User mode only: Processing step
  {
    id: "processing",
    title: "Processing",
    note: "Processing OCR and VLM image analysis...",
    icon: Loader2,
    originalIndex: 100,
  },
  {
    id: "final-review",
    title: "Final Review",
    note: "Review each page with OCR Markdown and locked VLM notes.",
    icon: FileCheck,
    originalIndex: 5,
  },
]

// 根據模式過濾步驟
export function getStepsForMode(isUserMode) {
  if (isUserMode) {
    // User mode: Upload -> Processing -> Preview -> Final Review
    const userSteps = ALL_STEPS.filter((s) =>
      s.originalIndex === 0 ||
      s.originalIndex === 100 ||
      s.originalIndex === 7 ||
      s.originalIndex === 5
    )

    // 重新排序以確保正確順序
    const order = [0, 100, 7, 5] // Upload, Processing, Preview, Final Review
    return userSteps.sort((a, b) => {
      return order.indexOf(a.originalIndex) - order.indexOf(b.originalIndex)
    })
  }
  // Developer mode: exclude Processing step, include all others
  return ALL_STEPS.filter((s) => s.originalIndex < 100)
}

export default function StepNav({ steps, currentIndex, onStepClick, collapsed = false }) {
  return (
    <nav className="flex flex-col gap-1 py-4 px-2">
      {steps.map((step, idx) => {
        const Icon = step.icon
        const isActive = idx === currentIndex
        const isPast = idx < currentIndex

        return (
          <button
            key={step.id}
            className={cn(
              "group flex items-center gap-3 w-full text-left rounded-lg transition-all border border-transparent",
              "hover:bg-muted/50",
              isActive && "bg-primary/10 border-primary/20",
              isPast && "text-muted-foreground",
              collapsed ? "justify-center px-2 py-2.5" : "px-4 py-2.5"
            )}
            onClick={() => onStepClick(idx)}
            title={collapsed ? `${step.title} (Step ${idx + 1})` : undefined}
          >
            <div className={cn(
              "w-9 h-9 flex items-center justify-center rounded-full bg-muted flex-shrink-0 text-muted-foreground transition-colors",
              isActive && "bg-primary text-primary-foreground",
              isPast && "bg-green-500 text-white"
            )}>
              <Icon size={18} className={cn(step.icon === Loader2 && isActive && "animate-spin")} />
            </div>
            {!collapsed && (
              <div className="flex flex-col min-w-0">
                <span className={cn(
                  "text-sm font-medium truncate text-foreground",
                  isActive && "text-primary"
                )}>
                  {step.title}
                </span>
                <span className="text-[11px] text-muted-foreground">Step {idx + 1}</span>
              </div>
            )}
          </button>
        )
      })}
    </nav>
  )
}
