"""
merge_lat.py — Lógica de detección y merge de audio latino con mkvmerge.
Usado por bot.py para el flujo de combinación YTS + identi.
"""

import json
import os
import re
import subprocess


JDOWNLOADER_DIR = "/home/ramiro/jdownloader"
PELICULAS_DIR   = "/mnt/DatosF/PelículasF"
VIDEO_EXTS      = {".mkv", ".mp4", ".avi", ".m4v"}


# ── Utilidades ────────────────────────────────────────────────────────────────

def normalize(s: str) -> str:
    """Letras y números en minúsculas, sin ruido."""
    s = re.sub(r"[\(\[\{]?(19|20)\d{2}[\)\]\}]?", "", s)
    noise = r"(1080p|720p|480p|2160p|4k|bluray|bdrip|webrip|web|hdtv|x264|x265|hevc|" \
            r"aac|ac3|e-ac-3|dts|extended|imax|remastered|hdr|remux|proper|" \
            r"10bits?|dual|latino|ingles|english|spanish|yts|mx|yify|identi|" \
            r"jdownloader|digital|\bspa\b|\beng\b)"
    s = re.sub(noise, "", s, flags=re.IGNORECASE)
    return re.sub(r"[^a-z0-9]", "", s.lower()).strip()


def similarity(a: str, b: str) -> float:
    """Simple word overlap ratio between two normalized strings."""
    wa = set(re.findall(r"[a-z0-9]+", normalize(a)))
    wb = set(re.findall(r"[a-z0-9]+", normalize(b)))
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / max(len(wa), len(wb))


def get_tracks(filepath: str) -> dict:
    """Return mkvmerge -J parsed track info."""
    try:
        r = subprocess.run(
            ["mkvmerge", "-J", filepath],
            capture_output=True, text=True, timeout=15
        )
        return json.loads(r.stdout)
    except Exception:
        return {}


def find_latino_audio(tracks_json: dict) -> int | None:
    """Return track id of the Latino/Spanish audio, or None."""
    for t in tracks_json.get("tracks", []):
        if t.get("type") != "audio":
            continue
        props = t.get("properties", {})
        lang  = props.get("language", "")
        name  = props.get("track_name", "").lower()
        if lang == "spa" or "latino" in name or "español" in name or "spanish" in name:
            return t["id"]
    return None


def find_spa_subs(tracks_json: dict) -> list[int]:
    """Return list of subtitle track ids that are Spanish."""
    ids = []
    for t in tracks_json.get("tracks", []):
        if t.get("type") != "subtitles":
            continue
        props = t.get("properties", {})
        lang  = props.get("language", "")
        name  = props.get("track_name", "").lower()
        if lang == "spa" or "español" in name or "spanish" in name or "latino" in name:
            ids.append(t["id"])
    return ids


# ── Detección de archivos ─────────────────────────────────────────────────────

def list_jdownloader_files() -> list[str]:
    """Return video files found in jdownloader dir (non-recursive)."""
    files = []
    if not os.path.isdir(JDOWNLOADER_DIR):
        return files
    for e in os.scandir(JDOWNLOADER_DIR):
        if e.is_file() and os.path.splitext(e.name)[1].lower() in VIDEO_EXTS:
            files.append(e.path)
    return sorted(files)


def find_yts_match(identi_path: str) -> list[tuple[float, str, str]]:
    """
    For a given identi file, find candidate YTS folders in PelículasF.
    Returns list of (score, folder_path, video_file_path) sorted by score desc.
    """
    identi_name = os.path.splitext(os.path.basename(identi_path))[0]
    candidates  = []

    if not os.path.isdir(PELICULAS_DIR):
        return candidates

    for entry in os.scandir(PELICULAS_DIR):
        if not entry.is_dir():
            continue
        score = similarity(identi_name, entry.name)
        if score < 0.3:
            continue
        # Find video file inside folder
        for sub in os.scandir(entry.path):
            if sub.is_file() and os.path.splitext(sub.name)[1].lower() in VIDEO_EXTS:
                candidates.append((score, entry.path, sub.path))
                break

    candidates.sort(reverse=True)
    return candidates[:5]


