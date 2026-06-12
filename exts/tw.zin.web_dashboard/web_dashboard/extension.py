import omni.ext
import omni.kit.app
import threading
import json
import os
import posixpath
import urllib.parse
from http.server import SimpleHTTPRequestHandler
import socketserver

# We will import SmartConveyorExtension locally inside the handlers to avoid IExt import warnings.

class DashboardRequestHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        # Handle API calls
        if self.path == '/api/status':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            # Add CORS headers
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            # Get data from SmartConveyor
            status = {
                "is_running": False,
                "speed": 15.0,
                "interval": 30.0,
                "uph": 0
            }
            try:
                from smart_conveyor.extension import SmartConveyorExtension
                if hasattr(SmartConveyorExtension, '_primary_instance'):
                    instance = SmartConveyorExtension._primary_instance
                    if instance:
                        status["is_running"] = instance._spawner_sub is not None
                        lines = []
                        if hasattr(instance, '_multi_line_models'):
                            for i, ml in enumerate(instance._multi_line_models):
                                p_cfg = ml.get("config_file")
                                p_paths = ml.get("paths")
                                p = (p_cfg.get_value_as_string() if p_cfg else None) or (p_paths.get_value_as_string() if p_paths else None)
                                if p:
                                    lines.append({
                                        "type": "multi_line",
                                        "index": i,
                                        "path": p,
                                        "speed": ml.get("speed").get_value_as_float() if ml.get("speed") else 15.0,
                                        "interval": ml.get("dispatch_interval").get_value_as_float() if ml.get("dispatch_interval") else 30.0,
                                        "initial_delay": ml.get("initial_delay").get_value_as_float() if ml.get("initial_delay") else 0.0,
                                        "override": ml.get("override").get_value_as_bool() if ml.get("override") else False
                                    })
                        if hasattr(instance, '_scene_overrides_models'):
                            for i, so in enumerate(instance._scene_overrides_models):
                                p = so.get("path")
                                if p: p = p.get_value_as_string()
                                if p:
                                    lines.append({
                                        "type": "scene_override",
                                        "index": i,
                                        "path": p,
                                        "speed": so.get("speed").get_value_as_float() if so.get("speed") else 15.0,
                                        "interval": so.get("dispatch_interval").get_value_as_float() if so.get("dispatch_interval") else 30.0,
                                        "initial_delay": so.get("initial_delay").get_value_as_float() if so.get("initial_delay") else 0.0,
                                        "override": so.get("override").get_value_as_bool() if so.get("override") else False
                                    })
                        status["lines"] = lines
            except Exception as e:
                print(f"[tw.zin.web_dashboard] Error in /api/status: {e}")
                import traceback
                traceback.print_exc()
            
            self.wfile.write(json.dumps(status).encode('utf-8'))
            return
            
        # Serve static files from the 'public' folder
        return super().do_GET()

    def do_POST(self):
        if self.path == '/api/control':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            
            action = data.get("action")
            speed = data.get("speed")
            interval = data.get("interval")
            initial_delay = data.get("initial_delay")
            
            try:
                from smart_conveyor.extension import SmartConveyorExtension
                if hasattr(SmartConveyorExtension, '_primary_instance'):
                    instance = SmartConveyorExtension._primary_instance
                    if instance:
                        import asyncio
                        async def run_command():
                            if action == "start":
                                instance.start_sim()
                            elif action == "stop":
                                instance.stop_sim()
                            elif action == "update_line":
                                line_type = data.get("line_type")
                                line_index = data.get("line_index")
                                if line_type == "multi_line" and hasattr(instance, '_multi_line_models'):
                                    try:
                                        ml = instance._multi_line_models[int(line_index)]
                                        ml["override"].set_value(True)
                                        if speed is not None: ml["speed"].set_value(float(speed))
                                        if interval is not None: ml["dispatch_interval"].set_value(float(interval))
                                        if initial_delay is not None: ml["initial_delay"].set_value(float(initial_delay))
                                    except Exception: pass
                                elif line_type == "scene_override" and hasattr(instance, '_scene_overrides_models'):
                                    try:
                                        so = instance._scene_overrides_models[int(line_index)]
                                        so["override"].set_value(True)
                                        if speed is not None: so["speed"].set_value(float(speed))
                                        if interval is not None: so["dispatch_interval"].set_value(float(interval))
                                        if initial_delay is not None: so["initial_delay"].set_value(float(initial_delay))
                                    except Exception: pass
                                    
                                if instance._spawner_sub is not None:
                                    try: instance.start_sim()
                                    except Exception: pass
                                    
                            elif action == "update_all_lines":
                                speed = data.get("speed")
                                interval = data.get("interval")
                                initial_delay = data.get("initial_delay")
                                
                                if hasattr(instance, '_multi_line_models'):
                                    for ml in instance._multi_line_models:
                                        ml["override"].set_value(True)
                                        if speed is not None: ml["speed"].set_value(float(speed))
                                        if interval is not None: ml["dispatch_interval"].set_value(float(interval))
                                        if initial_delay is not None: ml["initial_delay"].set_value(float(initial_delay))
                                        
                                if hasattr(instance, '_scene_overrides_models'):
                                    for so in instance._scene_overrides_models:
                                        so["override"].set_value(True)
                                        if speed is not None: so["speed"].set_value(float(speed))
                                        if interval is not None: so["dispatch_interval"].set_value(float(interval))
                                        if initial_delay is not None: so["initial_delay"].set_value(float(initial_delay))
                                        
                                if instance._spawner_sub is not None:
                                    try: instance.start_sim()
                                    except Exception: pass
                                    
                            elif action == "load_folder":
                                url = data.get("url", "").strip()
                                if url:
                                    import asyncio
                                    async def do_load():
                                        await instance.load_config_from_url_async(url)
                                    asyncio.ensure_future(do_load())
                                    
                        global MAIN_LOOP
                        if MAIN_LOOP:
                            asyncio.run_coroutine_threadsafe(run_command(), MAIN_LOOP)
            except ImportError:
                pass
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({"success": True}).encode('utf-8'))
            return

    def translate_path(self, path):
        # Override translate_path to point to our 'public' directory
        path = path.split('?',1)[0]
        path = path.split('#',1)[0]
        path = posixpath.normpath(urllib.parse.unquote(path))
        words = path.split('/')
        words = filter(None, words)
        
        # Determine the root path to the public directory
        ext_folder = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(ext_folder, "public")
        for word in words:
            if os.path.dirname(word) or word in (os.curdir, os.pardir):
                continue
            path = os.path.join(path, word)
        return path

    def log_message(self, format, *args):
        # Disable default logging to avoid terminal spam
        pass

