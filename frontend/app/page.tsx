"use client"

import { useState, useMemo, useEffect } from "react"
import { Search, ChevronDown, X, ExternalLink, Loader2 } from "lucide-react"
import Image from "next/image"

// Backend API types based on the Python backend (see docs/code-brown--backend-handoff.md)
interface LiveListing {
  title: string
  designer: string
  size: string
  condition: string
  color: string
  images: string[]
  description: string
  price_cents: number
  url: string
  seller?: string
  category?: string
}

interface Recommendation {
  item_id: string
  query: string
  scraped_at_unix: number
  edge_usd: number
  p_sell: number
  q50: number
  cost: number
  confidence: "high" | "medium" | "low" | "insufficient"
  live_listing: LiveListing
  valuation?: Record<string, unknown>
  sell_probability?: Record<string, unknown>
}

interface Listing {
  id: string
  title: string
  designer: string
  shortDescription: string
  longDescription: string
  image: string
  price: number
  profit: number
  profitPercent: number
  category: string
  link: string
  confidence: string
  sellProbability: number
  condition: string
  size: string
  medianSalePrice: number
  // Distribution data for the curve
  q10: number
  q25: number
  q50: number
  q75: number
  q90: number
}

function transformRecommendation(rec: Recommendation): Listing {
  const price = rec.cost || 0
  const profit = rec.edge_usd || 0
  const profitPercent = price > 0 ? Math.round((profit / price) * 100) : 0
  const pSell = rec.p_sell || 0
  
  const listing = (rec.live_listing && typeof rec.live_listing === 'object') ? rec.live_listing : {} as LiveListing
  const title = listing.title || "Unknown Item"
  const designer = listing.designer || "Unknown Designer"
  const condition = listing.condition || "Unknown"
  const size = listing.size || "N/A"
  const color = listing.color || "N/A"
  const description = listing.description || ""
  const images = listing.images || []
  const url = listing.url || "#"
  
  let category = listing.category || "Accessories"
  if (!listing.category && title) {
    const titleLower = title.toLowerCase()
    if (titleLower.includes("shoe") || titleLower.includes("sneaker") || titleLower.includes("boot") || titleLower.includes("jordan") || titleLower.includes("nike") || titleLower.includes("adidas") || titleLower.includes("guidi")) {
      category = "Shoes"
    } else if (titleLower.includes("shirt") || titleLower.includes("top") || titleLower.includes("hoodie") || titleLower.includes("jacket") || titleLower.includes("sweater") || titleLower.includes("tee")) {
      category = "Tops"
    } else if (titleLower.includes("pant") || titleLower.includes("jean") || titleLower.includes("short") || titleLower.includes("trouser")) {
      category = "Bottoms"
    }
  }

  // Extract percentiles from valuation if available
  const valuation = rec.valuation || {}
  const q10 = typeof valuation.q10 === 'number' ? valuation.q10 : (rec.q50 || 0) * 0.6
  const q25 = typeof valuation.q25 === 'number' ? valuation.q25 : (rec.q50 || 0) * 0.8
  const q50 = rec.q50 || 0
  const q75 = typeof valuation.q75 === 'number' ? valuation.q75 : (rec.q50 || 0) * 1.2
  const q90 = typeof valuation.q90 === 'number' ? valuation.q90 : (rec.q50 || 0) * 1.4
  
  return {
    id: rec.item_id || `${rec.scraped_at_unix || Date.now()}-${title.slice(0, 20)}`,
    title,
    designer,
    shortDescription: `${designer} - ${condition} condition`,
    longDescription: description || `${title} by ${designer}. Size: ${size}. Condition: ${condition}. Color: ${color}. This item has a ${Math.round(pSell * 100)}% probability of selling with a confidence level of ${rec.confidence || "unknown"}.`,
    image: images[0] || "/placeholder.svg?height=300&width=400",
    price: Math.round(price),
    profit: Math.round(profit),
    profitPercent,
    category,
    link: url,
    confidence: rec.confidence || "low",
    sellProbability: pSell,
    condition,
    size,
    medianSalePrice: Math.round(q50),
    q10: Math.round(q10),
    q25: Math.round(q25),
    q50: Math.round(q50),
    q75: Math.round(q75),
    q90: Math.round(q90),
  }
}

