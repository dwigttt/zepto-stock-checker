import { Fragment } from "react"

import { Badge } from "@/components/ui/badge"
import {
  Item,
  ItemActions,
  ItemContent,
  ItemDescription,
  ItemGroup,
  ItemSeparator,
  ItemTitle,
} from "@/components/ui/item"
import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"
import type { StoreResult } from "@/lib/api"

export const STATUS_LABEL: Record<StoreResult["status"], string> = {
  in_stock: "In stock",
  out_of_stock: "Out of stock",
  not_carried: "Not carried",
  error: "Check failed",
}

export const STATUS_VARIANT: Record<
  StoreResult["status"],
  "default" | "secondary" | "outline" | "destructive"
> = {
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
  onSelect: (result: StoreResult) => void
}

export function ResultsList({
  results,
  selectedId,
  cheapestId,
  onSelect,
}: ResultsListProps) {
  return (
    <ItemGroup>
      {results.map((r, i) => (
        <Fragment key={r.store.id}>
          {i > 0 && <ItemSeparator />}
          <Item asChild size="sm">
            <button
              type="button"
              id={`store-${r.store.id}`}
              onClick={() => onSelect(r)}
              className={cn(
                "w-full text-left transition-colors animate-in fade-in-0 slide-in-from-bottom-1 hover:bg-muted/50",
                r.store.id === selectedId && "bg-muted"
              )}
            >
              <ItemContent>
                <ItemTitle>
                  {prettyStoreName(r.store.name)}
                  {r.store.id === cheapestId && (
                    <Badge variant="outline">Cheapest</Badge>
                  )}
                </ItemTitle>
                <ItemDescription>
                  {r.store.city ? `${r.store.city} · ` : ""}
                  {r.distance_km} km away
                </ItemDescription>
              </ItemContent>
              <ItemActions>
                {r.status === "in_stock" && r.price != null && (
                  <span className="text-sm font-semibold tabular-nums">
                    ₹{formatPrice(r.price)}
                  </span>
                )}
                <Badge variant={STATUS_VARIANT[r.status]}>
                  {STATUS_LABEL[r.status]}
                </Badge>
              </ItemActions>
            </button>
          </Item>
        </Fragment>
      ))}
    </ItemGroup>
  )
}

export function ResultsSkeleton({ rows }: { rows: number }) {
  return (
    <ItemGroup>
      {Array.from({ length: rows }).map((_, i) => (
        <Fragment key={i}>
          {i > 0 && <ItemSeparator />}
          <Item size="sm">
            <ItemContent className="gap-1.5">
              <Skeleton className="h-4 w-40" />
              <Skeleton className="h-3 w-24" />
            </ItemContent>
            <ItemActions>
              <Skeleton className="h-5 w-20 rounded-full" />
            </ItemActions>
          </Item>
        </Fragment>
      ))}
    </ItemGroup>
  )
}
