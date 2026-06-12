import { useEffect, useMemo, useRef, useState } from "react"

import { HugeiconsIcon } from "@hugeicons/react"
import {
  CancelCircleIcon,
  CheckmarkCircle02Icon,
  LocationOffline01Icon,
  PackageRemoveIcon,
  Refresh01Icon,
  Search01Icon,
} from "@hugeicons/core-free-icons"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty"
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field"
import {
  InputGroup,
  InputGroupAddon,
  InputGroupInput,
} from "@/components/ui/input-group"
import { Progress } from "@/components/ui/progress"
import { Slider } from "@/components/ui/slider"
import { Spinner } from "@/components/ui/spinner"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { LocationSearch } from "@/components/location-search"
import { ResultsList, formatPrice, prettyStoreName } from "@/components/results-list"
import { ResultsMap } from "@/components/results-map"
import { useSearch } from "@/hooks/use-search"
import { resolveLink, type GeocodeResponse, type ResolveResponse } from "@/lib/api"

interface RecentProduct {
  pvid: string
  name: string | null
  image_url: string | null
  link: string
}

function load<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key)
    return raw ? (JSON.parse(raw) as T) : null
  } catch {
    return null
  }
}

function save(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // storage full/blocked — persistence is best-effort
  }
}

function looksResolvable(text: string): boolean {
  return /\/pvid\/[0-9a-fA-F-]{36}/.test(text) || (/zepto/i.test(text) && /https?:\/\//.test(text))
}

const RADIUS_PRESETS = [5, 10, 25, 50]

export function App() {
  const [linkText, setLinkText] = useState("")
  const [resolving, setResolving] = useState(false)
  const [resolveError, setResolveError] = useState<string | null>(null)
  const [resolved, setResolved] = useState<ResolveResponse | null>(null)
  const resolvedFor = useRef<string | null>(null)

  const [recent, setRecent] = useState<RecentProduct[]>(() => load("zf.recent") ?? [])
  const [coords, setCoordsState] = useState<GeocodeResponse | null>(() => load("zf.coords"))
  const [radiusKm, setRadiusState] = useState<number>(() => load("zf.radius") ?? 10)

  const [onlyInStock, setOnlyInStock] = useState(false)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [lastRunKey, setLastRunKey] = useState<string | null>(null)

  const { state, start, cancel } = useSearch()
  const autoRan = useRef(false)

  const setCoords = (c: GeocodeResponse | null) => {
    setCoordsState(c)
    if (c) save("zf.coords", c)
  }
  const setRadius = (km: number) => {
    setRadiusState(km)
    save("zf.radius", km)
  }

  async function doResolve(text: string) {
    setResolving(true)
    setResolveError(null)
    try {
      const result = await resolveLink(text, coords)
      setResolved(result)
      resolvedFor.current = text
      setRecent((prev) => {
        const next: RecentProduct[] = [
          {
            pvid: result.pvid,
            name: result.product.name,
            image_url: result.product.image_url,
            link: text,
          },
          ...prev.filter((p) => p.pvid !== result.pvid),
        ].slice(0, 4)
        save("zf.recent", next)
        return next
      })
    } catch (e) {
      setResolved(null)
      setResolveError(e instanceof Error ? e.message : "Couldn't read that link.")
    } finally {
      setResolving(false)
    }
  }

  // Auto-resolve as soon as the pasted text looks like a Zepto link.
  useEffect(() => {
    const text = linkText.trim()
    if (!text || resolving || resolvedFor.current === text || !looksResolvable(text)) return
    const timer = setTimeout(() => doResolve(text), 350)
    return () => clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [linkText, resolving])

  const searchKey =
    resolved && coords
      ? `${resolved.pvid}|${coords.lat.toFixed(4)},${coords.lng.toFixed(4)}|${radiusKm}`
      : null

  function runSearch(force: boolean) {
    if (!resolved || !coords || !searchKey) return
    setLastRunKey(searchKey)
    setSelectedId(null)
    setOnlyInStock(false)
    start({ pvid: resolved.pvid, lat: coords.lat, lng: coords.lng, radiusKm, force })
  }

  // Kick off the first search automatically once product + location are known.
  useEffect(() => {
    if (searchKey && !autoRan.current && state.phase === "idle") {
      autoRan.current = true
      runSearch(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchKey, state.phase])

  const sortedResults = useMemo(
    () =>
      [...state.results].sort(
        (a, b) =>
          (a.status === "in_stock" ? 0 : 1) - (b.status === "in_stock" ? 0 : 1) ||
          a.distance_km - b.distance_km
      ),
    [state.results]
  )

  const inStock = useMemo(() => sortedResults.filter((r) => r.status === "in_stock"), [sortedResults])
  const cheapestId = useMemo(() => {
    let best: { id: string; price: number } | null = null
    for (const r of inStock) {
      if (r.price != null && (best === null || r.price < best.price)) {
        best = { id: r.store.id, price: r.price }
      }
    }
    return inStock.length > 1 ? (best?.id ?? null) : null
  }, [inStock])

  const visibleResults = onlyInStock ? inStock : sortedResults

  const searching = state.phase === "searching"
  const probing =
    searching && state.discovery !== null && state.discovery.probed < state.discovery.total
  const homeInStock = state.home?.product?.status === "in_stock"
  const homeOnlySearch = state.phase === "done" && homeInStock && state.results.length === 0
  const paramsChanged = lastRunKey !== null && searchKey !== null && searchKey !== lastRunKey

  function handleSelect(id: string) {
    setSelectedId(id)
    document.getElementById(`store-${id}`)?.scrollIntoView({ behavior: "smooth", block: "nearest" })
  }

  const product = resolved?.product

  return (
    <div className="mx-auto flex min-h-svh w-full max-w-xl flex-col gap-6 p-4 pb-16">
      <header className="flex flex-col gap-1 pt-2">
        <h1 className="text-2xl font-semibold tracking-tight">Zepto Finder</h1>
        <p className="text-sm text-muted-foreground">
          Paste a shared Zepto product link and see which nearby stores actually have it.
        </p>
      </header>

      <FieldGroup>
        <Field data-invalid={resolveError ? true : undefined}>
          <FieldLabel htmlFor="link">Zepto product link</FieldLabel>
          <InputGroup>
            <InputGroupInput
              id="link"
              placeholder="https://www.zepto.com/pn/…/pvid/…"
              value={linkText}
              aria-invalid={resolveError ? true : undefined}
              onChange={(e) => setLinkText(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && looksResolvable(linkText) && doResolve(linkText.trim())}
            />
            <InputGroupAddon align="inline-end">
              {resolving ? (
                <Spinner />
              ) : resolved ? (
                <HugeiconsIcon icon={CheckmarkCircle02Icon} className="text-primary" />
              ) : (
                <HugeiconsIcon icon={Search01Icon} className="text-muted-foreground" />
              )}
            </InputGroupAddon>
          </InputGroup>
          {resolveError ? (
            <FieldDescription className="text-destructive">{resolveError}</FieldDescription>
          ) : (
            <FieldDescription>
              Share any product from the Zepto app and paste the link — it loads automatically.
            </FieldDescription>
          )}
        </Field>
        {recent.length > 0 && !resolved && (
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-muted-foreground">Recent:</span>
            {recent.map((r) => (
              <button
                type="button"
                key={r.pvid}
                onClick={() => setLinkText(r.link)}
                className="flex items-center gap-2 rounded-full border bg-card py-1 pl-1 pr-3 text-xs transition-colors hover:bg-muted/50"
              >
                {r.image_url && (
                  <img src={r.image_url} alt="" className="size-6 rounded-full border object-cover" />
                )}
                <span className="max-w-36 truncate">{r.name ?? "Product"}</span>
              </button>
            ))}
          </div>
        )}
      </FieldGroup>

      {product && (
        <Card className="animate-in fade-in-0 slide-in-from-bottom-1">
          <CardContent className="flex items-center gap-4">
            {product.image_url && (
              <img
                src={product.image_url}
                alt=""
                className="size-16 shrink-0 rounded-lg border object-cover"
              />
            )}
            <div className="min-w-0 flex-1">
              <p className="truncate font-medium">{product.name}</p>
              {product.brand && <p className="text-sm text-muted-foreground">{product.brand}</p>}
            </div>
            {product.price != null && (
              <div className="flex shrink-0 flex-col items-end">
                <span className="font-semibold tabular-nums">₹{formatPrice(product.price)}</span>
                {product.mrp != null && product.mrp > product.price && (
                  <s className="text-xs text-muted-foreground tabular-nums">
                    ₹{formatPrice(product.mrp)}
                  </s>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {resolved && (
        <FieldGroup>
          <LocationSearch coords={coords} onCoords={setCoords} />
          <Field>
            <div className="flex items-center justify-between">
              <FieldLabel htmlFor="radius">Search radius</FieldLabel>
              <span className="text-sm font-medium tabular-nums">{radiusKm} km</span>
            </div>
            <Slider
              id="radius"
              min={1}
              max={50}
              step={1}
              value={[radiusKm]}
              onValueChange={(v: number[]) => setRadius(v[0])}
            />
            <ToggleGroup
              type="single"
              variant="outline"
              size="sm"
              className="w-full"
              value={String(radiusKm)}
              onValueChange={(v: string) => v && setRadius(Number(v))}
            >
              {RADIUS_PRESETS.map((km) => (
                <ToggleGroupItem key={km} value={String(km)} className="flex-1">
                  {km} km
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
          </Field>

          {searching ? (
            <Button variant="outline" onClick={cancel}>
              <HugeiconsIcon icon={CancelCircleIcon} data-icon="inline-start" />
              Cancel search
            </Button>
          ) : lastRunKey === null ? (
            <Button onClick={() => runSearch(false)} disabled={!searchKey}>
              <HugeiconsIcon icon={Search01Icon} data-icon="inline-start" />
              Check availability
            </Button>
          ) : paramsChanged ? (
            <Button onClick={() => runSearch(false)}>
              <HugeiconsIcon icon={Search01Icon} data-icon="inline-start" />
              Update results
            </Button>
          ) : (
            <Button variant="outline" onClick={() => runSearch(false)}>
              <HugeiconsIcon icon={Refresh01Icon} data-icon="inline-start" />
              Re-check stock
            </Button>
          )}
        </FieldGroup>
      )}

      {state.error && (
        <Alert variant="destructive">
          <HugeiconsIcon icon={CancelCircleIcon} />
          <AlertTitle>Search failed</AlertTitle>
          <AlertDescription>{state.error}</AlertDescription>
        </Alert>
      )}

      {state.home && (
        <Alert className="animate-in fade-in-0 slide-in-from-bottom-1">
          <HugeiconsIcon
            icon={
              homeInStock
                ? CheckmarkCircle02Icon
                : state.home.serviceable
                  ? PackageRemoveIcon
                  : LocationOffline01Icon
            }
          />
          <AlertTitle>
            {homeInStock
              ? "In stock at your location 🎉"
              : state.home.serviceable
                ? "Not available at your location"
                : "Zepto doesn't deliver to this exact spot"}
          </AlertTitle>
          <AlertDescription>
            {state.home.serviceable ? (
              <>
                Your store: {prettyStoreName(state.home.store_name)}
                {state.home.eta_minutes != null && ` · ~${state.home.eta_minutes} min delivery`}
                {homeInStock && state.home.product?.price != null && (
                  <> · ₹{formatPrice(state.home.product.price)}</>
                )}
              </>
            ) : (
              "Checking stores in the area instead."
            )}
          </AlertDescription>
        </Alert>
      )}

      {homeOnlySearch && (
        <Button variant="outline" onClick={() => runSearch(true)}>
          <HugeiconsIcon icon={Search01Icon} data-icon="inline-start" />
          Search nearby stores anyway
        </Button>
      )}

      {searching && (
        <Card className="animate-in fade-in-0">
          <CardContent className="flex flex-col gap-2 text-sm">
            <div className="flex items-center gap-2">
              <Spinner />
              <span>
                {probing && state.discovery
                  ? `Mapping Zepto stores in this area… ${state.discovery.probed}/${state.discovery.total}`
                  : state.totalStores > 0
                    ? `Checking stock at ${state.results.length}/${state.totalStores} stores…`
                    : "Checking your store…"}
              </span>
            </div>
            {probing && state.discovery && (
              <>
                <Progress
                  value={(state.discovery.probed / Math.max(1, state.discovery.total)) * 100}
                />
                <p className="text-xs text-muted-foreground">
                  First search in a new area takes a while — it's instant once mapped.
                </p>
              </>
            )}
          </CardContent>
        </Card>
      )}

      {sortedResults.length > 0 && (
        <div className="flex items-center justify-between gap-2">
          <p className="text-sm text-muted-foreground">
            In stock at {inStock.length} of {sortedResults.length} stores
          </p>
          <ToggleGroup
            type="single"
            variant="outline"
            size="sm"
            value={onlyInStock ? "in" : "all"}
            onValueChange={(v: string) => v && setOnlyInStock(v === "in")}
          >
            <ToggleGroupItem value="all">All</ToggleGroupItem>
            <ToggleGroupItem value="in">In stock</ToggleGroupItem>
          </ToggleGroup>
        </div>
      )}

      {coords && (searching || state.phase === "done") && !homeOnlySearch && (
        <ResultsMap
          lat={coords.lat}
          lng={coords.lng}
          radiusKm={radiusKm}
          results={visibleResults}
          selectedId={selectedId}
          onSelect={handleSelect}
        />
      )}

      {visibleResults.length > 0 && (
        <ResultsList
          results={visibleResults}
          selectedId={selectedId}
          cheapestId={cheapestId}
          onSelect={handleSelect}
        />
      )}

      {state.phase === "done" && state.summary && !homeOnlySearch && inStock.length === 0 && (
        <Empty>
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <HugeiconsIcon icon={PackageRemoveIcon} />
            </EmptyMedia>
            <EmptyTitle>Not available nearby</EmptyTitle>
            <EmptyDescription>
              None of the {state.summary.stores} stores within {radiusKm} km have this in stock
              right now. Try a bigger radius.
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      )}
    </div>
  )
}

export default App
