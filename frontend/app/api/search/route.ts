import { NextRequest, NextResponse } from "next/server"

export async function POST(request: NextRequest) {
  const apiUrl = process.env.LIVE_URL?.trim().replace(/\/+$/, '')
  const apiKey = process.env.API_KEY?.trim()

  if (!apiUrl || !apiKey) {
    return NextResponse.json(
      { error: "Backend API not configured. Please set LIVE_URL and API_KEY environment variables." },
      { status: 500 }
    )
  }

  try {
    const body = await request.json()
    
    const response = await fetch(`${apiUrl}/search`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    })

    if (!response.ok) {
      const errorText = await response.text().catch(() => "")
      console.error("[v0] Search error:", response.status, errorText)
      return NextResponse.json(
        { error: `Backend returned ${response.status}: ${errorText}` },
        { status: response.status }
      )
    }

    const data = await response.json()
    return NextResponse.json(data)
  } catch (error) {
    console.error("[v0] Error searching:", error)
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Failed to search" },
      { status: 500 }
    )
  }
}
