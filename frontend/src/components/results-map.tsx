import { useEffect } from "react"

import L from "leaflet"
import { Circle, CircleMarker, MapContainer, Popup, TileLayer, useMap } from "react-leaflet"
import "leaflet/dist/leaflet.css"

import { cn } from "@/lib/utils"
import { useTheme } from "@/components/theme-provider"
import { STATUS_LABEL } from "@/components/results-list"
import type { StoreResult } from "@/lib/api"

// Carto basemaps track the app theme: Positron (light) / Dark Matter (dark).
// Cleaner than default OSM tiles and they actually have a dark variant.
const TILE_URL = {
  light: "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
  dark: "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
} as const
const TILE_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>'

const STATUS_COLORS: Record<StoreResult["status"], string> = {
  in_stock: "#16a34a",
  out_of_stock: "#9ca3af",
  not_carried: "#d1d5db",
  error: "#f87171",
}

function FitToRadius({ lat, lng, radiusKm }: { lat: number; lng: number; radiusKm: number }) {
  const map = useMap()
  useEffect(() => {
    map.fitBounds(L.latLng(lat, lng).toBounds(radiusKm * 2000))
  }, [map, lat, lng, radiusKm])
  return null
}

function FlyToSelected({ results, selectedId }: { results: StoreResult[]; selectedId: string | null }) {
  const map = useMap()
  useEffect(() => {
    const r = results.find((x) => x.store.id === selectedId)
    if (r) {
      map.flyTo([r.store.lat, r.store.lng], Math.max(map.getZoom(), 13), { duration: 0.6 })
    }
  }, [map, results, selectedId])
  return null
}

interface ResultsMapProps {
  lat: number
  lng: number
  radiusKm: number
  results: StoreResult[]
  // Stock at the user's own location (incl. via the backup store) — so the
  // "Your location" marker can match the banner instead of looking unavailable.
  homeStatus: StoreResult["status"] | null
  homePrice: number | null
  selectedId: string | null
  onSelect: (result: StoreResult) => void
  className?: string
}

export function ResultsMap({ lat, lng, radiusKm, results, homeStatus, homePrice, selectedId, onSelect, className }: ResultsMapProps) {
  const { resolvedTheme } = useTheme()
  return (
    <MapContainer
      center={[lat, lng]}
      zoom={12}
      className={cn("z-0 h-72 w-full", className)}
      scrollWheelZoom={false}
    >
      <TileLayer
        key={resolvedTheme}
        attribution={TILE_ATTRIBUTION}
        url={TILE_URL[resolvedTheme]}
      />
      <FitToRadius lat={lat} lng={lng} radiusKm={radiusKm} />
      <FlyToSelected results={results} selectedId={selectedId} />
      <Circle
        center={[lat, lng]}
        radius={radiusKm * 1000}
        pathOptions={{ color: "#7c3aed", weight: 1, fillOpacity: 0.04 }}
      />
      <CircleMarker
        center={[lat, lng]}
        radius={8}
        pathOptions={{
          // Purple ring keeps it identifiable as "you"; fill reflects stock at
          // your location (green when in stock, incl. via the backup store).
          color: "#6d28d9",
          weight: 3,
          fillColor: homeStatus ? STATUS_COLORS[homeStatus] : "#7c3aed",
          fillOpacity: 1,
        }}
      >
        <Popup>
          <span className="font-medium">Your location</span>
          {homeStatus && (
            <>
              <br />
              {homeStatus === "in_stock"
                ? `In stock — ₹${homePrice}`
                : STATUS_LABEL[homeStatus]}
            </>
          )}
        </Popup>
      </CircleMarker>
      {results.map((r) => (
        <CircleMarker
          key={r.store.id}
          center={[r.store.lat, r.store.lng]}
          radius={r.store.id === selectedId ? 12 : 9}
          pathOptions={{
            color: r.store.id === selectedId ? "#6d28d9" : "#ffffff",
            weight: 2,
            fillColor: STATUS_COLORS[r.status],
            fillOpacity: 0.95,
          }}
          eventHandlers={{ click: () => onSelect(r) }}
        >
          <Popup>
            <span className="font-medium">{r.store.name ?? "Store"}</span>
            <br />
            {r.distance_km} km · {r.status === "in_stock" ? `In stock — ₹${r.price}` : STATUS_LABEL[r.status]}
          </Popup>
        </CircleMarker>
      ))}
    </MapContainer>
  )
}
