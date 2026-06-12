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

export interface HomeResult {
  serviceable: boolean
  store_name: string | null
  city: string | null
  eta_minutes: number | null
  product: ProductInfo | null
}

export interface StoreResult {
  store: { id: string; name: string | null; city: string | null; lat: number; lng: number }
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

async function request<T>(input: string, init?: RequestInit): Promise<T> {
  const res = await fetch(input, init)
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

export function resolveLink(url: string, coords?: { lat: number; lng: number } | null) {
  return request<ResolveResponse>("/api/resolve", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, lat: coords?.lat, lng: coords?.lng }),
  })
}

export function geocode(q: string) {
  return request<GeocodeResponse>(`/api/geocode?q=${encodeURIComponent(q)}`)
}