MAIN_LOOP = None

class ZinWebDashboardExtension(omni.ext.IExt):
    def on_startup(self, ext_id):
        global MAIN_LOOP
        import asyncio
        try:
            MAIN_LOOP = asyncio.get_event_loop()
        except Exception:
            pass
            
        print("[tw.zin.web_dashboard] Zin Web Dashboard startup")
        self._port = 8013
        self._httpd = None
        self._server_thread = None
        self._start_server()
        
        # Ensure WebRTC streaming is enabled
        manager = omni.kit.app.get_app().get_extension_manager()
        webrtc_ext_name = "omni.kit.livestream.webrtc"
        if not manager.is_extension_enabled(webrtc_ext_name):
            print(f"[tw.zin.web_dashboard] Enabling {webrtc_ext_name}")
            manager.set_extension_enabled_immediate(webrtc_ext_name, True)

    def _start_server(self):
        try:
            socketserver.TCPServer.allow_reuse_address = True
            self._httpd = socketserver.TCPServer(("", self._port), DashboardRequestHandler)
            self._server_thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
            self._server_thread.start()
            print(f"[tw.zin.web_dashboard] Web Server started at http://localhost:{self._port}")
        except Exception as e:
            print(f"[tw.zin.web_dashboard] Failed to start Web Server: {e}")

    def on_shutdown(self):
        print("[tw.zin.web_dashboard] Zin Web Dashboard shutdown")
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()
        if self._server_thread:
            self._server_thread.join(timeout=1.0)