export default function Groogle() {
  const [showListings, setShowListings] = useState(false)
  const [searchQuery, setSearchQuery] = useState("")
  const [category, setCategory] = useState("All Categories")
  const [trendPeriod, setTrendPeriod] = useState("90 Days")
  const [sortBy, setSortBy] = useState("Most Profit")
  const [selectedListing, setSelectedListing] = useState<Listing | null>(null)
  const [openDropdown, setOpenDropdown] = useState<string | null>(null)
  const [listings, setListings] = useState<Listing[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (showListings && listings.length === 0) {
      fetchRecommendations()
    }
  }, [showListings])

  async function fetchRecommendations() {
    setLoading(true)
    setError(null)
    try {
      const response = await fetch("/api/recommendations")
      const data = await response.json()
      
      if (data.items && Array.isArray(data.items)) {
        const validItems = data.items.filter((item: Recommendation) => 
          item && typeof item === 'object'
        )
        const transformed = validItems.map((item: Recommendation) => 
          transformRecommendation(item)
        )
        setListings(transformed)
        
        if (data.items.length === 0 && data.error) {
          setError(data.error)
        }
      } else if (!response.ok || data.error) {
        throw new Error(data.error || "Failed to fetch recommendations")
      }
    } catch (err) {
      console.error("Error fetching recommendations:", err)
      setError(err instanceof Error ? err.message : "Failed to load recommendations")
    } finally {
      setLoading(false)
    }
  }

  async function handleSearch() {
    if (!searchQuery.trim()) {
      fetchRecommendations()
      return
    }
    
    setLoading(true)
    setError(null)
    setShowListings(true)
    
    try {
      const response = await fetch("/api/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: searchQuery }),
      })
      const data = await response.json()
      
      if (!response.ok) {
        throw new Error(data.error || "Search failed")
      }
      
      if (data.items && Array.isArray(data.items)) {
        const validItems = data.items.filter((item: Recommendation) => 
          item && typeof item === 'object'
        )
        const transformed = validItems.map((item: Recommendation) => 
          transformRecommendation(item)
        )
        setListings(transformed)
      }
    } catch (err) {
      console.error("Error searching:", err)
      setError(err instanceof Error ? err.message : "Search failed")
    } finally {
      setLoading(false)
    }
  }

  const filteredListings = useMemo(() => {
    let filtered = listings.filter((listing) => {
      const matchesSearch =
        listing.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        listing.shortDescription.toLowerCase().includes(searchQuery.toLowerCase()) ||
        listing.designer.toLowerCase().includes(searchQuery.toLowerCase())
      const matchesCategory = category === "All Categories" || listing.category === category
      return matchesSearch && matchesCategory
    })

    filtered.sort((a, b) => {
      if (sortBy === "Most Profit") return b.profit - a.profit
      if (sortBy === "Hot") return b.sellProbability - a.sellProbability
      if (sortBy === "Newest") return 0
      return 0
    })

    return filtered
  }, [listings, searchQuery, category, sortBy])

  // Select first listing if none selected and listings exist
  useEffect(() => {
    if (filteredListings.length > 0 && !selectedListing) {
      setSelectedListing(filteredListings[0])
    }
  }, [filteredListings, selectedListing])

  if (!showListings) {
    return (
      <div className="min-h-screen bg-background flex flex-col items-center justify-center px-4">
        <h1
          className="text-5xl md:text-7xl font-bold text-primary tracking-wider mb-12"
          style={{
            textShadow: "0 0 20px rgba(230, 184, 0, 0.2)",
          }}
        >
          GROOGLE
        </h1>

        <div className="w-full max-w-2xl">
          <div className="relative">
            <Search className="absolute left-5 top-1/2 transform -translate-y-1/2 text-muted-foreground w-5 h-5" />
            <input
              type="text"
              placeholder="Search for investment products..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleSearch()
              }}
              className="w-full bg-secondary border border-border rounded-full py-4 pl-14 pr-6 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary"
            />
          </div>

          <button
            onClick={() => setShowListings(true)}
            className="block mx-auto mt-6 text-primary hover:underline"
          >
            or see all listings
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-background flex flex-col">
      {/* Header */}
      <header className="border-b border-border bg-card flex-shrink-0">
        <div className="flex items-center gap-4 px-6 py-4">
          <button
            onClick={() => {
              setShowListings(false)
              setSearchQuery("")
              setSelectedListing(null)
            }}
            className="text-primary font-bold text-xl tracking-wider hover:opacity-80 transition-opacity"
          >
            GROOGLE
          </button>

          <div className="flex-1 max-w-2xl mx-4">
            <div className="relative">
              <input
                type="text"
                placeholder="Search products..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleSearch()
                }}
                className="w-full bg-secondary border border-border rounded-full py-2 pl-4 pr-4 text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>
          </div>

          <button 
            onClick={handleSearch}
            className="bg-primary text-primary-foreground font-bold px-6 py-2 rounded hover:opacity-90 transition-opacity"
          >
            SEARCH
          </button>

          <Dropdown
            id="sort"
            value={sortBy}
            onChange={setSortBy}
            options={["Most Profit", "Hot", "Newest"]}
            isOpen={openDropdown === "sort"}
            onToggle={() => setOpenDropdown(openDropdown === "sort" ? null : "sort")}
          />
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar Filters */}
        <aside className="w-56 p-4 flex-shrink-0 border-r border-border overflow-y-auto">
          <FilterSection
            id="category"
            label="CATEGORY"
            value={category}
            onChange={setCategory}
            options={["All Categories", "Shoes", "Tops", "Bottoms", "Accessories"]}
            isOpen={openDropdown === "category"}
            onToggle={() => setOpenDropdown(openDropdown === "category" ? null : "category")}
          />

          <FilterSection
            id="trend"
            label="TREND PERIOD"
            value={trendPeriod}
            onChange={setTrendPeriod}
            options={["90 Days", "30 Days", "7 Days"]}
            isOpen={openDropdown === "trend"}
            onToggle={() => setOpenDropdown(openDropdown === "trend" ? null : "trend")}
          />
        </aside>

        {/* Main Content - Vertical List + Detail Panel */}
        <main className="flex-1 flex overflow-hidden">
          {loading ? (
            <div className="flex-1 flex flex-col items-center justify-center">
              <Loader2 className="w-12 h-12 text-primary animate-spin mb-4" />
              <p className="text-muted-foreground">Loading recommendations...</p>
            </div>
          ) : error ? (
            <div className="flex-1 flex flex-col items-center justify-center p-6">
              <X className="w-16 h-16 text-red-500 mb-6" />
              <h2 className="text-2xl font-bold text-foreground mb-2">Error Loading Data</h2>
              <p className="text-muted-foreground text-center max-w-md mb-8">{error}</p>
              <button
                onClick={fetchRecommendations}
                className="bg-primary text-primary-foreground font-bold px-6 py-3 rounded hover:opacity-90 transition-opacity"
              >
                TRY AGAIN
              </button>
            </div>
          ) : filteredListings.length === 0 ? (
            <div className="flex-1 flex flex-col items-center justify-center p-6">
              <Search className="w-16 h-16 text-primary mb-6" />
              <h2 className="text-2xl font-bold text-foreground mb-2">
                No Investment Opportunities Found
              </h2>
              <p className="text-muted-foreground text-center max-w-md mb-8">
                We couldn&apos;t find any products matching your criteria.
              </p>
              <div className="flex gap-4">
                <button
                  onClick={() => {
                    setCategory("All Categories")
                    setSearchQuery("")
                  }}
                  className="border-2 border-primary text-primary font-bold px-6 py-3 rounded hover:bg-primary hover:text-primary-foreground transition-colors"
                >
                  RESET FILTERS
                </button>
                <button
                  onClick={() => {
                    setCategory("All Categories")
                    setSearchQuery("")
                    fetchRecommendations()
                  }}
                  className="bg-primary text-primary-foreground font-bold px-6 py-3 rounded hover:opacity-90 transition-opacity"
                >
                  BROWSE ALL
                </button>
              </div>
            </div>
          ) : (
            <>
              {/* Vertical Listings List */}
              <div className="w-80 border-r border-border overflow-y-auto flex-shrink-0">
                {filteredListings.map((listing) => (
                  <ListingRow
                    key={listing.id}
                    listing={listing}
                    isSelected={selectedListing?.id === listing.id}
                    onClick={() => setSelectedListing(listing)}
                  />
                ))}
              </div>

              {/* Detail Panel - Distribution Curve + Stats */}
              {selectedListing && (
                <div className="flex-1 flex flex-col overflow-y-auto p-6 gap-6">
                  {/* Top Box: Distribution Curve */}
                  <div className="bg-card border border-border rounded-lg p-6">
                    <h3 className="text-lg font-bold text-foreground mb-4">Price Distribution</h3>
                    <DistributionCurve listing={selectedListing} />
                  </div>

                  {/* Bottom Box: Description and Statistics */}
                  <div className="bg-card border border-border rounded-lg p-6 flex-1">
                    <div className="flex gap-6">
                      {/* Image */}
                      <div className="w-48 h-48 relative rounded-lg overflow-hidden flex-shrink-0 bg-secondary">
                        <Image
                          src={selectedListing.image}
                          alt={selectedListing.title}
                          fill
                          className="object-cover"
                        />
                      </div>

                      {/* Details */}
                      <div className="flex-1">
                        <h2 className="text-2xl font-bold text-foreground mb-1">{selectedListing.title}</h2>
                        <p className="text-primary font-medium mb-3">{selectedListing.designer}</p>
                        
                        <div className="flex flex-wrap gap-2 mb-4">
                          <span className="text-xs text-muted-foreground bg-secondary px-2 py-1 rounded">
                            {selectedListing.category}
                          </span>
                          <span className="text-xs text-muted-foreground bg-secondary px-2 py-1 rounded">
                            {selectedListing.condition}
                          </span>
                          <span className="text-xs text-muted-foreground bg-secondary px-2 py-1 rounded">
                            Size: {selectedListing.size}
                          </span>
                          <span className={`text-xs font-medium px-2 py-1 rounded ${
                            selectedListing.confidence === "high" 
                              ? "bg-green-500/20 text-green-500" 
                              : selectedListing.confidence === "medium"
                              ? "bg-yellow-500/20 text-yellow-500"
                              : "bg-red-500/20 text-red-500"
                          }`}>
                            {selectedListing.confidence} confidence
                          </span>
                        </div>

                        <p className="text-sm text-muted-foreground mb-4 line-clamp-3">
                          {selectedListing.longDescription}
                        </p>
                      </div>
                    </div>

                    {/* Statistics Grid */}
                    <div className="grid grid-cols-4 gap-4 mt-6 pt-6 border-t border-border">
                      <div>
                        <p className="text-xs text-muted-foreground mb-1">Price</p>
                        <p className="text-xl font-bold text-foreground">${selectedListing.price}</p>
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground mb-1">Expected Profit</p>
                        <p className="text-xl font-bold text-green-500">
                          +${selectedListing.profit}
                          <span className="text-sm ml-1">({selectedListing.profitPercent}%)</span>
                        </p>
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground mb-1">Median Sale Price</p>
                        <p className="text-xl font-bold text-foreground">${selectedListing.medianSalePrice}</p>
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground mb-1">Sell Probability</p>
                        <p className="text-xl font-bold text-foreground">{Math.round(selectedListing.sellProbability * 100)}%</p>
                      </div>
                    </div>

                    {/* View Listing Button */}
                    <a
                      href={selectedListing.link}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center justify-center gap-2 w-full bg-primary text-primary-foreground font-bold py-3 rounded-lg mt-6 hover:opacity-90 transition-opacity"
                    >
                      View Listing
                      <ExternalLink className="w-4 h-4" />
                    </a>
                  </div>
                </div>
              )}
            </>
          )}
        </main>
      </div>
    </div>
  )
}

