from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, ConversationHandler, filters, ContextTypes, CallbackQueryHandler
import logging
import os
import re
import time
import datetime
import requests
import qbittorrentapi
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ConversationHandler, filters, ContextTypes,
)
from config import TELEGRAM_TOKEN, ALLOWED_USER_ID, QB_HOST, QB_PORT, QB_USER, QB_PASS

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Estados ───────────────────────────────────────────────────────────────────
(SEARCH, MENU, TRENDING,
 SELECT_TYPE, SELECT_SERIES_PICK, SERIES_INFO, SELECT_SERIES_MODE, SELECT_SERIES_DETAIL,
 SELECT_MOVIE, SELECT_TORRENT,
 SELECT_MOVIE_FOLDER, WARN_EXISTING,
 SELECT_EXISTING_OR_NEW,
 CANCEL_DOWNLOAD, LIBRARY_SEARCH, SIMILAR_SEARCH,
 ADD_USER,
 DELETE_SEARCH, DELETE_SELECT, DELETE_CONFIRM1, DELETE_CONFIRM2,
 RECENT_CATEGORY,
 CONFIRM) = range(23)

# ── APIs / Constantes ─────────────────────────────────────────────────────────
YTS_API     = "https://yts.bz/api/v2/list_movies.json"
JACKETT_URL = "http://localhost:9117/api/v2.0/indexers/all/results"
JACKETT_KEY = "20s8ciqbnoyh7hfdj42nhti01d62s3s7"
OMDB_KEY    = "817e3c48"
OMDB_API    = "https://www.omdbapi.com/"
TVMAZE_API  = "https://api.tvmaze.com/shows"

MAX_RETRIES = 3
CHECK_INTERVAL = 60
MENU_BTN       = InlineKeyboardMarkup([[InlineKeyboardButton("📋 Menú", callback_data="show_menu")]])


# ── Reply Keyboards (contextuales) ───────────────────────────────────────────

def _kb(*rows):
    """Build a ReplyKeyboardMarkup from rows of button labels."""
    keyboard = [[KeyboardButton(b) for b in row] for row in rows]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)


KB_MAIN = _kb(
    ["1", "2", "3", "4"],
    ["5", "6", "7", "8", "9"],
)
KB_YES_NO    = _kb(["1", "2"])
KB_CONFIRM   = _kb(["1", "2"])
KB_3         = _kb(["1", "2", "3"])
KB_4         = _kb(["1", "2", "3", "4"])
KB_REMOVE    = ReplyKeyboardRemove()


def _kb_n(n, extras=None):
    """Build keyboard for n numbered options, 4 per row, plus extras."""
    nums  = list(range(1, n+1))
    rows  = [nums[i:i+4] for i in range(0, len(nums), 4)]
    rows  = [[str(x) for x in row] for row in rows]
    if extras:
        rows.append([str(x) for x in extras])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, one_time_keyboard=False)


async def _rpl(update, text, no_menu=False, **kwargs):
    """Wrapper for reply_text that always adds the Menú button unless no_menu=True."""
    if not no_menu and 'reply_markup' not in kwargs:
        kwargs['reply_markup'] = MENU_BTN
    return await update.message.reply_text(text, **kwargs)
PAGE_SIZE      = 10
STALL_HOURS    = 2   # horas sin progreso para considerar atascado

# ── Carpetas ──────────────────────────────────────────────────────────────────
MOVIE_FOLDERS = ["/mnt/DatosF/PelículasF", "/mnt/DatosF/NiñosF"]
ALL_SERIES_BASES = [
    "/mnt/DatosF/SeriesF", "/mnt/DatosE/SeriesE", "/mnt/DatosD/Series",
    "/mnt/DatosF/SeriesNiñosF", "/mnt/DatosE/SeriesNiñosE", "/mnt/DatosD/SeriesNiños",
]
NEW_SERIES_FOLDER       = "/mnt/DatosF/SeriesF"
NEW_SERIES_NINOS_FOLDER = "/mnt/DatosF/SeriesNiñosF"
MOVIE_SCAN_DIRS = [
    "/mnt/DatosD/Películas", "/mnt/DatosD/Niños",
    "/mnt/DatosE/PelículasE", "/mnt/DatosE/NiñosE",
    "/mnt/DatosF/PelículasF", "/mnt/DatosF/NiñosF",
]
SERIES_SCAN_DIRS = [
    "/mnt/DatosD/Series", "/mnt/DatosD/SeriesNiños",
    "/mnt/DatosE/SeriesE", "/mnt/DatosE/SeriesNiñosE",
    "/mnt/DatosF/SeriesF", "/mnt/DatosF/SeriesNiñosF",
]
ALL_SCAN_DIRS = MOVIE_SCAN_DIRS + SERIES_SCAN_DIRS

YTS_TRACKERS = [
    "udp://open.demonii.com:1337/announce",
    "udp://tracker.openbittorrent.com:80",
    "udp://tracker.coppersurfer.tk:6969",
    "udp://glotorrents.pw:6969/announce",
    "udp://tracker.opentrackr.org:1337/announce",
    "udp://torrent.gresille.org:80/announce",
    "udp://p4p.arenabg.com:1337",
    "udp://tracker.leechers-paradise.org:6969",
]

# ── Usuarios permitidos (ampliable) ──────────────────────────────────────────
def load_allowed():
    ids = {ALLOWED_USER_ID}
    try:
        with open("/opt/cine_bot/allowed_users.txt") as f:
            for line in f:
                line = line.strip()
                if line.isdigit():
                    ids.add(int(line))
    except FileNotFoundError:
        pass
    return ids

def save_allowed(ids):
    with open("/opt/cine_bot/allowed_users.txt", "w") as f:
        for uid in ids:
            if uid != ALLOWED_USER_ID:
                f.write(f"{uid}\n")

def guard(uid):
    return uid in load_allowed()

def is_owner(uid):
    return uid == ALLOWED_USER_ID

# ── Clientes externos ─────────────────────────────────────────────────────────
def qbt_client():
    c = qbittorrentapi.Client(host=QB_HOST, port=QB_PORT, username=QB_USER, password=QB_PASS)
    c.auth_log_in()
    return c

def get_omdb_data(title, year=None, kind=None):
    try:
        params = {"apikey": OMDB_KEY, "t": title, "plot": "full"}
        if year:   params["y"] = year
        if kind:   params["type"] = kind
        r = requests.get(OMDB_API, params=params, timeout=8).json()
        if r.get("Response") == "False":
            return {}
        return r
    except Exception:
        return {}

def get_omdb_poster(title, year=None):
    d = get_omdb_data(title, year)
    p = d.get("Poster")
    return p if p and p != "N/A" else None

def search_omdb_series(query):
    """Busca series en OMDB por nombre. Devuelve lista de resultados."""
    try:
        r = requests.get(OMDB_API, params={"apikey": OMDB_KEY, "s": query, "type": "series"}, timeout=8).json()
        if r.get("Response") == "False":
            return []
        return r.get("Search") or []
    except Exception:
        return []


def get_omdb_series_info(title, imdb_id=None):
    """Fetch series info. If imdb_id is provided, uses it for exact lookup."""
    try:
        if imdb_id:
            params = {"apikey": OMDB_KEY, "i": imdb_id, "plot": "full"}
        else:
            params = {"apikey": OMDB_KEY, "t": title, "type": "series", "plot": "full"}
        d = requests.get(OMDB_API, params=params, timeout=8).json()
        if d.get("Response") == "False":
            return {}
    except Exception:
        return {}
    return {
        "poster":       d.get("Poster") if d.get("Poster") != "N/A" else None,
        "rating":       d.get("imdbRating") if d.get("imdbRating") != "N/A" else None,
        "plot":         d.get("Plot") if d.get("Plot") != "N/A" else None,
        "totalSeasons": d.get("totalSeasons"),
        "title":        d.get("Title", title),
        "year":         d.get("Year"),
        "imdbID":       d.get("imdbID"),
        "genre":        d.get("Genre"),
    }

def get_omdb_episodes_per_season(title, total_seasons):
    result = {}
    for s in range(1, min(int(total_seasons)+1, 20)):
        try:
            r = requests.get(OMDB_API, params={"apikey": OMDB_KEY, "t": title, "Season": s}, timeout=8).json()
            eps = r.get("Episodes")
            if eps:
                result[s] = len(eps)
        except Exception:
            pass
    return result

def build_magnet(info_hash, title):
    trackers = "&tr=".join(requests.utils.quote(t) for t in YTS_TRACKERS)
    return f"magnet:?xt=urn:btih:{info_hash}&dn={requests.utils.quote(title)}&tr={trackers}"

# ── Biblioteca local ──────────────────────────────────────────────────────────
def normalize(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())

