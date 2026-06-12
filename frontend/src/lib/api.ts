export interface ProductInfo {
  status: "in_stock" | "out_of_stock" | "not_carried" | "error"
  name: string | null
  brand: string | null
  image_url: string | null
  price: number | null
  mrp: number | null
  available_quantity: number | null
}

export interface ResolveResponse {
  pvid: string
  product: ProductInfo
}

export interface GeocodeResponse {
  lat: number
  lng: number
  label: string
}

export interface PlaceSuggestion {
  place_id: string
  description: string
  main_text: string
  secondary_text: string
}

export interface HomeResult {
  serviceable: boolean
  store_name: string | null
  city: string | null
  eta_minutes: number | null
  product: ProductInfo | null
}

export interface StoreResult {
  store: {
    id: string
    name: string | null
    city: string | null
    lat: number
    lng: number
  }
  distance_km: number
  status: ProductInfo["status"]
  price: number | null
  mrp: number | null
}

export interface SearchSummary {
  in_stock: number
  out_of_stock: number
  not_carried: number
  error: number
  stores: number
}

// -- access token ----------------------------------------------------------
// A private instance is opened via an invite link carrying ?token=…; we stash
// it, strip it from the URL (so it doesn't linger in bookmarks/screenshots),
// and send it on every call. EventSource can't set headers, so search reads it
// from the query string instead — see tokenQuery().

const TOKEN_KEY = "zf_token"

function initToken(): string | null {
  const url = new URL(window.location.href)
  const fromUrl = url.searchParams.get("token")
  if (fromUrl) {
    localStorage.setItem(TOKEN_KEY, fromUrl)
    url.searchParams.delete("token")
    window.history.replaceState({}, "", url.pathname + url.search + url.hash)
    return fromUrl
  }
  return localStorage.getItem(TOKEN_KEY)
}

let token = initToken()

export function getToken(): string | null {
  return token
}

export function setToken(value: string): void {
  token = value.trim() || null
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

export function tokenQuery(): string {
  return token ? `&token=${encodeURIComponent(token)}` : ""
}

export interface AppConfig {
  auth_required: boolean
  max_radius_km: number
}

export function getConfig() {
  return request<AppConfig>("/api/config")
}

async function request<T>(input: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (token) headers.set("X-App-Token", token)
  const res = await fetch(input, { ...init, headers })
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      detail = (await res.json()).detail ?? detail
    } catch {
      // non-JSON error body
    }
    throw new Error(detail)
  }
  return res.json()
}

export function resolveLink(
  url: string,
  coords?: { lat: number; lng: number } | null
) {
  return request<ResolveResponse>("/api/resolve", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, lat: coords?.lat, lng: coords?.lng }),
  })
}

export function geocode(q: string) {
  return request<GeocodeResponse>(`/api/geocode?q=${encodeURIComponent(q)}`)
}

export function suggestPlaces(q: string, signal?: AbortSignal) {
  return request<{ suggestions: PlaceSuggestion[] }>(
    `/api/suggest?q=${encodeURIComponent(q)}`,
    { signal }
  )
}

export function placeDetails(placeId: string, label: string) {
  return request<GeocodeResponse>(
    `/api/place?place_id=${encodeURIComponent(placeId)}&label=${encodeURIComponent(label)}`
  )
}
