import { Fragment } from "react"

import { Badge } from "@/components/ui/badge"
import { Separator } from "@/components/ui/separator"
import { cn } from "@/lib/utils"
import type { StoreResult } from "@/lib/api"

const STATUS_LABEL: Record<StoreResult["status"], string> = {
  in_stock: "In stock",
  out_of_stock: "Out of stock",
  not_carried: "Not carried",
  error: "Check failed",
}

const STATUS_VARIANT: Record<StoreResult["status"], "default" | "secondary" | "outline" | "destructive"> = {
  in_stock: "default",
  out_of_stock: "secondary",
  not_carried: "outline",
  error: "destructive",
}

export function prettyStoreName(name: string | null): string {
  // Store names come prefixed with an internal city code, e.g. "BLR-HSR Layout New".
  return (name ?? "Zepto store").replace(/^[A-Z]{2,5}[- ]\s*/, "")
}

export function formatPrice(price: number): string {
  return price % 1 === 0 ? price.toFixed(0) : price.toFixed(2)
}

interface ResultsListProps {
  results: StoreResult[]
  selectedId: string | null
  cheapestId: string | null
  onSelect: (id: string) => void
}

export function ResultsList({ results, selectedId, cheapestId, onSelect }: ResultsListProps) {
  return (
    <div className="flex flex-col overflow-hidden rounded-xl border">
      {results.map((r, i) => (
        <Fragment key={r.store.id}>
          {i > 0 && <Separator />}
          <button
            type="button"
            id={`store-${r.store.id}`}
            onClick={() => onSelect(r.store.id)}
            className={cn(
              "flex items-center gap-3 px-4 py-3 text-left transition-colors animate-in fade-in-0 slide-in-from-bottom-1 hover:bg-muted/50",
              r.store.id === selectedId && "bg-muted"
            )}
          >
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <p className="truncate text-sm font-medium">{prettyStoreName(r.store.name)}</p>
                {r.store.id === cheapestId && <Badge variant="outline">Cheapest</Badge>}
              </div>
              <p className="text-xs text-muted-foreground">
                {r.store.city ? `${r.store.city} · ` : ""}
                {r.distance_km} km away
              </p>
            </div>
            {r.status === "in_stock" && r.price != null && (
              <span className="text-sm font-semibold tabular-nums">₹{formatPrice(r.price)}</span>
            )}
            <Badge variant={STATUS_VARIANT[r.status]}>{STATUS_LABEL[r.status]}</Badge>
          </button>
        </Fragment>
      ))}
    </div>
  )
}
