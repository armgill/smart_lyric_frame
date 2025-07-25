from flask import jsonify
# app.py
import os
from flask import Flask, render_template, redirect, request, session
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import lyricsgenius

# load environment variables from .env
load_dotenv()

# flask setup
app = Flask(__name__)
app.secret_key = os.urandom(24)

# spotify credentials
SPOTIPY_CLIENT_ID = os.getenv("SPOTIPY_CLIENT_ID")
SPOTIPY_CLIENT_SECRET = os.getenv("SPOTIPY_CLIENT_SECRET")
SPOTIPY_REDIRECT_URI = os.getenv("SPOTIPY_REDIRECT_URI")

# genius setup
GENIUS_ACCESS_TOKEN = os.getenv("GENIUS_ACCESS_TOKEN")
genius = lyricsgenius.Genius(GENIUS_ACCESS_TOKEN)
genius.skip_non_songs = True
genius.excluded_terms = ["(Remix)", "(Live)"]

# spotify Auth
scope = "user-read-playback-state user-read-currently-playing"
sp_oauth = SpotifyOAuth(
    client_id=SPOTIPY_CLIENT_ID,
    client_secret=SPOTIPY_CLIENT_SECRET,
    redirect_uri=SPOTIPY_REDIRECT_URI,
    scope=scope
)

@app.route('/')
def index():
    if 'token_info' not in session:
        return redirect('/login')

    token_info = session['token_info']
    if sp_oauth.is_token_expired(token_info):
        token_info = sp_oauth.refresh_access_token(token_info['refresh_token'])
        session['token_info'] = token_info

    sp = spotipy.Spotify(auth=token_info['access_token'])

    try:
        current = sp.current_playback()
        if current and current['is_playing']:
            song = current['item']['name']
            artist = current['item']['artists'][0]['name']
            album = current['item']['album']['name']
            album_art = current['item']['album']['images'][0]['url']
            progress_ms = current['progress_ms']
            lyrics_data = load_lrc(song, artist)
            current_lyric = get_current_lyric_line(lyrics_data, progress_ms)
        else:
            song = "Nothing playing"
            artist = ""
            album = ""
            album_art = ""
            current_lyric = ""
    except Exception as e:
        print("Spotify error:", e)
        song, artist, album, album_art, current_lyric = "Error", "", "", "", ""

    # fetch lyrics
    lyrics = ""
    if song and artist and song != "Nothing playing":
        try:
            genius_song = genius.search_song(song, artist)
            if genius_song:
                lyrics = genius_song.lyrics
        except Exception as e:
            print("Genius error:", e)

    return render_template(
        'index.html',
        song=song,
        artist=artist,
        album=album,
        album_art=album_art,
        lyrics=lyrics,
        current_lyric=current_lyric
    )

@app.route('/login')
def login():
    auth_url = sp_oauth.get_authorize_url()
    return redirect(auth_url)

@app.route('/callback')
def callback():
    code = request.args.get('code')
    token_info = sp_oauth.get_access_token(code)
    session['token_info'] = token_info
    return redirect('/')

def load_lrc(song, artist):
    filename = f"lyrics/{song} - {artist}.lrc"
    print("Looking for:", filename)
    if not os.path.exists(filename):
        print("LRC file not found")
        return []

    lyrics = []
    with open(filename, "r", encoding="utf-8") as f:
        for line in f:
            print("LRC Line:", line.strip())  # 🧪 Add this
            line = line.strip()
            if not line.startswith("[") or "]" not in line:
                continue
            try:
                timestamp = line[line.index("[")+1 : line.index("]")]
                if timestamp.replace(":", "").replace(".", "").isdigit() and timestamp.count(":") == 1 and "." in timestamp:
                    time_parts = timestamp.split(":")
                    minutes = int(time_parts[0])
                    seconds = float(time_parts[1])
                    total_seconds = minutes * 60 + seconds
                    text = line[line.index("]")+1:].strip()
                    lyrics.append((total_seconds, text))
            except Exception as e:
                print("Parse error:", e)
                continue
    print("Loaded lines:", lyrics)  # show what's parsed
    return lyrics

@app.route('/current_line')
def current_line():
    if 'token_info' not in session:
        return jsonify({"line": ""})
    sp = spotipy.Spotify(auth=session['token_info']['access_token'])
    current = sp.current_playback()
    if not current or not current.get("is_playing"):
        return jsonify({"line": ""})

    song = current["item"]["name"]
    artist = current["item"]["artists"][0]["name"]
    progress_ms = current["progress_ms"]

    lyrics_data = load_lrc(song, artist)
    prev2, prev1, current_line, next_line = get_current_lyric_lines(lyrics_data, progress_ms)
    return jsonify({
        "line": current_line,
        "prev1": prev1,
        "prev2": prev2,
        "next": next_line
    })

def get_current_lyric_lines(lyrics, progress_ms):
    print("Playback time:", progress_ms)
    prev2 = prev1 = current = next_line = ""
    for i in range(len(lyrics)):
        if progress_ms >= lyrics[i][0] * 1000:
            if i >= 2:
                prev2 = lyrics[i - 2][1]
            if i >= 1:
                prev1 = lyrics[i - 1][1]
            current = lyrics[i][1]
            if i + 1 < len(lyrics):
                next_line = lyrics[i + 1][1]
        else:
            break
    print("Previous 2:", prev2)
    print("Previous 1:", prev1)
    print("Current:", current)
    print("Next:", next_line)
    return prev2, prev1, current, next_line

if __name__ == '__main__':
    app.run(debug=True)