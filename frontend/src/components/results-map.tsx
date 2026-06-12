import { useEffect } from "react"

import L from "leaflet"
import { Circle, CircleMarker, MapContainer, Popup, TileLayer, useMap } from "react-leaflet"
import "leaflet/dist/leaflet.css"

import { cn } from "@/lib/utils"
import type { StoreResult } from "@/lib/api"

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
  selectedId: string | null
  onSelect: (result: StoreResult) => void
  className?: string
}

export function ResultsMap({ lat, lng, radiusKm, results, selectedId, onSelect, className }: ResultsMapProps) {
  return (
    <MapContainer
      center={[lat, lng]}
      zoom={12}
      className={cn("z-0 h-72 w-full", className)}
      scrollWheelZoom={false}
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <FitToRadius lat={lat} lng={lng} radiusKm={radiusKm} />
      <FlyToSelected results={results} selectedId={selectedId} />
      <Circle
        center={[lat, lng]}
        radius={radiusKm * 1000}
        pathOptions={{ color: "#6366f1", weight: 1, fillOpacity: 0.04 }}
      />
      <CircleMarker
        center={[lat, lng]}
        radius={7}
        pathOptions={{ color: "#4f46e5", fillColor: "#6366f1", fillOpacity: 1 }}
      >
        <Popup>Your location</Popup>
      </CircleMarker>
      {results.map((r) => (
        <CircleMarker
          key={r.store.id}
          center={[r.store.lat, r.store.lng]}
          radius={r.store.id === selectedId ? 12 : 9}
          pathOptions={{
            color: r.store.id === selectedId ? "#1d4ed8" : "#ffffff",
            weight: 2,
            fillColor: STATUS_COLORS[r.status],
            fillOpacity: 0.95,
          }}
          eventHandlers={{ click: () => onSelect(r) }}
        >
          <Popup>
            <span className="font-medium">{r.store.name ?? "Store"}</span>
            <br />
            {r.distance_km} km · {r.status === "in_stock" ? `In stock — ₹${r.price}` : "Not available"}
          </Popup>
        </CircleMarker>
      ))}
    </MapContainer>
  )
}