def titles_match(query, name, exact=False):
    """Match query against a file/folder name.
    exact=True  (duplicate check): all significant words must be identical.
    exact=False (library search): all query words must appear anywhere in name.
    """
    NOISE = {"1080p","720p","480p","2160p","4k","bluray","bdrip","webrip","webdl",
             "web","hdtv","dvdrip","xvid","x264","x265","hevc","aac","ac3","dts",
             "extended","imax","remastered","proper","yts","mx","eztv","mkv","mp4",
             "avi","dual","10bit","5","1","2","0","hdr","sdr","remux"}
    def clean(s):
        words = re.findall(r"[a-z0-9]+", s.lower())
        result = []
        for w in words:
            if re.match(r"^(19|20)\d{2}$", w): break
            if w in NOISE: break
            result.append(w)
        return result
    qw = clean(query)
    nw = clean(name)
    if not qw or not nw: return False
    if exact:
        return qw == nw
    # Library search: every query word must appear somewhere in the name
    return all(w in nw for w in qw)

def find_in_library(query, scan_dirs, exact=False):
    video_exts = {".mkv",".mp4",".avi",".mov",".wmv",".m4v"}
    found = []
    for base in scan_dirs:
        if not os.path.isdir(base): continue
        try:
            for e in os.scandir(base):
                if titles_match(query, os.path.splitext(e.name)[0], exact=exact):
                    if e.is_dir() or os.path.splitext(e.name)[1].lower() in video_exts:
                        found.append(e.path)
        except PermissionError: continue
    return found

def find_episode_in_library(query, episode, scan_dirs):
    video_exts = {".mkv",".mp4",".avi",".mov",".wmv",".m4v"}
    ep_pat = re.compile(re.escape(episode), re.IGNORECASE)
    found = []
    for base in scan_dirs:
        if not os.path.isdir(base): continue
        try:
            for sd in os.scandir(base):
                if not sd.is_dir() or not titles_match(query, sd.name): continue
                for root, _, files in os.walk(sd.path):
                    for f in files:
                        if os.path.splitext(f)[1].lower() in video_exts and ep_pat.search(f):
                            found.append(os.path.join(root, f))
        except PermissionError: continue
    return found

def find_series_folder(query, base_paths):
    q_norm = normalize(query)
    matches = []
    for base in base_paths:
        if not os.path.isdir(base): continue
        try:
            for e in os.scandir(base):
                if e.is_dir() and normalize(e.name) == q_norm:
                    matches.append(e.path)
        except PermissionError: continue
    return matches

def get_recent_files(scan_dirs, limit=15):
    video_exts = {".mkv",".mp4",".avi",".mov",".wmv",".m4v"}
    files = []
    for base in scan_dirs:
        if not os.path.isdir(base): continue
        try:
            for root, _, fs in os.walk(base):
                for f in fs:
                    if os.path.splitext(f)[1].lower() in video_exts:
                        fp = os.path.join(root, f)
                        files.append((os.path.getmtime(fp), fp))
        except PermissionError: continue
    files.sort(reverse=True)
    return [fp for _, fp in files[:limit]]