# ── YTS library helpers ──────────────────────────────────────────────────────

def get_recent_yts(limit: int = 5) -> list[tuple[float, str, str]]:
    """Return the most recently modified folders in PelículasF."""
    import subprocess, datetime
    items = []
    if not os.path.isdir(PELICULAS_DIR):
        return items
    try:
        result = subprocess.run(
            ["ls", "--time-style=+%Y-%m-%d %H:%M", "-lt", PELICULAS_DIR],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            parts = line.split(None, 7)
            if len(parts) < 8 or parts[0] == "total": continue
            if not parts[0][0] in "dl-": continue
            folder = os.path.join(PELICULAS_DIR, parts[7].strip())
            if not os.path.isdir(folder): continue
            for sub in os.scandir(folder):
                if sub.is_file() and os.path.splitext(sub.name)[1].lower() in VIDEO_EXTS:
                    items.append((0.0, folder, sub.path))
                    break
            if len(items) >= limit:
                break
    except Exception:
        pass
    return items


def search_yts_by_title(query: str, limit: int = 8) -> list[tuple[float, str, str]]:
    """Search PelículasF folders by title similarity."""
    candidates = []
    if not os.path.isdir(PELICULAS_DIR):
        return candidates
    qw = set(re.findall(r"[a-z0-9]+", query.lower()))
    if not qw:
        return candidates
    for entry in os.scandir(PELICULAS_DIR):
        if not entry.is_dir(): continue
        nw    = set(re.findall(r"[a-z0-9]+", entry.name.lower()))
        score = len(qw & nw) / max(len(qw), len(nw)) if nw else 0.0
        if score < 0.3: continue
        for sub in os.scandir(entry.path):
            if sub.is_file() and os.path.splitext(sub.name)[1].lower() in VIDEO_EXTS:
                candidates.append((score, entry.path, sub.path))
                break
    candidates.sort(reverse=True)
    return candidates[:limit]


# ── Merge ──────────────────────────────────────────────────────────────────────

def build_output_name(yts_folder: str) -> str:
    """Build output filename: folder name + _eng-lat.mkv inside the folder."""
    folder_name = os.path.basename(yts_folder)
    # Clean brackets/tags from folder name for cleaner output
    clean = re.sub(r"\s*[\[\(][^\]\)]*[\]\)]", "", folder_name).strip()
    return os.path.join(yts_folder, clean + "_eng-lat.mkv")


def run_merge(yts_video: str, identi_video: str, output: str) -> tuple[bool, str]:
    """
    Run mkvmerge to combine:
      - Video + original audio from YTS file
      - Latino audio from identi file
      - Spanish subs from identi file (if any)
    Returns (success, message).
    """
    identi_tracks = get_tracks(identi_video)
    lat_audio_id  = find_latino_audio(identi_tracks)
    spa_sub_ids   = find_spa_subs(identi_tracks)

    if lat_audio_id is None:
        return False, "No se encontró pista de audio latino en el archivo de identi."

    cmd = ["mkvmerge", "-o", output]

    # YTS: keep everything (video + original audio + subs if any)
    cmd += [yts_video]

    # identi: only latino audio
    cmd += [
        "--no-video",
        "--audio-tracks", str(lat_audio_id),
        "--language",     f"{lat_audio_id}:spa",
        "--track-name",   f"{lat_audio_id}:Latino",
    ]
    # Spanish subs from identi
    if spa_sub_ids:
        cmd += ["--subtitle-tracks", ",".join(str(i) for i in spa_sub_ids)]
    else:
        cmd += ["--no-subtitles"]

    cmd += [identi_video]

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if r.returncode == 0 or r.returncode == 1:  # 1 = warnings only
            return True, r.stdout
        return False, r.stderr or r.stdout
    except subprocess.TimeoutExpired:
        return False, "mkvmerge tardó demasiado (>5 min)."
    except Exception as e:
        return False, str(e)


def cleanup(yts_video: str, identi_video: str):
    """Delete original YTS video and identi file after successful merge."""
    for fp in [yts_video, identi_video]:
        try:
            os.remove(fp)
        except Exception:
            pass
