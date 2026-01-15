import http.server
import socketserver
import os
from urllib.parse import urlparse

PORT = 3003
DIRECTORY = r"c:\amttp\frontend\amttp_app\build\web"

class SPAHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP request handler for Single Page Applications"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)
    
    def do_GET(self):
        # Parse the URL
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        
        # Check if file exists
        file_path = os.path.join(DIRECTORY, path.lstrip('/'))
        
        # If it's a file that exists, serve it
        if os.path.isfile(file_path):
            return super().do_GET()
        
        # For all other paths (SPA routes), serve index.html
        self.path = '/index.html'
        return super().do_GET()
    
    def end_headers(self):
        # Add CORS headers for local development
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        super().end_headers()

# Start server
with socketserver.TCPServer(("127.0.0.1", PORT), SPAHTTPRequestHandler) as httpd:
    print(f"✅ Flutter app serving at http://127.0.0.1:{PORT}")
    print(f"📂 Directory: {DIRECTORY}")
    print("Press Ctrl+C to stop")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Server stopped")