function DistributionCurve({ listing }: { listing: Listing }) {
  const { q10, q25, q50, q75, q90, price } = listing
  
  // Calculate the position of the current price on the curve (0-100%)
  const minPrice = q10 * 0.8
  const maxPrice = q90 * 1.2
  const range = maxPrice - minPrice
  
  const pricePosition = ((price - minPrice) / range) * 100
  const q10Pos = ((q10 - minPrice) / range) * 100
  const q25Pos = ((q25 - minPrice) / range) * 100
  const q50Pos = ((q50 - minPrice) / range) * 100
  const q75Pos = ((q75 - minPrice) / range) * 100
  const q90Pos = ((q90 - minPrice) / range) * 100

  // Determine percentile of current price
  let percentile = 0
  if (price <= q10) percentile = 10
  else if (price <= q25) percentile = 10 + ((price - q10) / (q25 - q10)) * 15
  else if (price <= q50) percentile = 25 + ((price - q25) / (q50 - q25)) * 25
  else if (price <= q75) percentile = 50 + ((price - q50) / (q75 - q50)) * 25
  else if (price <= q90) percentile = 75 + ((price - q75) / (q90 - q75)) * 15
  else percentile = 90

  return (
    <div className="relative">
      {/* Percentile Label */}
      <div className="text-center mb-4">
        <span className="text-3xl font-bold text-primary">{Math.round(percentile)}th</span>
        <span className="text-muted-foreground ml-2">percentile</span>
      </div>

      {/* SVG Distribution Curve */}
      <div className="relative h-40">
        <svg viewBox="0 0 400 120" className="w-full h-full" preserveAspectRatio="none">
          {/* Bell curve path */}
          <path
            d="M 0,100 C 40,100 60,95 100,70 C 140,45 170,20 200,10 C 230,20 260,45 300,70 C 340,95 360,100 400,100"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            className="text-muted-foreground"
          />
          
          {/* Filled area under curve */}
          <path
            d="M 0,100 C 40,100 60,95 100,70 C 140,45 170,20 200,10 C 230,20 260,45 300,70 C 340,95 360,100 400,100 L 400,120 L 0,120 Z"
            fill="currentColor"
            className="text-primary/10"
          />

          {/* Percentile markers */}
          {[
            { pos: q10Pos, label: "10th", value: q10 },
            { pos: q25Pos, label: "25th", value: q25 },
            { pos: q50Pos, label: "50th", value: q50 },
            { pos: q75Pos, label: "75th", value: q75 },
            { pos: q90Pos, label: "90th", value: q90 },
          ].map((marker, i) => (
            <g key={i}>
              <line
                x1={marker.pos * 4}
                y1="100"
                x2={marker.pos * 4}
                y2="110"
                stroke="currentColor"
                strokeWidth="1"
                className="text-muted-foreground"
              />
            </g>
          ))}

          {/* Current price marker */}
          <line
            x1={Math.min(Math.max(pricePosition, 0), 100) * 4}
            y1="0"
            x2={Math.min(Math.max(pricePosition, 0), 100) * 4}
            y2="100"
            stroke="currentColor"
            strokeWidth="2"
            strokeDasharray="4"
            className="text-primary"
          />
          <circle
            cx={Math.min(Math.max(pricePosition, 0), 100) * 4}
            cy="50"
            r="6"
            fill="currentColor"
            className="text-primary"
          />
        </svg>

        {/* Price labels */}
        <div className="flex justify-between text-xs text-muted-foreground mt-2">
          <span>${q10}</span>
          <span>${q25}</span>
          <span className="font-bold text-foreground">${q50}</span>
          <span>${q75}</span>
          <span>${q90}</span>
        </div>
      </div>

      {/* Current Price Legend */}
      <div className="flex items-center justify-center gap-4 mt-4 text-sm">
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded-full bg-primary"></div>
          <span className="text-muted-foreground">Your Price: <span className="text-foreground font-bold">${price}</span></span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-3 h-0.5 bg-muted-foreground"></div>
          <span className="text-muted-foreground">Market Distribution</span>
        </div>
      </div>
    </div>
  )
}

