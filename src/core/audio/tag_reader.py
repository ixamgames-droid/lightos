"""F-15 (Tier 0): BPM aus eingebetteten Datei-Tags lesen — reines stdlib.

Liest die im Audiofile gespeicherte BPM-METADATEN (kein Audio-Inhalt!):
  * MP3  → ID3v2 ``TBPM``-Frame (v2.2 ``TBP``, v2.3/v2.4 ``TBPM``)
  * M4A/MP4/AAC → iTunes ``tmpo``-Atom (moov→udta→meta→ilst→tmpo→data, 16-bit)

Das ist Metadaten-Auslesen, KEINE Offline-Audioanalyse — daher unabhängig von der
bewussten Auslassung der Inhalts-Analyse und strikt besser als die Dateinamen-Heuristik
(``guess_genre_bpm``). Liefert ``0.0`` bei fehlendem Tag / Lesefehler / unbekanntem Format.
"""
from __future__ import annotations
import os
import re
import struct


def read_tag_bpm(path: str) -> float:
    """BPM aus dem eingebetteten Tag (oder 0.0). Wirft nie."""
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".mp3":
            return _read_id3v2_tbpm(path)
        if ext in (".m4a", ".mp4", ".aac"):
            return _read_mp4_tmpo(path)
    except Exception:
        return 0.0
    return 0.0


# ── ID3v2 (MP3) ───────────────────────────────────────────────────────────────

def _syncsafe(b: bytes) -> int:
    return (b[0] << 21) | (b[1] << 14) | (b[2] << 7) | b[3]


def _read_id3v2_tbpm(path: str) -> float:
    with open(path, "rb") as f:
        header = f.read(10)
        if len(header) < 10 or header[0:3] != b"ID3":
            return 0.0
        major = header[3]
        flags = header[5]
        size = _syncsafe(header[6:10])
        data = f.read(size)
    pos = 0
    if flags & 0x40:                       # erweiterter Header → überspringen
        if len(data) < 4:
            return 0.0
        ext = _syncsafe(data[0:4]) if major == 4 else struct.unpack(">I", data[0:4])[0]
        pos += ext
    if major == 2:                          # v2.2: 6-Byte-Frames, 3-Zeichen-IDs
        while pos + 6 <= len(data):
            fid = data[pos:pos + 3]
            if fid == b"\x00\x00\x00":
                break
            fsize = (data[pos + 3] << 16) | (data[pos + 4] << 8) | data[pos + 5]
            pos += 6
            if fid == b"TBP":
                return _parse_text_number(data[pos:pos + fsize])
            pos += fsize
        return 0.0
    # v2.3 / v2.4: 10-Byte-Frames, 4-Zeichen-IDs
    while pos + 10 <= len(data):
        fid = data[pos:pos + 4]
        if fid == b"\x00\x00\x00\x00":
            break
        if major == 4:
            fsize = _syncsafe(data[pos + 4:pos + 8])
        else:
            fsize = struct.unpack(">I", data[pos + 4:pos + 8])[0]
        pos += 10
        if fid == b"TBPM":
            return _parse_text_number(data[pos:pos + fsize])
        pos += fsize
    return 0.0


def _parse_text_number(body: bytes) -> float:
    if not body:
        return 0.0
    enc = body[0]
    raw = body[1:]
    try:
        if enc == 0:
            s = raw.decode("latin-1", "ignore")
        elif enc == 1:
            s = raw.decode("utf-16", "ignore")
        elif enc == 2:
            s = raw.decode("utf-16-be", "ignore")
        else:
            s = raw.decode("utf-8", "ignore")
    except Exception:
        s = ""
    m = re.match(r"\s*(\d+(?:\.\d+)?)", s.replace("\x00", " ").strip())
    return float(m.group(1)) if m else 0.0


# ── MP4 / M4A (iTunes tmpo) ─────────────────────────────────────────────────────

def _find_atom(f, end: int, target: bytes):
    """Nächstes Atom mit Typ ``target`` im Bereich [f.tell(), end) → (start, end) der
    Nutzlast, sonst None. Behandelt 64-bit-Größen (size==1) und size==0 (bis Ende)."""
    while f.tell() + 8 <= end:
        start = f.tell()
        hdr = f.read(8)
        if len(hdr) < 8:
            return None
        size = struct.unpack(">I", hdr[0:4])[0]
        typ = hdr[4:8]
        if size == 1:                       # 64-bit-Größe folgt
            ext = f.read(8)
            if len(ext) < 8:
                return None
            size = struct.unpack(">Q", ext[0:8])[0]
            payload_start = start + 16
        elif size == 0:                     # bis zum Ende
            payload_start = start + 8
            size = end - start
        else:
            payload_start = start + 8
        payload_end = start + size
        if size < 8 or payload_end > end:
            return None
        if typ == target:
            return (payload_start, payload_end)
        f.seek(payload_end)
    return None


def _read_mp4_tmpo(path: str) -> float:
    with open(path, "rb") as f:
        f.seek(0, 2)
        fsize = f.tell()
        f.seek(0)
        moov = _find_atom(f, fsize, b"moov")
        if not moov:
            return 0.0
        f.seek(moov[0])
        udta = _find_atom(f, moov[1], b"udta")
        if not udta:
            return 0.0
        f.seek(udta[0])
        meta = _find_atom(f, udta[1], b"meta")
        if not meta:
            return 0.0
        # 'meta' ist eine Full-Box: 4 Byte Version/Flags vor den Kind-Atomen.
        f.seek(meta[0] + 4)
        ilst = _find_atom(f, meta[1], b"ilst")
        if not ilst:
            return 0.0
        f.seek(ilst[0])
        tmpo = _find_atom(f, ilst[1], b"tmpo")
        if not tmpo:
            return 0.0
        f.seek(tmpo[0])
        data = _find_atom(f, tmpo[1], b"data")
        if not data:
            return 0.0
        # 'data'-Box: 4 Byte Version/Flags + 4 Byte Reserved, dann der Wert (16-bit).
        f.seek(data[0] + 8)
        val = f.read(data[1] - (data[0] + 8))
        if len(val) >= 2:
            return float(struct.unpack(">H", val[:2])[0])
    return 0.0
