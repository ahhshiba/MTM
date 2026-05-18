import "./globals.css"
import { Fraunces, Space_Grotesk } from "next/font/google"
import { AppProvider } from "./context/AppContext"

const display = Fraunces({
  subsets: ["latin"],
  variable: "--font-display",
  weight: ["400", "600", "700"],
})

const body = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-body",
  weight: ["400", "500", "600"],
})

export const metadata = {
  title: "MTM OCR Pipeline",
  description: "Local OCR and VLM pipeline console",
}

export default function RootLayout({ children }) {
  return (
    <html lang="en" className={`${display.variable} ${body.variable}`}>
      <body>
        <AppProvider>
          {children}
        </AppProvider>
      </body>
    </html>
  )
}