function ListingRow({ listing, isSelected, onClick }: { listing: Listing; isSelected: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`w-full flex items-center gap-3 p-3 border-b border-border hover:bg-secondary/50 transition-colors text-left ${
        isSelected ? "bg-secondary border-l-2 border-l-primary" : ""
      }`}
    >
      {/* Thumbnail */}
      <div className="w-16 h-16 relative rounded overflow-hidden flex-shrink-0 bg-secondary">
        <Image
          src={listing.image}
          alt={listing.title}
          fill
          className="object-cover"
        />
      </div>

      {/* Info */}
      <div className="flex-1 min-w-0">
        <h3 className="font-medium text-foreground text-sm line-clamp-1">{listing.title}</h3>
        <p className="text-xs text-muted-foreground line-clamp-1">{listing.shortDescription}</p>
        <p className="text-sm font-bold text-green-500 mt-1">+${listing.profit}</p>
      </div>
    </button>
  )
}

function FilterSection({
  id,
  label,
  value,
  onChange,
  options,
  isOpen,
  onToggle,
}: {
  id: string
  label: string
  value: string
  onChange: (value: string) => void
  options: string[]
  isOpen: boolean
  onToggle: () => void
}) {
  return (
    <div className="mb-6">
      <p className="text-primary text-sm font-bold tracking-wider mb-3">{label}</p>
      <div className="relative">
        <button
          onClick={onToggle}
          className="w-full flex items-center justify-between bg-secondary border border-border rounded px-4 py-3 text-foreground hover:border-primary transition-colors"
        >
          <span className="text-sm">{value}</span>
          <ChevronDown className={`w-4 h-4 transition-transform ${isOpen ? "rotate-180" : ""}`} />
        </button>

        {isOpen && (
          <div className="absolute top-full left-0 right-0 mt-1 bg-secondary border border-border rounded z-10">
            {options.map((option) => (
              <button
                key={option}
                onClick={() => {
                  onChange(option)
                  onToggle()
                }}
                className={`w-full text-left px-4 py-2 text-sm hover:bg-primary hover:text-primary-foreground transition-colors ${
                  value === option ? "bg-[#0066cc] text-white" : "text-foreground"
                }`}
              >
                {option}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function Dropdown({
  id,
  value,
  onChange,
  options,
  isOpen,
  onToggle,
}: {
  id: string
  value: string
  onChange: (value: string) => void
  options: string[]
  isOpen: boolean
  onToggle: () => void
}) {
  return (
    <div className="relative">
      <button
        onClick={onToggle}
        className="flex items-center gap-2 bg-secondary border border-border rounded px-4 py-2 text-foreground hover:border-primary transition-colors"
      >
        <span>{value}</span>
        <ChevronDown className={`w-4 h-4 transition-transform ${isOpen ? "rotate-180" : ""}`} />
      </button>

      {isOpen && (
        <div className="absolute top-full right-0 mt-1 bg-secondary border border-border rounded z-10 min-w-[150px]">
          {options.map((option) => (
            <button
              key={option}
              onClick={() => {
                onChange(option)
                onToggle()
              }}
              className={`w-full text-left px-4 py-2 hover:bg-primary hover:text-primary-foreground transition-colors ${
                value === option ? "bg-[#0066cc] text-white" : "text-foreground"
              }`}
            >
              {option}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
