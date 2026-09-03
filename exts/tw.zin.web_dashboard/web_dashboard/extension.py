import omni.ext
import omni.kit.app
import threading
import json
import os
import posixpath
import urllib.parse
from http.server import SimpleHTTPRequestHandler
import socketserver

import sys
import zin_core.ui_utils as zin_ui_utils
from zin_core.menu import ZinMenuMixin

# We will import SmartConveyorExtension locally inside the handlers to avoid IExt import warnings.

class DashboardRequestHandler(SimpleHTTPRequestHandler):
    MAX_REQUEST_SIZE = 16 * 1024
    CONTROL_ACTIONS = {"start", "stop", "update_line", "update_all_lines", "load_folder"}

    def _send_json(self, status_code, payload):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode("utf-8"))

    def do_GET(self):
        # Handle API calls
        if self.path == '/api/status':
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
            
            self._send_json(200, status)
            return
            
        # Serve static files from the 'public' folder
        return super().do_GET()

    def do_POST(self):
        if self.path == '/api/control':
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self._send_json(400, {"success": False, "error": "Invalid Content-Length"})
                return
            if not 0 < content_length <= self.MAX_REQUEST_SIZE:
                self._send_json(413, {"success": False, "error": "Request body is too large"})
                return
            try:
                data = json.loads(self.rfile.read(content_length).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._send_json(400, {"success": False, "error": "Invalid JSON payload"})
                return
            if not isinstance(data, dict) or data.get("action") not in self.CONTROL_ACTIONS:
                self._send_json(400, {"success": False, "error": "Unsupported control action"})
                return
            
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
                                    
                        if MAIN_LOOP:
                            asyncio.run_coroutine_threadsafe(run_command(), MAIN_LOOP)
            except ImportError:
                pass
            
            self._send_json(200, {"success": True})
            return

        self._send_json(404, {"success": False, "error": "Not found"})

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

class ZinWebDashboardExtension(ZinMenuMixin, omni.ext.IExt):
    WINDOW_NAME = "Web Dashboard"
    MENU_PATH = f"Zin_All_Tools/{WINDOW_NAME}"

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
            
        self._window = None
        self._build_menu()

    def _start_server(self):
        try:
            socketserver.TCPServer.allow_reuse_address = True
            self._httpd = socketserver.TCPServer(("127.0.0.1", self._port), DashboardRequestHandler)
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
            
        if getattr(self, '_window', None) is not None:
            self._window.destroy()
            self._window = None
        self._remove_menu()

    def _toggle_window(self, menu, value):
        import omni.ui as ui
        if value:
            if getattr(self, '_window', None) is None:
                self._window = ui.Window("Web Dashboard", width=300, height=150)
                with self._window.frame:
                    self.build_ui_layout()
            else:
                self._window.visible = True
        else:
            if getattr(self, '_window', None) is not None:
                self._window.visible = False

    def build_ui_layout(self):
        import omni.ui as ui
        with ui.VStack(style=zin_ui_utils.ZIN_NATIVE_STYLE, spacing=zin_ui_utils.ZIN_V_SPACING, padding=6):
            with ui.CollapsableFrame("Local Server Settings", collapsed=False, height=0):
                with ui.VStack(spacing=zin_ui_utils.ZIN_V_SPACING, padding=6):
                    def build_status():
                        ui.Label("Running", style={"color": 0xFF44AA44, "font_weight": "bold"})
                    zin_ui_utils.build_property_row("Server Status:", build_status)
                    
                    def build_url():
                        ui.Label(f"http://localhost:{self._port}", name="Description")
                    zin_ui_utils.build_property_row("Access URL:", build_url)
                    
            ui.Spacer(height=5)
            ui.Label("WebRTC Livestream is enabled for remote viewing.", name="Description", word_wrap=True)
            ui.Spacer()
