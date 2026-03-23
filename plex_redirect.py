#!/usr/bin/env python3
"""
Servidor HTTP que redirige al app de Plex en iOS.
Abre la app con búsqueda del título, y fallback a la web local.
"""

import http.server
import urllib.parse

PLEX_ID    = "f3697c32ed5a7c741b2ad247f99af50b82dc390a"
PLEX_TOKEN = "J56KspJpTsoL6ntyaYrv"
PLEX_LOCAL = "http://192.168.1.10:32400"

HTML = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Abriendo en Plex...</title>
  <script>
    var deepLink = "plex://search?query={title_encoded}";
    var webLink  = "{plex_local}/web/index.html#!/server/{server}/details?key=%2Flibrary%2Fmetadata%2F{rk}&X-Plex-Token={token}";

    // Intenta abrir la app
    window.location = deepLink;

    // Fallback a la web local si no abre en 1.5s
    setTimeout(function() {{
      window.location = webLink;
    }}, 1500);
  </script>
</head>
<body style="font-family:-apple-system,sans-serif;text-align:center;padding-top:80px;background:#1f1f1f;color:#e5a00d">
  <div style="font-size:48px">🎬</div>
  <h2 style="color:#fff">{title}</h2>
  <p style="color:#aaa">Abriendo en Plex...</p>
  <p style="margin-top:30px">
    <a href="{plex_local}/web/index.html#!/server/{server}/details?key=%2Flibrary%2Fmetadata%2F{rk}&X-Plex-Token={token}"
       style="color:#e5a00d;font-size:18px">Ver en Plex →</a>
  </p>
</body>
</html>"""


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        parts  = parsed.path.strip("/").split("/")

        if parts[0] == "plex" and len(parts) >= 3:
            rk    = parts[1]
            title = urllib.parse.unquote_plus(parts[2])
            html  = HTML.format(
                title         = title,
                title_encoded = urllib.parse.quote(title),
                rk            = rk,
                server        = PLEX_ID,
                token         = PLEX_TOKEN,
                plex_local    = PLEX_LOCAL,
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode())
        else:
            self.send_response(404)
            self.end_headers()


if __name__ == "__main__":
    server = http.server.HTTPServer(("0.0.0.0", 7777), Handler)
    print("Plex redirect server running on port 7777")
    server.serve_forever()