# ── Job: notificación descarga completada ─────────────────────────────────────
async def check_downloads(context):
    watching = context.bot_data.get("watching", {})
    if not watching: return
    try:
        qbt = qbt_client()
        torrents = {t.hash: t for t in qbt.torrents_info()}
    except Exception as e:
        logger.warning(f"check_downloads: {e}"); return
    finished = []
    for h, info in watching.items():
        t = torrents.get(h.lower()) or torrents.get(h.upper()) or torrents.get(h)
        if t and t.state in ("uploading","stalledUP","pausedUP","queuedUP","checkingUP","forcedUP"):
            finished.append((h, info))
    for h, info in finished:
        try:
            kind  = info.get("kind")
            icon  = "🎬" if kind == "movie" else "📺"
            title = info["title"]
            # Wait a moment then look up in Plex
            import time as _time; _time.sleep(3)
            await context.bot.send_message(
                chat_id=info["chat_id"],
                text=f"✅ *¡Descarga completada!*\n\n{icon} {title}\n💾 {info['quality']}\n📁 `{info['folder']}`",
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.warning(f"Notificación fallida: {e}")
        del watching[h]
    context.bot_data["watching"] = watching

# ── Helpers ───────────────────────────────────────────────────────────────────
async def _bad_input(update, context, state, hint):
    retries = context.user_data.get("retries", 0) + 1
    context.user_data["retries"] = retries
    remaining = MAX_RETRIES - retries
    if remaining <= 0:
        context.user_data.clear()
        await _rpl(update, "❌ Demasiados intentos. Operación cancelada.\nManda un título o escribe *menú* cuando quieras.", parse_mode="Markdown")
        return SEARCH
    s = "s" if remaining > 1 else ""
    await _rpl(update, f"⚠️ {hint} ({remaining} intento{s} restante{s})")
    return state

async def _show_page(update, context, key_all, key_offset, state, header, fmt_fn):
    items  = context.user_data.get(key_all, [])
    offset = context.user_data.get(key_offset, 0)
    page   = items[offset:offset+PAGE_SIZE]
    if not page:
        await _rpl(update, "❌ No hay más resultados.")
        context.user_data.clear(); return SEARCH
    context.user_data[key_offset] = offset
    context.user_data["retries"]  = 0
    has_more = len(items) > offset + PAGE_SIZE
    lines = [f"{i+1}. {fmt_fn(item)}" for i, item in enumerate(page)]
    n = len(page)
    extras = [n+1, n+2] if has_more else [n+1]
    if has_more:
        lines.append(f"{n+1}. ➡️ Más")
        lines.append(f"{n+2}. ❌ Cancelar")
    else:
        lines.append(f"{n+1}. ❌ Cancelar")
    await _rpl(update, 
        f"{header}\n\n" + "\n".join(lines) + "\n\nResponde con el *número*.",
        parse_mode="Markdown",
        reply_markup=_kb_n(n, extras),
    )
    return state

MENU_TEXT = (
    "🎬 *¿Qué quieres hacer?*\n\n"
    "1. 🎬 Estrenos de películas\n"
    "2. 📺 Series en tendencia\n"
    "3. 📊 Status de descargas\n"
    "4. ❌ Cancelar una descarga\n"
    "5. 🔍 Buscar en mi biblioteca\n"
    "6. 🕐 Últimas descargas\n"
    "7. 🗑 Borrar película/serie\n"
    "8. ⚠️ Torrents atascados\n"
    "9. 👥 Agregar usuario\n\n"
    "_O escribe el título de una película o serie directamente._"
)

async def show_menu(update, context):
    if not guard(update.effective_user.id): return ConversationHandler.END
    context.user_data.clear()
    await _rpl(update, MENU_TEXT, no_menu=True, parse_mode="Markdown", reply_markup=KB_MAIN)
    return MENU

# ── MENU HANDLER ─────────────────────────────────────────────────────────────
async def handle_menu(update, context):
    if not guard(update.effective_user.id): return ConversationHandler.END
    answer = update.message.text.strip()

    if answer == "1":
        return await _fetch_trending_movies(update, context)
    if answer == "2":
        return await _fetch_trending_series(update, context)
    if answer == "3":
        return await _status_downloads(update, context)
    if answer == "4":
        return await _list_for_cancel(update, context)
    if answer == "5":
        await _rpl(update, "🔍 ¿Qué título quieres buscar en tu biblioteca?", reply_markup=KB_REMOVE)
        return LIBRARY_SEARCH
    if answer == "6":
        return await _show_recent_category(update, context, "movie")
    if answer == "7":
        await _rpl(update, "🗑 ¿Qué título quieres borrar?", reply_markup=KB_REMOVE)
        return DELETE_SEARCH
    if answer == "8":
        return await _show_stalled(update, context)
    if answer == "9":
        if not is_owner(update.effective_user.id):
            await _rpl(update, "❌ Solo el dueño puede agregar usuarios.")
            return SEARCH
        await _rpl(update, 
            "👥 Manda el Telegram ID numérico del usuario a agregar\n"
            "o escribe *cancelar* para volver.",
            parse_mode="Markdown",
            reply_markup=KB_REMOVE,
        )
        return ADD_USER

    context.user_data.clear()
    return await search_movie_handler(update, context)

# ── 1. ESTRENOS PELÍCULAS ─────────────────────────────────────────────────────
async def _fetch_trending_movies(update, context):
    await _rpl(update, "🎬 Buscando estrenos…")
    year, movies, yts_page = datetime.date.today().year, [], 1
    try:
        while len(movies) < 50:
            r = requests.get(YTS_API, params={
                "sort_by":"date_added","order_by":"desc","limit":50,"page":yts_page
            }, timeout=10).json()
            batch = r.get("data",{}).get("movies") or []
            if not batch: break
            movies += [m for m in batch if str(m.get("year","")) == str(year)]
            yts_page += 1
            if yts_page > 5: break
    except Exception as e:
        await _rpl(update, f"❌ Error consultando YTS: {e}"); return SEARCH
    if not movies:
        await _rpl(update, "❌ No encontré estrenos de este año."); return SEARCH
    context.user_data.update({"all_trending": movies, "trending_offset": 0})
    return await _show_page(update, context, "all_trending", "trending_offset", TRENDING,
        f"🆕 *Últimos estrenos de {year}:*",
        lambda m: f"{m['title']} ({m['year']}) ⭐{m.get('rating','?')}")

async def select_trending(update, context):
    if not guard(update.effective_user.id): return ConversationHandler.END
    items  = context.user_data.get("all_trending", [])
    offset = context.user_data.get("trending_offset", 0)
    page   = items[offset:offset+PAGE_SIZE]
    n, has_more = len(page), len(items) > offset+PAGE_SIZE
    max_opt = n+2 if has_more else n+1
    try:
        idx = int(update.message.text.strip()) - 1
        if not (0 <= idx < max_opt): raise ValueError
    except ValueError:
        return await _bad_input(update, context, TRENDING, f"Responde un número del 1 al {max_opt}.")
    if idx == max_opt-1:
        await _rpl(update, "Cancelado."); context.user_data.clear(); return SEARCH
    if has_more and idx == n:
        context.user_data["trending_offset"] = offset+PAGE_SIZE
        return await _show_page(update, context, "all_trending", "trending_offset", TRENDING,
            f"🆕 *Estrenos de {datetime.date.today().year}:*",
            lambda m: f"{m['title']} ({m['year']}) ⭐{m.get('rating','?')}")
    movie = page[idx]
    context.user_data.update({"kind":"movie","query":movie["title"],"movie_meta":movie,"retries":0})
    return await _present_movie_qualities(update, context, movie)

# ── 2. SERIES EN TENDENCIA ────────────────────────────────────────────────────
async def _fetch_trending_series(update, context):
    await _rpl(update, "📺 Buscando series populares…")
    try:
        r = requests.get(TVMAZE_API, params={"page": 0}, timeout=10).json()
        shows = (r if isinstance(r, list) else [])[:50]
    except Exception as e:
        await _rpl(update, f"❌ Error: {e}"); return SEARCH
    if not shows:
        await _rpl(update, "❌ Sin resultados."); return SEARCH
    context.user_data.update({"all_trending_series": shows, "trending_series_offset": 0})
    return await _show_page(update, context, "all_trending_series", "trending_series_offset", TRENDING,
        "🔥 *Series populares:*",
        lambda s: f"{s.get('name','?')} ({(s.get('premiered') or '')[:4]})")

async def select_trending_series(update, context):
    # Reuses TRENDING state — distinguished by which key exists
    if context.user_data.get("all_trending") is not None:
        return await select_trending(update, context)
    if not guard(update.effective_user.id): return ConversationHandler.END
    items  = context.user_data.get("all_trending_series", [])
    offset = context.user_data.get("trending_series_offset", 0)
    page   = items[offset:offset+PAGE_SIZE]
    n, has_more = len(page), len(items) > offset+PAGE_SIZE
    max_opt = n+2 if has_more else n+1
    try:
        idx = int(update.message.text.strip()) - 1
        if not (0 <= idx < max_opt): raise ValueError
    except ValueError:
        return await _bad_input(update, context, TRENDING, f"Responde un número del 1 al {max_opt}.")
    if idx == max_opt-1:
        await _rpl(update, "Cancelado."); context.user_data.clear(); return SEARCH
    if has_more and idx == n:
        context.user_data["trending_series_offset"] = offset+PAGE_SIZE
        return await _show_page(update, context, "all_trending_series", "trending_series_offset", TRENDING,
            "🔥 *Series populares:*",
            lambda s: f"{s.get('name','?')} ({(s.get('premiered') or '')[:4]})")
    show = page[idx]
    name = show.get("name","?")
    context.user_data.update({"query": name, "retries": 0})
    return await _present_series_menu(update, context, name)

async def _present_series_menu(update, context, name):
    await _rpl(update, "🔍 Buscando series…")
    results = search_omdb_series(name)
    if len(results) > 1:
        # Multiple matches — ask user to pick
        context.user_data.update({"series_search_results": results, "retries": 0})
        lines = [f"{i+1}. {r.get('Title','?')} ({r.get('Year','?')})" for i, r in enumerate(results[:10])]
        lines.append(f"{min(len(results),10)+1}. ❌ Cancelar")
        await _rpl(update, 
            "📺 *¿A cuál de estas te refieres?*\n\n" + "\n".join(lines) + "\n\nResponde con el *número*.",
            parse_mode="Markdown",
        )
        return SELECT_SERIES_PICK
    # Single or no result — go straight with the name
    exact_title = results[0].get("Title", name) if results else name
    return await _load_series_info(update, context, exact_title)


async def select_series_pick(update, context):
    if not guard(update.effective_user.id): return ConversationHandler.END
    results = context.user_data.get("series_search_results", [])
    n = min(len(results), 10)
    try:
        idx = int(update.message.text.strip()) - 1
        if not (0 <= idx <= n): raise ValueError
    except ValueError:
        return await _bad_input(update, context, SELECT_SERIES_PICK, f"Responde un número del 1 al {n+1}.")
    if idx == n:
        await _rpl(update, "Cancelado."); context.user_data.clear(); return SEARCH
    chosen   = results[idx].get("Title", context.user_data["query"])
    imdb_id  = results[idx].get("imdbID")
    context.user_data.pop("series_search_results", None)
    return await _load_series_info(update, context, chosen, imdb_id=imdb_id)


async def _load_series_info(update, context, title, imdb_id=None):
    """Fetch full series info and show the search mode menu."""
    info = get_omdb_series_info(title, imdb_id=imdb_id)
    context.user_data["series_omdb"] = info
    # Update query to exact title so Jackett searches the right name
    context.user_data["query"] = info.get("title", title)
    poster = info.get("poster")
    if poster:
        try: await update.message.reply_photo(photo=poster)
        except Exception: pass
    real_title = info.get("title", title)
    year       = info.get("year","")
    rating     = info.get("rating")
    seasons    = info.get("totalSeasons")
    plot       = info.get("plot","")
    short      = (plot[:300].rsplit(" ",1)[0]+"…") if len(plot)>300 else plot
    header     = f"📺 *{real_title}*" + (f" ({year})" if year else "")
    if rating:  header += f"\n⭐ *IMDB:* {rating}"
    if seasons: header += f"\n📅 *Temporadas:* {seasons}"
    if short:   header += f"\n\n📝 _{short}_"
    header += "\n\n¿Cómo quieres buscar?\n\n1. 🎯 Episodio específico\n2. 📦 Temporada completa\n3. 🔎 Búsqueda general\n4. ℹ️ Info detallada"
    await _rpl(update, header, parse_mode="Markdown")
    return SELECT_SERIES_MODE

# ── 3. STATUS ─────────────────────────────────────────────────────────────────
async def _status_downloads(update, context):
    try:
        qbt = qbt_client()
        active = [t for t in qbt.torrents_info() if t.state in ("downloading","stalledDL","metaDL","checkingDL","forcedDL")]
    except Exception as e:
        await _rpl(update, f"❌ Error con qBittorrent: {e}"); return SEARCH
    if not active:
        await _rpl(update, "✅ No hay descargas activas en este momento."); return SEARCH
    lines = []
    for t in active[:10]:
        pct   = f"{t.progress*100:.1f}%"
        speed = f"{t.dlspeed/1_048_576:.1f} MB/s" if t.dlspeed > 0 else "—"
        eta   = f"{int(t.eta//3600)}h{int((t.eta%3600)//60)}m" if t.eta > 0 and t.eta < 8640000 else "—"
        lines.append(f"📥 *{t.name[:45]}*\n    {pct} · {speed} · ETA {eta}")
    await _rpl(update, "📊 *Descargas activas:*\n\n" + "\n\n".join(lines), parse_mode="Markdown")
    return SEARCH

# ── 4. CANCELAR DESCARGA ──────────────────────────────────────────────────────
async def _list_for_cancel(update, context):
    try:
        qbt = qbt_client()
        torrents = [t for t in qbt.torrents_info()
                    if t.state not in ("uploading","stalledUP","pausedUP","queuedUP","checkingUP","forcedUP","missingFiles")]
    except Exception as e:
        await _rpl(update, f"❌ Error con qBittorrent: {e}"); return SEARCH
    if not torrents:
        await _rpl(update, "✅ No hay descargas activas para cancelar."); return SEARCH
    context.user_data.update({"cancel_list": [t.hash for t in torrents], "retries": 0})
    lines = [f"{i+1}. {t.name[:50]} ({t.state})" for i,t in enumerate(torrents)]
    lines.append(f"{len(torrents)+1}. ❌ No cancelar nada")
    await _rpl(update, 
        "❌ *¿Cuál descarga quieres cancelar?*\n\n" + "\n".join(lines) + "\n\nResponde con el *número*.",
        parse_mode="Markdown",
        reply_markup=_kb_n(len(torrents), [len(torrents)+1]),
    )
    return CANCEL_DOWNLOAD

async def confirm_cancel(update, context):
    if not guard(update.effective_user.id): return ConversationHandler.END
    hashes = context.user_data.get("cancel_list", [])
    n = len(hashes)
    try:
        idx = int(update.message.text.strip()) - 1
        if not (0 <= idx <= n): raise ValueError
    except ValueError:
        return await _bad_input(update, context, CANCEL_DOWNLOAD, f"Responde un número del 1 al {n+1}.")
    if idx == n:
        await _rpl(update, "De acuerdo, no se canceló nada.")
        context.user_data.clear(); return SEARCH
    h = hashes[idx]
    try:
        qbt = qbt_client()
        qbt.torrents_delete(delete_files=False, torrent_hashes=h)
        await _rpl(update, "✅ Descarga cancelada (el archivo parcial se conserva).")
    except Exception as e:
        await _rpl(update, f"❌ Error: {e}")
    context.user_data.clear(); return SEARCH

# ── 5. COLA / PENDIENTES ──────────────────────────────────────────────────────
async def _show_queue(update, context):
    try:
        qbt = qbt_client()
        queue = [t for t in qbt.torrents_info() if t.state in ("queuedDL","queuedUP")]
        paused = [t for t in qbt.torrents_info() if t.state in ("pausedDL","pausedUP")]
    except Exception as e:
        await _rpl(update, f"❌ Error con qBittorrent: {e}"); return SEARCH
    lines = []
    if queue:
        lines.append("⏳ *En cola:*")
        for t in queue[:10]:
            lines.append(f"  • {t.name[:50]}")
    if paused:
        lines.append("\n⏸ *Pausados:*")
        for t in paused[:10]:
            lines.append(f"  • {t.name[:50]}")
    if not lines:
        await _rpl(update, "✅ No hay torrents en cola ni pausados."); return SEARCH
    await _rpl(update, "\n".join(lines), parse_mode="Markdown")
    return SEARCH

# ── 6. BUSCAR EN BIBLIOTECA ───────────────────────────────────────────────────
async def library_search(update, context):
    if not guard(update.effective_user.id): return ConversationHandler.END
    query = update.message.text.strip()
    await _rpl(update, f"🔍 Buscando *{query}* en tu biblioteca…", parse_mode="Markdown", reply_markup=KB_REMOVE)
    found = find_in_library(query, ALL_SCAN_DIRS)
    if not found:
        await _rpl(update, "❌ No encontré nada con ese título en tu biblioteca.")
    else:
        lines = [f"• `{p}`" for p in found[:15]]
        extra = f"\n_...y {len(found)-15} más_" if len(found)>15 else ""
        await _rpl(update, 
            "📂 *Encontrado:*\n\n" + "\n".join(lines) + extra,
            parse_mode="Markdown",
        )
    context.user_data.clear(); return SEARCH

# ── 7. ARCHIVOS RECIENTES ─────────────────────────────────────────────────────
def _clean_title_from_path(fp):
    parts = fp.split(os.sep)
    base_names = {"peliculasf","ninosf","seriesf","seriesninosf",
                  "peliculase","niñose","seriese","seriesninose",
                  "peliculas","ninos","series","seriosninos"}
    candidate = None
    for part in reversed(parts[:-1]):
        if normalize(part) not in base_names and part:
            candidate = part; break
    if not candidate:
        candidate = os.path.splitext(os.path.basename(fp))[0]
    noise = r"[.\-_]*(1080p|720p|2160p|4k|bluray|bdrip|webrip|web|hdtv|x264|x265|hevc|aac|ac3|yts|mx|eztv|extended|imax|remastered|hdr|remux|proper).*"
    clean = re.sub(noise, "", candidate, flags=re.IGNORECASE).strip(" .-_()")
    year_m = re.search(r"(19|20)\d{2}", clean)
    year   = year_m.group(0) if year_m else None
    title  = re.sub(r"\(?(19|20)\d{2}\)?", "", clean).strip(" .-_()") if year_m else clean
    title  = re.sub(r"[._]", " ", title).strip()
    title  = re.sub(r"\s+", " ", title).strip()
    return title, year


async def _show_recent(update, context):
    files = get_recent_files(ALL_SCAN_DIRS, limit=15)
    if not files:
        await _rpl(update, "❌ No encontré archivos recientes."); return SEARCH
    lines = []
    for fp in files:
        mtime       = datetime.datetime.fromtimestamp(os.path.getmtime(fp))
        title, year = _clean_title_from_path(fp)
        yr          = f" ({year})" if year else ""
        lines.append(f"🕐 *{mtime.strftime('%d/%m  %H:%M')}*  —  {title}{yr}")
    await _rpl(update, "🕐 *Archivos recientes:*\n\n" + "\n".join(lines), parse_mode="Markdown")
    return SEARCH


async def similar_search(update, context):
    if not guard(update.effective_user.id): return ConversationHandler.END
    query = update.message.text.strip()
    await _rpl(update, f"🎯 Buscando similares a *{query}*…", parse_mode="Markdown")
    d = get_omdb_data(query)
    if not d:
        await _rpl(update, "❌ No encontré info en OMDB para ese título.")
        context.user_data.clear(); return SEARCH
    genre  = d.get("Genre","").split(",")[0].strip()
    year   = d.get("Year","")[:4]
    kind   = "movie" if d.get("Type") == "movie" else "series"
    title  = d.get("Title", query)
    rating = d.get("imdbRating","?")
    # Search YTS by genre for movies
    lines = []
    if kind == "movie":
        try:
            r = requests.get(YTS_API, params={
                "genre": genre.lower(), "sort_by":"rating","order_by":"desc","limit":10
            }, timeout=10).json()
            movies = r.get("data",{}).get("movies") or []
            similar = [m for m in movies if m["title"].lower() != title.lower()][:8]
            for m in similar:
                lines.append(f"🎬 {m['title']} ({m['year']}) ⭐{m.get('rating','?')}")
        except Exception: pass
    text = f"🎯 *Similar a {title}* ({year}) ⭐{rating}\n📌 Género: _{genre}_\n\n"
    if lines:
        text += "\n".join(lines)
    else:
        text += "_No encontré recomendaciones automáticas. Prueba buscar por género directamente._"
    await _rpl(update, text, parse_mode="Markdown")
    context.user_data.clear(); return SEARCH

# ── 9. TORRENTS ATASCADOS ─────────────────────────────────────────────────────
async def _show_stalled(update, context):
    try:
        qbt = qbt_client()
        stalled = [t for t in qbt.torrents_info() if "stalled" in t.state.lower() and "UP" not in t.state]
    except Exception as e:
        await _rpl(update, f"❌ Error: {e}"); return SEARCH
    if not stalled:
        await _rpl(update, "✅ No hay torrents atascados."); return SEARCH
    lines = []
    for t in stalled[:10]:
        pct = f"{t.progress*100:.1f}%"
        lines.append(f"⚠️ *{t.name[:50]}*\n    {pct} — seeds: {t.num_seeds}")
    await _rpl(update, "⚠️ *Torrents atascados:*\n\n" + "\n\n".join(lines), parse_mode="Markdown")
    return SEARCH

# ── 10. AGREGAR USUARIO ───────────────────────────────────────────────────────
async def add_user(update, context):
    if not guard(update.effective_user.id): return ConversationHandler.END
    text = update.message.text.strip()
    if text.lower() == "cancelar":
        await _rpl(update, "Cancelado.")
        context.user_data.clear(); return SEARCH
    if not text.isdigit():
        return await _bad_input(update, context, ADD_USER, "Manda el ID numérico o escribe *cancelar*.")
    new_id = int(text)
    ids = load_allowed()
    if new_id in ids:
        await _rpl(update, f"ℹ️ El usuario {new_id} ya tiene acceso.")
    else:
        ids.add(new_id)
        save_allowed(ids)
        await _rpl(update, f"✅ Usuario {new_id} agregado. Ya puede usar el bot.")
    context.user_data.clear(); return SEARCH

# ── BÚSQUEDA PELÍCULAS (YTS) ──────────────────────────────────────────────────
async def _search_yts(update, context):
    query = context.user_data["query"]
    await _rpl(update, f"🔍 Buscando película *{query}*…", parse_mode="Markdown", reply_markup=KB_REMOVE)
    try:
        r = requests.get(YTS_API, params={"query_term":query,"limit":20}, timeout=10).json()
    except Exception as e:
        await _rpl(update, f"❌ Error al consultar YTS: {e}"); return SEARCH
    if r.get("status") != "ok" or r["data"]["movie_count"] == 0:
        await _rpl(update, "❌ Sin resultados en YTS."); return SEARCH
    movies = r["data"]["movies"]
    context.user_data.update({"all_movies":movies,"movie_offset":0,"retries":0})
    if len(movies) == 1:
        context.user_data["movie_meta"] = movies[0]
        return await _present_movie_qualities(update, context, movies[0])
    return await _show_page(update, context, "all_movies","movie_offset", SELECT_MOVIE,
        "🎬 *Películas encontradas:*",
        lambda m: f"{m['title']} ({m['year']}) ⭐{m.get('rating','?')}")

async def _present_movie_qualities(update, context, movie):
    raw = movie.get("torrents") or []
    if not raw:
        await _rpl(update, "❌ Sin torrents para esta película."); return SEARCH
    context.user_data.update({"selected_title":f"{movie['title']} ({movie['year']})", "kind":"movie", "movie_meta":movie})
    rating  = movie.get("rating")
    summary = movie.get("description_full") or movie.get("summary") or ""
    short   = (summary[:300].rsplit(" ",1)[0]+"…") if len(summary)>300 else summary
    header  = f"🎞 *{movie['title']} ({movie['year']})*"
    if rating: header += f"\n⭐ *IMDB:* {rating}"
    if short:  header += f"\n\n📝 _{short}_"
    header += "\n\n*Calidades disponibles:*"
    poster = movie.get("large_cover_image") or movie.get("medium_cover_image")
    if not poster: poster = get_omdb_poster(movie["title"], str(movie.get("year","")))
    if poster:
        try: await update.message.reply_photo(photo=poster)
        except Exception: pass
    torrents = [{
        "hash":    t["hash"],
        "magnet":  build_magnet(t["hash"], movie["title"]),
        "display": f"{t.get('quality','?')} {t.get('type','')} — {t.get('size','?')}  🌱{t.get('seeds',0)}",
        "quality": f"{t.get('quality','')} {t.get('type','')}".strip(),
    } for t in raw]
    context.user_data.update({"all_torrents":torrents,"torrent_offset":0,"torrent_header":header})
    return await _show_page(update, context, "all_torrents","torrent_offset", SELECT_TORRENT, header, lambda t: t["display"])

# ── BÚSQUEDA SERIES (Jackett) ─────────────────────────────────────────────────
async def _search_jackett(update, context):
    query  = context.user_data["query"]
    mode   = context.user_data.get("series_mode")
    detail = context.user_data.get("series_detail")
    if mode == "episode" and detail:
        sq = f"{query} {detail.upper()}"; header = f"📺 *{query}* — {detail.upper()}\n\n*Torrents encontrados:*"
    elif mode == "season" and detail:
        sq = f"{query} S{detail.zfill(2)}"; header = f"📺 *{query}* — Temporada {detail}\n\n*Torrents encontrados:*"
    else:
        sq = query; header = f"📺 *{query}*\n\n*Todos los resultados:*"
    await _rpl(update, f"🔍 Buscando *{sq}*…", parse_mode="Markdown")
    try:
        r = requests.get(JACKETT_URL, params={"apikey":JACKETT_KEY,"Query":sq}, timeout=15).json()
    except Exception as e:
        await _rpl(update, f"❌ Error al consultar Jackett: {e}"); return SEARCH
    results = r.get("Results") or []
    if not results:
        await _rpl(update, "❌ Sin resultados."); return SEARCH
    seen, unique = {}, []
    for t in results:
        key = re.sub(r"[^a-z0-9]","",t.get("Title","").lower())
        if key not in seen: seen[key]=True; unique.append(t)
    query_words = re.findall(r"[a-z0-9]+", query.lower())
    filtered = [t for t in unique if all(w in t.get("Title","").lower() for w in query_words)]
    if len(filtered) >= 3: unique = filtered
    def score(t):
        title = t.get("Title",""); s = 0
        if title.lower().startswith(query.lower()): s += 200
        if mode == "season" and re.search(r"complete|season.pack", title, re.IGNORECASE): s += 150
        if detail:
            if re.search(re.escape(detail), title, re.IGNORECASE): s += 100
            em = re.search(r"[Ss](\d{1,2})[Ee](\d{1,2})", title)
            ed = re.search(r"[Ss](\d{1,2})[Ee](\d{1,2})", detail, re.IGNORECASE) if detail else None
            if em and mode == "episode" and ed:
                if em.group(1).zfill(2)==ed.group(1).zfill(2) and em.group(2).zfill(2)==ed.group(2).zfill(2): s+=50
                else: s-=80
            if mode == "season":
                sm = re.search(r"[Ss](\d{1,2})", title)
                if sm and sm.group(1).zfill(2) != detail.zfill(2): s-=80
        return (s, t.get("Seeders",0))
    unique.sort(key=score, reverse=True)
    context.user_data.update({"selected_title":query,"kind":"series","all_torrents":[{
        "hash":    t.get("InfoHash") or "",
        "magnet":  t.get("MagnetUri") or t.get("Link",""),
        "display": f"{t.get('Title','?')[:70]} — {(lambda z: f'{z/1_073_741_824:.1f} GB' if z>1_073_741_824 else f'{z/1_048_576:.0f} MB')(t.get('Size',0))}  🌱{t.get('Seeders',0)}",
        "quality": t.get("Title",""),
    } for t in unique],"torrent_offset":0,"torrent_header":header})
    return await _show_page(update, context, "all_torrents","torrent_offset", SELECT_TORRENT, header, lambda t: t["display"])

# ── VERIFICACIÓN BIBLIOTECA ───────────────────────────────────────────────────
async def _check_library(update, context, next_fn):
    kind   = context.user_data.get("kind")
    mode   = context.user_data.get("series_mode")
    detail = context.user_data.get("series_detail")
    if kind == "movie":
        search_title = context.user_data.get("selected_title") or context.user_data["query"]
        found = find_in_library(search_title, MOVIE_SCAN_DIRS, exact=True); label = "película"
    else:
        query = context.user_data["query"]
        found = find_episode_in_library(query, detail, SERIES_SCAN_DIRS) if mode=="episode" and detail else find_in_library(query, SERIES_SCAN_DIRS, exact=True)
        label = "serie/episodio"
    if not found: return await next_fn(update, context)
    lines = [f"• `{p}`" for p in found[:5]]
    extra = "\n_...y más_" if len(found)>5 else ""
    search_q  = (context.user_data.get("selected_title") or context.user_data.get("query","")).rsplit("(",1)[0].strip()
    msg = (f"⚠️ *Ya tienes esta {label} en tu biblioteca:*\n\n" + "\n".join(lines) + extra +
           "\n\n1. ✅ Descargar de todas formas\n2. ❌ Cancelar")
    context.user_data["retries"] = 0
    await _rpl(update, msg, parse_mode="Markdown", reply_markup=KB_YES_NO)
    return WARN_EXISTING

async def warn_existing(update, context):
    if not guard(update.effective_user.id): return ConversationHandler.END
    answer = update.message.text.strip()
    if answer == "2":
        await _rpl(update, "❌ Descarga cancelada.")
        context.user_data.clear(); return SEARCH
    if answer != "1":
        return await _bad_input(update, context, WARN_EXISTING, "Responde *1* para continuar o *2* para cancelar.")
    if context.user_data.get("kind") == "movie":
        await _rpl(update, "📁 *¿Dónde va esta película?*\n\n1. PelículasF\n2. NiñosF", parse_mode="Markdown", reply_markup=KB_YES_NO)
        context.user_data["retries"] = 0; return SELECT_MOVIE_FOLDER
    else:
        matches = find_series_folder(context.user_data["query"], ALL_SERIES_BASES)
        return await _show_folder_options(update, context, matches)

# ── CARPETAS SERIES ───────────────────────────────────────────────────────────
async def _show_folder_options(update, context, matches):
    context.user_data.update({"folder_matches":matches,"retries":0})
    query = context.user_data["query"]
    lines = [f"{i+1}. 📂 {'/'.join(p.split('/')[-2:])}" for i,p in enumerate(matches)]
    n = len(matches)
    lines.append(f"{n+1}. ➕ Crear '{query}' en SeriesF")
    lines.append(f"{n+2}. ➕ Crear '{query}' en SeriesNiñosF")
    header = "📁 *Carpeta encontrada:*" if matches else "📁 *No encontré carpeta existente.*"
    await _rpl(update, f"{header}\n\n" + "\n".join(lines) + "\n\nResponde con el *número*.", parse_mode="Markdown")
    return SELECT_EXISTING_OR_NEW

# ── CONFIRMACIÓN ──────────────────────────────────────────────────────────────
async def _show_confirm(update, context):
    torrent = context.user_data["selected_torrent"]
    title   = context.user_data["selected_title"]
    folder  = context.user_data["selected_folder"]
    kind    = context.user_data.get("kind","movie")
    icon    = "🎬" if kind=="movie" else "📺"
    meta_lines = ""
    if kind == "movie":
        meta    = context.user_data.get("movie_meta") or {}
        rating  = meta.get("rating")
        summary = meta.get("description_full") or meta.get("summary") or ""
        short   = (summary[:300].rsplit(" ",1)[0]+"…") if len(summary)>300 else summary
        if rating: meta_lines += f"⭐ *IMDB:* {rating}\n"
        if short:  meta_lines += f"\n📝 _{short}_\n"
    await _rpl(update, 
        f"✅ *Confirmar descarga*\n\n{icon} {title}\n{meta_lines}"
        f"💾 {torrent['display']}\n📁 `{folder}`\n\n1. ✅ Confirmar\n2. ❌ Cancelar",
        parse_mode="Markdown",
        reply_markup=KB_YES_NO,
    )
    return CONFIRM

# ── HANDLERS DE CONVERSACIÓN ──────────────────────────────────────────────────
async def search_movie_handler(update, context):
    if not guard(update.effective_user.id): return ConversationHandler.END
    context.user_data.update({"query":update.message.text.strip(),"retries":0})
    await _rpl(update, "¿Qué estás buscando?\n\n1. 🎬 Película\n2. 📺 Serie", reply_markup=KB_YES_NO)
    return SELECT_TYPE

async def select_type(update, context):
    if not guard(update.effective_user.id): return ConversationHandler.END
    answer = update.message.text.strip()
    if answer == "1":
        context.user_data["retries"]=0; return await _search_yts(update, context)
    if answer == "2":
        context.user_data["retries"]=0
        return await _present_series_menu(update, context, context.user_data["query"])
    return await _bad_input(update, context, SELECT_TYPE, "Responde *1* para película o *2* para serie.")

async def select_series_mode(update, context):
    if not guard(update.effective_user.id): return ConversationHandler.END
    answer = update.message.text.strip()
    if answer == "1":
        context.user_data.update({"series_mode":"episode","retries":0})
        await _rpl(update, "Escribe el episodio en formato *S01E03*:", parse_mode="Markdown", reply_markup=KB_REMOVE)
        return SELECT_SERIES_DETAIL
    if answer == "2":
        context.user_data.update({"series_mode":"season","retries":0})
        await _rpl(update, "¿Qué temporada? Escribe el número (ej: *2*):", parse_mode="Markdown", reply_markup=KB_REMOVE)
        return SELECT_SERIES_DETAIL
    if answer == "3":
        context.user_data.update({"series_mode":"general","series_detail":None,"retries":0})
        return await _search_jackett(update, context)
    if answer == "4":
        context.user_data["retries"]=0; return await show_series_info(update, context)
    return await _bad_input(update, context, SELECT_SERIES_MODE, "Responde *1*, *2*, *3* o *4*.")

async def show_series_info(update, context):
    if not guard(update.effective_user.id): return ConversationHandler.END
    query = context.user_data["query"]
    info  = context.user_data.get("series_omdb") or get_omdb_series_info(query)
    total = int(info.get("totalSeasons") or 0)
    if total == 0:
        await _rpl(update, "❌ No encontré información detallada en OMDB.")
        await _rpl(update, "¿Cómo quieres buscar?\n\n1. 🎯 Episodio específico\n2. 📦 Temporada completa\n3. 🔎 Búsqueda general\n4. ℹ️ Info detallada", reply_markup=KB_4)
        return SELECT_SERIES_MODE
    await _rpl(update, "⏳ Cargando episodios…")
    eps_map = get_omdb_episodes_per_season(query, total)
    lines = [f"T{s:02d}: {eps_map.get(s,'?')} episodios" for s in range(1, total+1)]
    total_eps = sum(v for v in eps_map.values())
    text = (f"📺 *{info.get('title',query)}*\n📅 {total} temporadas — {total_eps} episodios en total\n\n"
            + "\n".join(lines)
            + "\n\n¿Cómo quieres buscar?\n\n1. 🎯 Episodio específico\n2. 📦 Temporada completa\n3. 🔎 Búsqueda general\n4. ℹ️ Info detallada")
    await _rpl(update, text, parse_mode="Markdown")
    return SELECT_SERIES_MODE

async def select_series_detail(update, context):
    if not guard(update.effective_user.id): return ConversationHandler.END
    detail = update.message.text.strip()
    mode   = context.user_data.get("series_mode")
    if mode == "episode" and not re.match(r"^[Ss]\d{1,2}[Ee]\d{1,2}$", detail):
        return await _bad_input(update, context, SELECT_SERIES_DETAIL, "Formato inválido. Usa *S01E03*.")
    if mode == "season" and not re.match(r"^\d{1,2}$", detail):
        return await _bad_input(update, context, SELECT_SERIES_DETAIL, "Escribe solo el número (ej: *2*).")
    context.user_data.update({"series_detail":detail,"retries":0})
    return await _search_jackett(update, context)

async def select_movie(update, context):
    if not guard(update.effective_user.id): return ConversationHandler.END
    items  = context.user_data.get("all_movies",[])
    offset = context.user_data.get("movie_offset",0)
    page   = items[offset:offset+PAGE_SIZE]
    n, has_more = len(page), len(items) > offset+PAGE_SIZE
    max_opt = n+2 if has_more else n+1
    try:
        idx = int(update.message.text.strip()) - 1
        if not (0 <= idx < max_opt): raise ValueError
    except ValueError:
        return await _bad_input(update, context, SELECT_MOVIE, f"Responde un número del 1 al {max_opt}.")
    if idx == max_opt-1:
        await _rpl(update, "Cancelado."); context.user_data.clear(); return SEARCH
    if has_more and idx == n:
        context.user_data["movie_offset"] = offset+PAGE_SIZE
        return await _show_page(update, context,"all_movies","movie_offset",SELECT_MOVIE,
            "🎬 *Películas encontradas:*", lambda m: f"{m['title']} ({m['year']}) ⭐{m.get('rating','?')}")
    movie = page[idx]
    context.user_data.update({"movie_meta":movie,"retries":0})
    return await _present_movie_qualities(update, context, movie)

async def select_torrent(update, context):
    if not guard(update.effective_user.id): return ConversationHandler.END
    items  = context.user_data.get("all_torrents",[])
    offset = context.user_data.get("torrent_offset",0)
    header = context.user_data.get("torrent_header","")
    page   = items[offset:offset+PAGE_SIZE]
    n, has_more = len(page), len(items) > offset+PAGE_SIZE
    max_opt = n+2 if has_more else n+1
    try:
        idx = int(update.message.text.strip()) - 1
        if not (0 <= idx < max_opt): raise ValueError
    except ValueError:
        return await _bad_input(update, context, SELECT_TORRENT, f"Responde un número del 1 al {max_opt}.")
    if idx == max_opt-1:
        await _rpl(update, "Cancelado."); context.user_data.clear(); return SEARCH
    if has_more and idx == n:
        context.user_data["torrent_offset"] = offset+PAGE_SIZE
        return await _show_page(update, context,"all_torrents","torrent_offset",SELECT_TORRENT, header, lambda t: t["display"])
    context.user_data["selected_torrent"] = page[idx]
    if context.user_data.get("kind") == "movie":
        async def _goto_movie_folder(u,c):
            c.user_data["retries"]=0
            await u.message.reply_text("📁 *¿Dónde va esta película?*\n\n1. PelículasF\n2. NiñosF", parse_mode="Markdown")
            return SELECT_MOVIE_FOLDER
        return await _check_library(update, context, _goto_movie_folder)
    else:
        async def _goto_series_folders(u,c):
            m = find_series_folder(c.user_data["query"], ALL_SERIES_BASES)
            return await _show_folder_options(u,c,m)
        return await _check_library(update, context, _goto_series_folders)

async def select_movie_folder(update, context):
    if not guard(update.effective_user.id): return ConversationHandler.END
    answer = update.message.text.strip()
    if answer not in ("1","2"):
        return await _bad_input(update, context, SELECT_MOVIE_FOLDER, "Responde *1* (PelículasF) o *2* (NiñosF).")
    context.user_data.update({"selected_folder":MOVIE_FOLDERS[int(answer)-1],"retries":0})
    return await _show_confirm(update, context)

async def select_existing_or_new(update, context):
    if not guard(update.effective_user.id): return ConversationHandler.END
    matches = context.user_data.get("folder_matches",[])
    n = len(matches)
    try:
        idx = int(update.message.text.strip()) - 1
        if not (0 <= idx < n+2): raise ValueError
    except ValueError:
        return await _bad_input(update, context, SELECT_EXISTING_OR_NEW, "Opción inválida.")
    if idx < n:
        context.user_data.update({"selected_folder":matches[idx],"retries":0})
        return await _show_confirm(update, context)
    base = NEW_SERIES_FOLDER if idx==n else NEW_SERIES_NINOS_FOLDER
    query = context.user_data["query"]
    new_folder = os.path.join(base, query)
    try: os.makedirs(new_folder, exist_ok=True)
    except Exception as e:
        await _rpl(update, f"❌ No se pudo crear la carpeta: {e}")
        context.user_data.clear(); return SEARCH
    context.user_data.update({"selected_folder":new_folder,"retries":0})
    return await _show_confirm(update, context)

async def confirm_download(update, context):
    if not guard(update.effective_user.id): return ConversationHandler.END
    answer = update.message.text.strip()
    if answer == "2":
        await _rpl(update, "❌ Descarga cancelada.")
        context.user_data.clear(); return SEARCH
    if answer != "1":
        return await _bad_input(update, context, CONFIRM, "Responde *1* para confirmar o *2* para cancelar.")
    torrent = context.user_data["selected_torrent"]
    title   = context.user_data["selected_title"]
    folder  = context.user_data["selected_folder"]
    kind    = context.user_data.get("kind","movie")
    magnet  = torrent.get("magnet") or build_magnet(torrent["hash"], title)
    try:
        qbt    = qbt_client()
        before = {t.hash for t in qbt.torrents_info()}
        qbt.torrents_add(urls=magnet, save_path=folder)
        real_hash = torrent.get("hash") or ""
        for _ in range(10):
            time.sleep(1)
            after = {t.hash for t in qbt.torrents_info()}
            new_h = after - before
            if new_h: real_hash = new_h.pop(); break
        watching = context.bot_data.setdefault("watching", {})
        if real_hash:
            watching[real_hash] = {"chat_id":update.effective_chat.id,"title":title,
                                   "quality":torrent.get("quality",""),"folder":folder,"kind":kind}
        icon = "🎬" if kind=="movie" else "📺"
        await _rpl(update, 
            f"🚀 *¡Descarga iniciada!*\n\n{icon} {title}\n💾 {torrent['display']}\n📁 `{folder}`\n\n_Te aviso cuando termine_ 🔔",
            parse_mode="Markdown",
        )
        # Notify owner if a different user initiated the download
        user = update.effective_user
        if user.id != ALLOWED_USER_ID:
            username = f"@{user.username}" if user.username else f"{user.first_name} (ID {user.id})"
            notify_text = (f"👤 *{username}* inició una descarga:\n\n"
                           f"{icon} {title}\n💾 {torrent['display']}\n📁 `{folder}`")
            try:
                # Send poster to owner if available
                poster = None
                if kind == "movie":
                    meta   = context.user_data.get("movie_meta") or {}
                    poster = meta.get("large_cover_image") or meta.get("medium_cover_image")
                    if not poster:
                        poster = get_omdb_poster(title.rsplit("(",1)[0].strip())
                else:
                    info   = context.user_data.get("series_omdb") or {}
                    poster = info.get("poster")
                if poster:
                    await context.bot.send_photo(chat_id=ALLOWED_USER_ID, photo=poster, caption=notify_text, parse_mode="Markdown")
                else:
                    await context.bot.send_message(chat_id=ALLOWED_USER_ID, text=notify_text, parse_mode="Markdown")
            except Exception as e:
                logger.warning(f"No se pudo notificar al dueño: {e}")
    except Exception as e:
        await _rpl(update, f"❌ Error con qBittorrent: {e}")
    context.user_data.clear(); return SEARCH




# ── ÚLTIMAS DESCARGAS ─────────────────────────────────────────────────────────

RECENT_DIRS = {
    "movie":       ["/mnt/DatosD/Películas", "/mnt/DatosE/PelículasE", "/mnt/DatosF/PelículasF"],
    "kids_movie":  ["/mnt/DatosD/Niños", "/mnt/DatosE/NiñosE", "/mnt/DatosF/NiñosF"],
    "series":      ["/mnt/DatosD/Series", "/mnt/DatosE/SeriesE", "/mnt/DatosF/SeriesF"],
    "kids_series": ["/mnt/DatosD/SeriesNiños", "/mnt/DatosE/SeriesNiñosE", "/mnt/DatosF/SeriesNiñosF"],
}
RECENT_LABELS = {
    "movie":       "🎬 Películas",
    "kids_movie":  "👶 Niños",
    "series":      "📺 Series",
    "kids_series": "🧒 Series Niños",
}
RECENT_ORDER = ["movie", "kids_movie", "series", "kids_series"]


def get_recent_by_category(cat, limit=10):
    """Use ls -lt to get sorted entries fast, then merge across dirs."""
    import subprocess, datetime
    dirs  = RECENT_DIRS.get(cat, [])
    items = []  # list of (datetime, name)
    for base in dirs:
        if not os.path.isdir(base): continue
        try:
            # ls -lt: sorted newest first, long format
            result = subprocess.run(
                ["ls", "--time-style=+%Y-%m-%d %H:%M", "-lt", base],
                capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.splitlines():
                # format: perms links owner group size date time name
                parts = line.split(None, 7)
                if len(parts) < 8: continue
                if parts[0] == "total": continue
                if not parts[0][0] in "dl-": continue
                try:
                    dt   = datetime.datetime.strptime(f"{parts[5]} {parts[6]}", "%Y-%m-%d %H:%M")
                    name = parts[7].strip()
                    items.append((dt, name))
                except ValueError:
                    continue
        except (PermissionError, OSError, subprocess.TimeoutExpired):
            continue
    # Sort all dirs combined, newest first
    items.sort(key=lambda x: x[0], reverse=True)
    return items[:limit]


def clean_entry_name(name):
    name = re.sub(r"[.\-_]*(1080p|720p|2160p|4k|bluray|bdrip|webrip|web|hdtv|x264|x265|hevc|aac|yts|mx|eztv|extended|imax|hdr|remux|proper).*", "", name, flags=re.IGNORECASE)
    name = re.sub(r"[._]", " ", name).strip(" -_()")
    return name


async def _show_recent_category(update, context, cat):
    context.user_data["recent_cat"] = cat
    context.user_data["retries"]    = 0
    label    = RECENT_LABELS[cat]
    await _rpl(update, f"🕐 Cargando {RECENT_LABELS[cat]}…")
    import asyncio, functools
    loop  = asyncio.get_running_loop()
    try:
        items = await asyncio.wait_for(
            loop.run_in_executor(None, functools.partial(get_recent_by_category, cat)),
            timeout=10
        )
    except asyncio.TimeoutError:
        await _rpl(update, "❌ Tardó demasiado. Intenta de nuevo.")
        context.user_data.clear(); return SEARCH
    logger.info(f"get_recent_by_category({cat}) returned {len(items)} items")
    cat_idx  = RECENT_ORDER.index(cat)
    prev_cat = RECENT_ORDER[(cat_idx - 1) % len(RECENT_ORDER)]
    next_cat = RECENT_ORDER[(cat_idx + 1) % len(RECENT_ORDER)]
    prev_lbl = RECENT_LABELS[prev_cat]
    next_lbl = RECENT_LABELS[next_cat]

    if not items:
        entries = "Sin entradas"
        context.user_data["recent_items"] = []
    else:
        # Build full paths for delete
        dirs  = RECENT_DIRS.get(cat, [])
        paths = {}
        for base in dirs:
            if not os.path.isdir(base): continue
            try:
                for e in os.scandir(base):
                    paths[e.name] = e.path
            except OSError:
                continue
        context.user_data["recent_items"] = [
            paths.get(name, name) for _, name in items
        ]
        lines = []
        for i, (dt, name) in enumerate(items):
            cname = clean_entry_name(name)
            lines.append(f"{i+1}. 🕐 {dt.strftime('%d/%m  %H:%M')}  {cname}")
        entries = "\n".join(lines)

    n = len(items)
    nav = f"\n\nNavegar: {n+1}. {prev_lbl}  |  {n+2}. {next_lbl}  |  {n+3}. ❌ Cerrar"
    if items:
        nav = f"\n\nToca un número para borrar.{nav}"
    text = f"Últimas descargas — {label}\n\n{entries}{nav}"
    await _rpl(update, text)
    return RECENT_CATEGORY


async def handle_recent_category(update, context):
    if not guard(update.effective_user.id): return ConversationHandler.END
    answer   = update.message.text.strip()
    cat      = context.user_data.get("recent_cat", "movie")
    cat_idx  = RECENT_ORDER.index(cat)
    prev_cat = RECENT_ORDER[(cat_idx - 1) % len(RECENT_ORDER)]
    next_cat = RECENT_ORDER[(cat_idx + 1) % len(RECENT_ORDER)]
    items    = context.user_data.get("recent_items", [])
    n        = len(items)

    try:
        idx = int(answer) - 1
    except ValueError:
        return await _bad_input(update, context, RECENT_CATEGORY, f"Responde un número.")

    # Navigate prev
    if idx == n:
        return await _show_recent_category(update, context, prev_cat)
    # Navigate next
    if idx == n + 1:
        return await _show_recent_category(update, context, next_cat)
    # Close
    if idx == n + 2:
        await _rpl(update, "Cerrado.")
        context.user_data.clear(); return SEARCH
    # Select item to delete
    if 0 <= idx < n:
        target = items[idx]
        context.user_data["delete_target"] = target
        context.user_data["retries"] = 0
        short = "/".join(target.split("/")[-2:])
        await _rpl(update, 
            f"⚠️ Primera confirmación\n\n"
            f"¿Seguro que quieres borrar?\n{short}\n\n"
            f"Escribe sí para continuar o cualquier otra cosa para cancelar.",
        )
        return DELETE_CONFIRM1

    return await _bad_input(update, context, RECENT_CATEGORY, f"Responde un número del 1 al {n+3}.")


# ── BORRAR PELÍCULA / SERIE ───────────────────────────────────────────────────

async def delete_search(update, context):
    if not guard(update.effective_user.id): return ConversationHandler.END
    query = update.message.text.strip()
    found = find_in_library(query, ALL_SCAN_DIRS)
    if not found:
        await _rpl(update, "❌ No encontré nada con ese título en tu biblioteca.")
        context.user_data.clear(); return SEARCH
    # Keep only top-level folders/files (not nested files inside a folder that's already listed)
    # Deduplicate: if a file's parent folder is already in found, skip the file
    top = []
    found_set = set(found)
    for fp in found:
        parent = os.path.dirname(fp)
        if parent not in found_set:
            top.append(fp)
    if not top:
        top = found
    context.user_data.update({"delete_results": top, "retries": 0})
    lines = [f"{i+1}. {'/'.join(p.split('/')[-2:])}" for i, p in enumerate(top)]
    lines.append(f"{len(top)+1}. ❌ Cancelar")
    await _rpl(update, 
        f"🗑 *Resultados para borrar:*\n\n" + "\n".join(lines) + "\n\nResponde con el *número*.",
        parse_mode="Markdown",
    )
    return DELETE_SELECT


async def delete_select(update, context):
    if not guard(update.effective_user.id): return ConversationHandler.END
    results = context.user_data.get("delete_results", [])
    n = len(results)
    try:
        idx = int(update.message.text.strip()) - 1
        if not (0 <= idx <= n): raise ValueError
    except ValueError:
        return await _bad_input(update, context, DELETE_SELECT, f"Responde un número del 1 al {n+1}.")
    if idx == n:
        await _rpl(update, "Cancelado."); context.user_data.clear(); return SEARCH
    target = results[idx]
    context.user_data["delete_target"] = target
    context.user_data["retries"] = 0
    short = "/".join(target.split("/")[-2:])
    await _rpl(update, 
        f"⚠️ *Primera confirmación*\n\n"
        f"¿Seguro que quieres borrar?\n`{short}`\n\n"
        f"Escribe *sí* para continuar o cualquier otra cosa para cancelar.",
        parse_mode="Markdown",
    )
    return DELETE_CONFIRM1


async def delete_confirm1(update, context):
    if not guard(update.effective_user.id): return ConversationHandler.END
    answer = update.message.text.strip().lower().replace("í","i")
    if answer != "si":
        await _rpl(update, "Cancelado. No se borró nada.")
        context.user_data.clear(); return SEARCH
    target = context.user_data.get("delete_target","")
    short  = "/".join(target.split("/")[-2:])
    context.user_data["retries"] = 0
    await _rpl(update, 
        f"🚨 *Segunda confirmación*\n\n"
        f"Esta acción es *irreversible*. ¿Confirmas borrar?\n`{short}`\n\n"
        f"Escribe *sí* para borrar definitivamente.",
        parse_mode="Markdown",
    )
    return DELETE_CONFIRM2


async def delete_confirm2(update, context):
    if not guard(update.effective_user.id): return ConversationHandler.END
    answer = update.message.text.strip().lower().replace("í","i")
    if answer != "si":
        await _rpl(update, "Cancelado. No se borró nada.")
        context.user_data.clear(); return SEARCH
    target = context.user_data.get("delete_target","")
    short  = "/".join(target.split("/")[-2:])
    try:
        import shutil
        if os.path.isdir(target):
            shutil.rmtree(target)
        else:
            os.remove(target)
        await _rpl(update, f"✅ *Borrado:*\n`{short}`", parse_mode="Markdown")
    except Exception as e:
        await _rpl(update, f"❌ Error al borrar: {e}")
    context.user_data.clear(); return SEARCH



async def cancel(update, context):
    context.user_data.clear()
    await _rpl(update, "Operación cancelada. Manda un título o *menú* cuando quieras.", parse_mode="Markdown")
    return SEARCH

# ── Main ──────────────────────────────────────────────────────────────────────

async def menu_callback(update, context):
    """Handle the Menú inline button — cancel current flow and show menu."""
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    await query.message.reply_text(MENU_TEXT, parse_mode="Markdown", reply_markup=KB_MAIN)
    return MENU


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.job_queue.run_repeating(check_downloads, interval=CHECK_INTERVAL, first=CHECK_INTERVAL)

    MENU_FILTER    = filters.Regex(r"(?i)^(men[uú]|opciones|inicio|ayuda)$") & ~filters.COMMAND
    TRENDING_FILTER = filters.Regex(r"(?i)^(pel[ií]culas?|peliculas?)$") & ~filters.COMMAND

    common_entry = [
        MessageHandler(MENU_FILTER, show_menu),
        MessageHandler(TRENDING_FILTER, _fetch_trending_movies),
        MessageHandler(filters.TEXT & ~filters.COMMAND, search_movie_handler),
    ]

    conv = ConversationHandler(
        entry_points=common_entry,
        states={
            SEARCH:              common_entry,
            MENU:                [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu)],
            TRENDING:            [MessageHandler(filters.TEXT & ~filters.COMMAND, select_trending_series)],
            SELECT_TYPE:         [MessageHandler(filters.TEXT & ~filters.COMMAND, select_type)],
            SELECT_SERIES_PICK:  [MessageHandler(filters.TEXT & ~filters.COMMAND, select_series_pick)],
            SERIES_INFO:         [MessageHandler(filters.TEXT & ~filters.COMMAND, select_series_mode)],
            SELECT_SERIES_MODE:  [MessageHandler(filters.TEXT & ~filters.COMMAND, select_series_mode)],
            SELECT_SERIES_DETAIL:[MessageHandler(filters.TEXT & ~filters.COMMAND, select_series_detail)],
            SELECT_MOVIE:        [MessageHandler(filters.TEXT & ~filters.COMMAND, select_movie)],
            SELECT_TORRENT:      [MessageHandler(filters.TEXT & ~filters.COMMAND, select_torrent)],
            SELECT_MOVIE_FOLDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_movie_folder)],
            WARN_EXISTING:       [MessageHandler(filters.TEXT & ~filters.COMMAND, warn_existing)],
            SELECT_EXISTING_OR_NEW:[MessageHandler(filters.TEXT & ~filters.COMMAND, select_existing_or_new)],
            CANCEL_DOWNLOAD:     [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_cancel)],
            LIBRARY_SEARCH:      [MessageHandler(filters.TEXT & ~filters.COMMAND, library_search)],
            SIMILAR_SEARCH:      [MessageHandler(filters.TEXT & ~filters.COMMAND, similar_search)],
            RECENT_CATEGORY:     [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_recent_category)],
            DELETE_SEARCH:       [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_search)],
            DELETE_SELECT:       [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_select)],
            DELETE_CONFIRM1:     [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_confirm1)],
            DELETE_CONFIRM2:     [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_confirm2)],
            ADD_USER:            [MessageHandler(filters.TEXT & ~filters.COMMAND, add_user)],
            CONFIRM:             [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_download)],
        },
        fallbacks=[CommandHandler("cancel", cancel), CommandHandler("menu", show_menu), CallbackQueryHandler(menu_callback, pattern="^show_menu$")],
        allow_reentry=False,
    )
    app.add_handler(conv)
    logger.info("Bot iniciado.")
    app.run_polling()

if __name__ == "__main__":
    main()
