"""
Flutter Web Server with proper CSP headers for development.
"""
import http.server
import socketserver
import os

PORT = 3010
DIRECTORY = r"c:\amttp\frontend\amttp_app\build\web"

class FlutterHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)
    
    def end_headers(self):
        # CORS headers
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        
        # CSP that allows Flutter web to work (including Google CDN for fonts and CanvasKit)
        # Also allows framing content from localhost for FATF/Next.js integration
        self.send_header('Content-Security-Policy', 
            "default-src 'self' https://*.gstatic.com https://*.googleapis.com http://localhost:*; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://*.gstatic.com http://localhost:*; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com http://localhost:*; "
            "img-src 'self' data: blob: https: http://localhost:*; "
            "font-src 'self' data: https://fonts.gstatic.com; "
            "connect-src 'self' http://localhost:* ws://localhost:* https://*.gstatic.com https://*.googleapis.com; "
            "frame-src 'self' http://localhost:*; "
            "worker-src 'self' blob:;"
        )
        
        # Cache control for development
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        
        super().end_headers()
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

if __name__ == "__main__":
    os.chdir(DIRECTORY)
    
    with socketserver.TCPServer(("", PORT), FlutterHandler) as httpd:
        print(f"=" * 50)
        print(f"  Flutter Web Server")
        print(f"  Serving: {DIRECTORY}")
        print(f"  URL: http://localhost:{PORT}")
        print(f"=" * 50)
        httpd.serve_forever()
