"""SQLite cache of discovered dark stores and probed coordinates."""

import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import SERVICEABLE_PROBE_TTL_DAYS, UNSERVICEABLE_PROBE_TTL_DAYS
from .grid import KM_PER_DEG_LAT, haversine_km

SCHEMA = """
CREATE TABLE IF NOT EXISTS stores (
    id TEXT PRIMARY KEY,
    name TEXT,
    city TEXT,
    lat REAL NOT NULL,
    lng REAL NOT NULL,
    probe_count INTEGER NOT NULL DEFAULT 1,
    discovered_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS probed_points (
    lat REAL NOT NULL,
    lng REAL NOT NULL,
    store_id TEXT,
    serviceable INTEGER NOT NULL,
    probed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_probed_lat ON probed_points(lat);
"""


@dataclass
class Store:
    id: str
    name: str | None
    city: str | None
    lat: float
    lng: float


class StoreCache:
    def __init__(self, path: Path | str):
        if isinstance(path, Path):
            path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(SCHEMA)

    def close(self) -> None:
        self._db.close()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def stores_within(self, lat: float, lng: float, radius_km: float) -> list[Store]:
        dlat = radius_km / KM_PER_DEG_LAT
        dlng = radius_km / (KM_PER_DEG_LAT * max(0.1, math.cos(math.radians(lat))))
        rows = self._db.execute(
            "SELECT id, name, city, lat, lng FROM stores WHERE lat BETWEEN ? AND ? AND lng BETWEEN ? AND ?",
            (lat - dlat, lat + dlat, lng - dlng, lng + dlng),
        ).fetchall()
        return [
            Store(*r)
            for r in rows
            if haversine_km(lat, lng, r[3], r[4]) <= radius_km
        ]

    def has_fresh_probe_near(self, lat: float, lng: float, within_km: float) -> bool:
        """True if the point is already covered by a recent probe."""
        cutoff_ok = datetime.now(timezone.utc) - timedelta(days=SERVICEABLE_PROBE_TTL_DAYS)
        cutoff_empty = datetime.now(timezone.utc) - timedelta(days=UNSERVICEABLE_PROBE_TTL_DAYS)
        dlat = within_km / KM_PER_DEG_LAT
        dlng = within_km / (KM_PER_DEG_LAT * max(0.1, math.cos(math.radians(lat))))
        rows = self._db.execute(
            "SELECT lat, lng, serviceable, probed_at FROM probed_points WHERE lat BETWEEN ? AND ? AND lng BETWEEN ? AND ?",
            (lat - dlat, lat + dlat, lng - dlng, lng + dlng),
        ).fetchall()
        for plat, plng, serviceable, probed_at in rows:
            if haversine_km(lat, lng, plat, plng) > within_km:
                continue
            ts = datetime.fromisoformat(probed_at)
            if ts >= (cutoff_ok if serviceable else cutoff_empty):
                return True
        return False

    def record_probe(
        self,
        lat: float,
        lng: float,
        store_id: str | None,
        store_name: str | None = None,
        city: str | None = None,
    ) -> Store | None:
        """Record a probe result; returns the (possibly new) store if serviceable."""
        now = self._now()
        self._db.execute(
            "INSERT INTO probed_points (lat, lng, store_id, serviceable, probed_at) VALUES (?, ?, ?, ?, ?)",
            (lat, lng, store_id, 1 if store_id else 0, now),
        )
        store = None
        if store_id:
            row = self._db.execute(
                "SELECT lat, lng, probe_count FROM stores WHERE id = ?", (store_id,)
            ).fetchone()
            if row:
                # Running centroid of all probe points that hit this store
                # approximates the store's real location.
                olat, olng, n = row
                nlat, nlng = (olat * n + lat) / (n + 1), (olng * n + lng) / (n + 1)
                self._db.execute(
                    "UPDATE stores SET lat=?, lng=?, probe_count=?, last_seen_at=?, "
                    "name=COALESCE(?, name), city=COALESCE(?, city) WHERE id=?",
                    (nlat, nlng, n + 1, now, store_name, city, store_id),
                )
                store = Store(store_id, store_name, city, nlat, nlng)
            else:
                self._db.execute(
                    "INSERT INTO stores (id, name, city, lat, lng, probe_count, discovered_at, last_seen_at) "
                    "VALUES (?, ?, ?, ?, ?, 1, ?, ?)",
                    (store_id, store_name, city, lat, lng, now, now),
                )
                store = Store(store_id, store_name, city, lat, lng)
        self._db.commit()
        return store

    def stats(self) -> dict:
        stores = self._db.execute("SELECT COUNT(*) FROM stores").fetchone()[0]
        probes = self._db.execute("SELECT COUNT(*) FROM probed_points").fetchone()[0]
        return {"stores": stores, "probes": probes}
