from typing import Literal

from pydantic import BaseModel, Field


class SearchParams(BaseModel):
    """User-facing filters for a Grailed scrape run."""

    query: str = ""
    department: str | None = None  # "menswear" | "womenswear" | None
    category: str | None = None  # e.g. "tops", "footwear"; matches Algolia `category` facet
    category_path: str | None = None  # optional dotted path, e.g. "tops.short_sleeve_shirts"
    condition: str | None = None  # "is_new" | "is_gently_used" | "is_used" | "is_worn" | None
    location: str | None = None  # "United States" | "Europe" | "Asia" | ...
    strata: str | None = None  # "basic" | "grailed" | "hype" | "sartorial" | None
    designer: str | None = None  # matches `designers.name` facet
    min_price_usd: int = 0
    max_price_usd: int = 1_000_000
    live_limit: int = 5
    sold_limit: int = 3
    include_sold: bool = True
    fetch_descriptions: bool = False


class EVDistribution(BaseModel):
    q10: float
    q50: float
    q90: float


class SellerBadges(BaseModel):
    verified: bool
    trusted_seller: bool
    quick_responder: bool
    speedy_shipper: bool


class Seller(BaseModel):
    seller_name: str
    reviews_count: int
    transactions_count: int
    items_for_sale_count: int
    posted_at_unix: int
    badges: SellerBadges


class LivePrice(BaseModel):
    listing_price_usd: int
    shipping_price_usd: int


class SoldPrice(BaseModel):
    sold_price_usd: int
    shipping_price_usd: int


class LiveListing(BaseModel):
    id: str
    url: str
    designer: str
    name: str
    size: str
    condition_raw: str
    location: str
    color: str
    image_urls: list[str]
    price: LivePrice
    seller: Seller
    description: str


class SoldListing(BaseModel):
    id: str
    url: str
    designer: str
    name: str
    size: str
    condition_raw: str
    location: str
    color: str
    image_urls: list[str]
    price: SoldPrice
    sold_at_unix: int
    seller: Seller
    description: str


class GrailedResultRow(BaseModel):
    live_listing: LiveListing
    sold_comparables: list[SoldListing] = Field(default_factory=list)


class ScrapeMetadata(BaseModel):
    query: str
    categories: list[str]
    live_limit_requested: int
    sold_limit_requested: int
    scraped_at_unix: int
    total_live_found: int


class GrailedScrapeResult(BaseModel):
    """Root object emitted by the scraper."""

    metadata: ScrapeMetadata
    results: list[GrailedResultRow] = Field(default_factory=list)


class TrendPoint(BaseModel):
    day_unix: int
    intensity: int


class TrendSeries(BaseModel):
    range: Literal["7d", "30d", "90d"]
    points: list[TrendPoint] = Field(default_factory=list)


class RelatedQuery(BaseModel):
    query: str
    value: int
    kind: Literal["rising", "top"]
    is_breakout: bool


class HypeEvidence(BaseModel):
    related: list[RelatedQuery] = Field(default_factory=list)


class HypeResult(BaseModel):
    term: str
    score: float | None
    confidence: Literal["high", "medium", "low", "insufficient"]
    series_30d: TrendSeries
    series_7d: TrendSeries | None = None
    series_90d: TrendSeries | None = None
    evidence: HypeEvidence
    fetched_at_unix: int


class Recommendation(BaseModel):
    """One ranked recommendation. Single shape returned by both ``/search``
    and ``/recommendations`` so the frontend writes one renderer.

    Typed top-level fields (``edge_usd``, ``p_sell``, ``q50``, ``cost``,
    ``confidence``) are extracted from the raw EV dicts at construction time
    so the frontend can sort/filter without digging into JSONB.

    ``valuation`` and ``sell_probability`` stay as ``dict`` so the math owner
    can add fields additively (see EV_MODEL_SPEC.md) without API changes.
    Sold comparables are intentionally NOT included — the valuation summarizes
    them and the raw comps aren't useful for display.
    """

    item_id: str
    scraped_at_unix: int
    query: str
    edge_usd: float
    p_sell: float
    q50: float
    cost: float
    confidence: str
    valuation: dict
    sell_probability: dict
    live_listing: LiveListing


class SearchResponse(BaseModel):
    """Full ranked search response. Returned by ``orchestrator.run_search``."""

    metadata: ScrapeMetadata
    items: list[Recommendation] = Field(default_factory=list)