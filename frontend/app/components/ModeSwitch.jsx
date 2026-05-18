"use client"
// app/components/ModeSwitch.jsx
/**
 * 開發者/使用者模式切換元件 (Tailwind CSS)
 */

import { useApp } from "../context/AppContext"
import { MODE_STORAGE_KEY } from "../utils/formatters"
import { cn } from "../utils/cn"

export default function ModeSwitch() {
  const { state, dispatch } = useApp()
  const { mode, modeLoaded, job } = state

  const isDisabled = !!job?.local_job_id

  const handleModeChange = (newMode) => {
    if (isDisabled) return
    dispatch({ type: "SET_MODE", payload: newMode })
    dispatch({ type: "SET_STEP_INDEX", payload: 0 })
    if (typeof window !== "undefined") {
      window.localStorage.setItem(MODE_STORAGE_KEY, newMode)
    }
  }

  if (!modeLoaded) return null

  return (
    <div className={cn("flex items-center bg-muted p-1 rounded-lg", isDisabled && "opacity-50 pointer-events-none cursor-not-allowed")}>
      <button
        disabled={isDisabled}
        className={cn(
          "px-3 py-1.5 text-sm font-medium rounded-md transition-all",
          mode === "developer"
            ? "bg-background text-foreground shadow-sm"
            : "text-muted-foreground hover:text-foreground hover:bg-background/50"
        )}
        onClick={() => handleModeChange("developer")}
      >
        Developer
      </button>
      <button
        disabled={isDisabled}
        className={cn(
          "px-3 py-1.5 text-sm font-medium rounded-md transition-all",
          mode === "user"
            ? "bg-background text-foreground shadow-sm"
            : "text-muted-foreground hover:text-foreground hover:bg-background/50"
        )}
        onClick={() => handleModeChange("user")}
      >
        User
      </button>
    </div>
  )
}
