import { useMemo, useState } from "react"

import { CheckCircle2, LocateFixed, MapPinOff, PackageX, Search, XCircle } from "lucide-react"

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
  InputGroupButton,
  InputGroupInput,
} from "@/components/ui/input-group"
import { Progress } from "@/components/ui/progress"
import { Slider } from "@/components/ui/slider"
import { Spinner } from "@/components/ui/spinner"
import { ResultsList, formatPrice, prettyStoreName } from "@/components/results-list"
import { ResultsMap } from "@/components/results-map"
import { useSearch } from "@/hooks/use-search"
import { geocode, resolveLink, type GeocodeResponse, type ResolveResponse } from "@/lib/api"

export function App() {
  const [linkText, setLinkText] = useState("")
  const [resolving, setResolving] = useState(false)
  const [resolveError, setResolveError] = useState<string | null>(null)
  const [resolved, setResolved] = useState<ResolveResponse | null>(null)

  const [locText, setLocText] = useState("")
  const [coords, setCoords] = useState<GeocodeResponse | null>(null)
  const [locating, setLocating] = useState(false)
  const [locError, setLocError] = useState<string | null>(null)

  const [radiusKm, setRadiusKm] = useState(10)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const { state, start } = useSearch()

  const sortedResults = useMemo(
    () =>
      [...state.results].sort(
        (a, b) =>
          (a.status === "in_stock" ? 0 : 1) - (b.status === "in_stock" ? 0 : 1) ||
          a.distance_km - b.distance_km
      ),
    [state.results]
  )

  const searching = state.phase === "searching"
  const homeInStock = state.home?.product?.status === "in_stock"
  const homeOnlySearch = state.phase === "done" && homeInStock && state.results.length === 0

  async function handleResolve() {
    if (!linkText.trim() || resolving) return
    setResolving(true)
    setResolveError(null)
    try {
      setResolved(await resolveLink(linkText, coords))
    } catch (e) {
      setResolved(null)
      setResolveError(e instanceof Error ? e.message : "Couldn't read that link.")
    } finally {
      setResolving(false)
    }
  }

  async function handleGeocode(): Promise<GeocodeResponse | null> {
    if (coords) return coords
    if (!locText.trim()) {
      setLocError("Enter a pincode or use the location button.")
      return null
    }
    setLocating(true)
    setLocError(null)
    try {
      const result = await geocode(locText.trim())
      setCoords(result)
      return result
    } catch (e) {
      setLocError(e instanceof Error ? e.message : "Couldn't find that location.")
      return null
    } finally {
      setLocating(false)
    }
  }

  function handleUseGps() {
    if (!navigator.geolocation) {
      setLocError("Geolocation isn't supported by this browser — use a pincode.")
      return
    }
    setLocating(true)
    setLocError(null)
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setCoords({
          lat: pos.coords.latitude,
          lng: pos.coords.longitude,
          label: "Current location (GPS)",
        })
        setLocText("")
        setLocating(false)
      },
      () => {
        setLocError("Location access denied — enter a pincode instead.")
        setLocating(false)
      },
      { enableHighAccuracy: true, timeout: 10_000 }
    )
  }

  async function handleSearch(force: boolean) {
    if (!resolved) return
    const where = await handleGeocode()
    if (!where) return
    setSelectedId(null)
    start({ pvid: resolved.pvid, lat: where.lat, lng: where.lng, radiusKm, force })
  }

  const product = resolved?.product

  return (
    <div className="mx-auto flex min-h-svh w-full max-w-xl flex-col gap-6 p-4 pb-16">
      <header className="flex flex-col gap-1 pt-2">
        <h1 className="text-2xl font-semibold tracking-tight">Zepto Finder</h1>
        <p className="text-sm text-muted-foreground">
          Paste a shared Zepto product link, set your location, and see which nearby stores
          actually have it in stock.
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
              onKeyDown={(e) => e.key === "Enter" && handleResolve()}
            />
            <InputGroupAddon align="inline-end">
              <InputGroupButton onClick={handleResolve} disabled={resolving || !linkText.trim()}>
                {resolving ? <Spinner /> : "Find"}
              </InputGroupButton>
            </InputGroupAddon>
          </InputGroup>
          {resolveError ? (
            <FieldDescription className="text-destructive">{resolveError}</FieldDescription>
          ) : (
            <FieldDescription>
              Share any product from the Zepto app and paste the link here.
            </FieldDescription>
          )}
        </Field>
      </FieldGroup>

      {product && (
        <Card>
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
          <Field data-invalid={locError ? true : undefined}>
            <FieldLabel htmlFor="loc">Your location</FieldLabel>
            <InputGroup>
              <InputGroupInput
                id="loc"
                placeholder="Pincode or locality"
                value={locText}
                aria-invalid={locError ? true : undefined}
                onChange={(e) => {
                  setLocText(e.target.value)
                  setCoords(null)
                }}
                onKeyDown={(e) => e.key === "Enter" && handleGeocode()}
              />
              <InputGroupAddon align="inline-end">
                <InputGroupButton
                  aria-label="Use my current location"
                  onClick={handleUseGps}
                  disabled={locating}
                >
                  {locating ? <Spinner /> : <LocateFixed />}
                </InputGroupButton>
              </InputGroupAddon>
            </InputGroup>
            {locError ? (
              <FieldDescription className="text-destructive">{locError}</FieldDescription>
            ) : coords ? (
              <FieldDescription>Searching around: {coords.label}</FieldDescription>
            ) : (
              <FieldDescription>Used to find your Zepto store and nearby ones.</FieldDescription>
            )}
          </Field>
          <Field>
            <FieldLabel htmlFor="radius">Search radius: {radiusKm} km</FieldLabel>
            <Slider
              id="radius"
              min={1}
              max={50}
              step={1}
              value={[radiusKm]}
              onValueChange={(v: number[]) => setRadiusKm(v[0])}
            />
          </Field>
          <Button onClick={() => handleSearch(false)} disabled={searching || locating}>
            {searching ? (
              <>
                <Spinner data-icon="inline-start" />
                Searching…
              </>
            ) : (
              <>
                <Search data-icon="inline-start" />
                Check availability
              </>
            )}
          </Button>
        </FieldGroup>
      )}

      {state.error && (
        <Alert variant="destructive">
          <XCircle />
          <AlertTitle>Search failed</AlertTitle>
          <AlertDescription>{state.error}</AlertDescription>
        </Alert>
      )}

      {state.home && (
        <Alert>
          {homeInStock ? <CheckCircle2 /> : state.home.serviceable ? <XCircle /> : <MapPinOff />}
          <AlertTitle>
            {homeInStock
              ? "In stock at your location"
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
        <Button variant="outline" onClick={() => handleSearch(true)}>
          <Search data-icon="inline-start" />
          Search nearby stores anyway
        </Button>
      )}

      {searching && state.discovery && state.discovery.probed < state.discovery.total && (
        <Field>
          <FieldLabel>
            Mapping Zepto stores in the area… {state.discovery.probed}/{state.discovery.total}
          </FieldLabel>
          <Progress value={(state.discovery.probed / Math.max(1, state.discovery.total)) * 100} />
          <FieldDescription>
            First search in a new area takes a while; later searches here are instant.
          </FieldDescription>
        </Field>
      )}

      {searching && state.totalStores > 0 && (
        <p className="text-sm text-muted-foreground">
          Checking stock at {state.results.length}/{state.totalStores} stores…
        </p>
      )}

      {coords && (searching || state.phase === "done") && !homeOnlySearch && (
        <ResultsMap
          lat={coords.lat}
          lng={coords.lng}
          radiusKm={radiusKm}
          results={sortedResults}
          selectedId={selectedId}
          onSelect={setSelectedId}
        />
      )}

      {sortedResults.length > 0 && (
        <ResultsList results={sortedResults} selectedId={selectedId} onSelect={setSelectedId} />
      )}

      {state.phase === "done" &&
        state.summary &&
        !homeOnlySearch &&
        (state.summary.in_stock > 0 ? (
          <p className="text-sm text-muted-foreground">
            In stock at {state.summary.in_stock} of {state.summary.stores} stores within {radiusKm}{" "}
            km.
          </p>
        ) : (
          <Empty>
            <EmptyHeader>
              <EmptyMedia variant="icon">
                <PackageX />
              </EmptyMedia>
              <EmptyTitle>Not available nearby</EmptyTitle>
              <EmptyDescription>
                None of the {state.summary.stores} stores within {radiusKm} km have this in stock
                right now. Try a bigger radius.
              </EmptyDescription>
            </EmptyHeader>
          </Empty>
        ))}
    </div>
  )
}

export default App
