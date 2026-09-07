"""Loopback-only WordPress protocol peer for regression and interactive smoke.

This is a controlled HTTP peer, not WordPress and not proof of a production account.
"""
import argparse
import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


def make_server(port=0):
    state = {"posts": [], "reads": [], "mode": "normal", "body": "原有服务页面正文。", "title": "服务介绍", "link_path": "/service"}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, payload, status=200, content_type="application/json"):
            data = json.dumps(payload, ensure_ascii=False).encode() if isinstance(payload, (dict, list)) else payload.encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def document(self):
            body = state["body"]
            if state["mode"] == "hidden":
                body = '<main>仍然是旧正文</main><div hidden>' + body + '</div>'
            elif state["mode"] == "script":
                body = '<main>仍然是旧正文</main><script>' + body + '</script>'
            return '<!doctype html><html><head><title>' + state["title"] + '</title><meta name="description" content="受控协议验证官网"><link rel="canonical" href="' + base() + '/service"></head><body><h1>' + state["title"] + '</h1><article>' + body + '</article></body></html>'

        def resource(self):
            return {"id": 17, "link": base() + state["link_path"], "status": "publish", "title": {"rendered": state["title"]}, "content": {"rendered": state["body"]}}

        def do_GET(self):
            state["reads"].append(self.path)
            if self.path == "/__state":
                self.send(state)
            elif self.path == "/wp-json/wp/v2/pages/17":
                self.send(self.resource())
            elif self.path == "/robots.txt":
                self.send("User-agent: OAI-SearchBot\nAllow: /\nUser-agent: GPTBot\nDisallow: /\nUser-agent: Googlebot\nAllow: /\n", content_type="text/plain")
            elif self.path in {"/service", "/other", "/"}:
                self.send(self.document(), content_type="text/html")
            else:
                self.send({"code": "not_found"}, 404)

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            if self.path == "/__control":
                for key in ("mode", "body", "title", "link_path"):
                    if key in body:
                        state[key] = body[key]
                self.send({"ok": True})
            elif self.path == "/wp-json/wp/v2/pages/17":
                if state["mode"] == "auth_error":
                    self.send({"code": "rest_cannot_edit"}, 401)
                    return
                state["posts"].append(body)
                state["body"], state["title"] = body["content"], body["title"]
                if state["mode"] == "unknown":
                    self.send({"code": "response_lost_after_write"}, 503)
                else:
                    self.send(self.resource())
            else:
                self.send({"code": "not_found"}, 404)

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    def base():
        return f"http://127.0.0.1:{server.server_port}"
    return server, state


@contextmanager
def controlled_peer():
    server, state = make_server()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", state
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=18765)
    args = parser.parse_args()
    server, _ = make_server(args.port)
    print(f"Controlled WordPress protocol peer ready http://127.0.0.1:{server.server_port}; existing page17 /service", flush=True)
    server.serve_forever()
