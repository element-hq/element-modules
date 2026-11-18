"""Serves an Element Web release with its config.json replaced.

    python element_serve.py <webapp dir> <config.json> <port>
"""

import functools
import http.server
import sys

webapp, config_path, port = sys.argv[1], sys.argv[2], int(sys.argv[3])


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.split("?")[0] in ("/config.json", "/config.localhost.json"):
            with open(config_path, "rb") as f:
                body = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            super().do_GET()


http.server.ThreadingHTTPServer(
    ("127.0.0.1", port), functools.partial(Handler, directory=webapp)
).serve_forever()
