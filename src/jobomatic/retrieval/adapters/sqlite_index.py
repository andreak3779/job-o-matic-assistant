"""The index as one SQLite file: chunks, an FTS5 keyword table and a sqlite-vec vector table.

Rebuildable from the profile at any time, so a damaged or out-of-date file is never a loss.
"""

from __future__ import annotations

import sqlite3
import struct
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

import sqlite_vec

from jobomatic.retrieval.model import Chunk, RetrievalError
from jobomatic.retrieval.ports import IndexEntry

SCHEMA_VERSION = "1"


def _blob(vector: Sequence[float]) -> bytes:
    return struct.pack(f"{len(vector)}f", *vector)


def _chunk(row: sqlite3.Row) -> Chunk:
    return Chunk(
        id=row["id"],
        kind=row["kind"],
        title=row["title"],
        text=row["text"],
        status=row["status"],
        url=row["url"],
        local_only=bool(row["local_only"]),
    )


class SqliteIndex:
    """``IndexStore`` over a SQLite file with the FTS5 and sqlite-vec extensions."""

    def __init__(self, path: Path) -> None:
        self.path = path

    @contextmanager
    def _connect(self, *, create: bool = False) -> Iterator[sqlite3.Connection]:
        if not create and not self.path.is_file():
            empty = self._empty()
            try:
                yield empty
            finally:
                empty.close()
            return
        if create:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            self._load_vec(conn)
            with conn:  # one transaction: commit on success, roll back on error
                yield conn
        finally:
            conn.close()

    @staticmethod
    def _empty() -> sqlite3.Connection:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(_SCHEMA)
        return conn

    @staticmethod
    def _load_vec(conn: sqlite3.Connection) -> None:
        try:
            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
            conn.enable_load_extension(False)
        except (AttributeError, sqlite3.OperationalError) as exc:
            raise RetrievalError(
                "this Python's sqlite3 cannot load extensions, so sqlite-vec is unavailable "
                f"({exc}); use a Python built with loadable-extension support"
            ) from exc

    def _meta(self, conn: sqlite3.Connection) -> dict[str, str]:
        try:
            return {r["key"]: r["value"] for r in conn.execute("select key, value from meta")}
        except sqlite3.OperationalError:  # no tables yet
            return {}

    # ── IndexStore ───────────────────────────────────────────────────────────

    def fingerprint(self) -> tuple[str, int] | None:
        with self._connect() as conn:
            meta = self._meta(conn)
        if meta.get("schema") != SCHEMA_VERSION or "model" not in meta:
            return None
        return meta["model"], int(meta["dimensions"])

    def hashes(self) -> dict[str, str]:
        if self.fingerprint() is None:
            return {}
        with self._connect() as conn:
            return {
                r["id"]: r["text_hash"] for r in conn.execute("select id, text_hash from chunks")
            }

    def apply(
        self,
        entries: Sequence[IndexEntry],
        remove: Sequence[str],
        *,
        model: str,
        dimensions: int,
        reset: bool,
    ) -> None:
        with self._connect(create=True) as conn:
            meta = self._meta(conn)
            if reset or meta.get("schema") != SCHEMA_VERSION:
                for table in ("chunks_fts", "vec_chunks", "chunks", "meta"):
                    conn.execute(f"drop table if exists {table}")
                meta = {}
            if not meta:
                if dimensions <= 0:
                    raise RetrievalError("cannot create an index without any vectors")
                conn.executescript(_SCHEMA)
                conn.execute(
                    f"create virtual table vec_chunks using vec0("
                    f"embedding float[{int(dimensions)}] distance_metric=cosine)"
                )
                conn.executemany(
                    "insert into meta(key, value) values (?, ?)",
                    [
                        ("schema", SCHEMA_VERSION),
                        ("model", model),
                        ("dimensions", str(dimensions)),
                    ],
                )
            for chunk_id in remove:
                self._delete(conn, chunk_id)
            for entry in entries:
                self._upsert(conn, entry)
            conn.execute("insert into chunks_fts(chunks_fts) values ('rebuild')")

    def chunks(self, kinds: frozenset[str] | None = None) -> list[Chunk]:
        with self._connect() as conn:
            rows = conn.execute("select * from chunks order by rowid").fetchall()
        return [_chunk(r) for r in rows if kinds is None or r["kind"] in kinds]

    def nearest(
        self, vector: list[float], limit: int, kinds: frozenset[str] | None = None
    ) -> list[tuple[Chunk, float]]:
        if limit <= 0 or self.fingerprint() is None:
            return []
        with self._connect() as conn:
            neighbours = conn.execute(
                "select rowid, distance from vec_chunks where embedding match ? and k = ? "
                "order by distance",
                (_blob(vector), limit),
            ).fetchall()
            found: list[tuple[Chunk, float]] = []
            for hit in neighbours:
                row = conn.execute(
                    "select * from chunks where rowid = ?", (hit["rowid"],)
                ).fetchone()
                if row is None or (kinds is not None and row["kind"] not in kinds):
                    continue
                found.append((_chunk(row), 1.0 - float(hit["distance"])))
        return found

    # ── helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _delete(conn: sqlite3.Connection, chunk_id: str) -> None:
        row = conn.execute("select rowid from chunks where id = ?", (chunk_id,)).fetchone()
        if row is not None:
            conn.execute("delete from vec_chunks where rowid = ?", (row["rowid"],))
            conn.execute("delete from chunks where rowid = ?", (row["rowid"],))

    @staticmethod
    def _upsert(conn: sqlite3.Connection, entry: IndexEntry) -> None:
        chunk = entry.chunk
        values = (
            chunk.kind,
            chunk.title,
            chunk.text,
            chunk.status,
            chunk.url,
            int(chunk.local_only),
            entry.text_hash,
        )
        row = conn.execute("select rowid from chunks where id = ?", (chunk.id,)).fetchone()
        if row is None:
            if entry.vector is None:
                raise RetrievalError(f"no vector for new chunk {chunk.id}")
            cursor = conn.execute(
                "insert into chunks(kind, title, text, status, url, local_only, text_hash, id) "
                "values (?, ?, ?, ?, ?, ?, ?, ?)",
                (*values, chunk.id),
            )
            conn.execute(
                "insert into vec_chunks(rowid, embedding) values (?, ?)",
                (cursor.lastrowid, _blob(entry.vector)),
            )
            return
        conn.execute(
            "update chunks set kind=?, title=?, text=?, status=?, url=?, local_only=?, "
            "text_hash=? where rowid=?",
            (*values, row["rowid"]),
        )
        if entry.vector is not None:
            conn.execute("delete from vec_chunks where rowid = ?", (row["rowid"],))
            conn.execute(
                "insert into vec_chunks(rowid, embedding) values (?, ?)",
                (row["rowid"], _blob(entry.vector)),
            )


_SCHEMA = """
create table if not exists meta (key text primary key, value text not null);
create table if not exists chunks (
    id text not null unique,
    kind text not null,
    title text not null,
    text text not null,
    status text not null,
    url text not null,
    local_only integer not null,
    text_hash text not null
);
create virtual table if not exists chunks_fts using fts5(
    title, text, content='chunks', content_rowid='rowid'
);
"""
