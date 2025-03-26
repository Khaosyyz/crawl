from http.server import BaseHTTPRequestHandler

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        
        message = {
            "status": "success",
            "message": "Hello World from Vercel Function",
            "path": self.path
        }
        
        import json
        self.wfile.write(json.dumps(message).encode()) 