import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest import mock

import requests

from core.mcp_server import JarvisMCPServer, make_http_handler


class FakeDispatcher:
    def list_tools(self):
        return [{"name": "status", "inputSchema": {"type": "object"}}]

    def call(self, name, arguments, context=None):
        return {"ok": True, "name": name, "arguments": arguments, "source": context.source}


class MCPServerTests(unittest.TestCase):
    def server(self):
        server = JarvisMCPServer()
        server.dispatcher = FakeDispatcher()
        return server

    def test_initialize_list_and_call_are_json_rpc_compatible(self):
        server = self.server()

        initialized = server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        listed = server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        called = server.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "status", "arguments": {}}})

        self.assertIn("protocolVersion", initialized["result"])
        self.assertEqual(listed["result"]["tools"][0]["name"], "status")
        self.assertFalse(called["result"]["isError"])
        self.assertEqual(called["result"]["structuredContent"]["source"], "mcp")

    def test_http_transport_requires_bearer_token_and_allowed_origin(self):
        service = self.server()
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_http_handler(service, "secret"))
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{httpd.server_address[1]}/mcp"
        payload = {"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {}}
        try:
            unauthorized = requests.post(url, json=payload, timeout=3)
            wrong_origin = requests.post(
                url,
                json=payload,
                headers={"Authorization": "Bearer secret", "Origin": "https://example.com"},
                timeout=3,
            )
            accepted = requests.post(
                url,
                json=payload,
                headers={"Authorization": "Bearer secret", "Origin": "http://localhost"},
                timeout=3,
            )
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=3)

        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(wrong_origin.status_code, 403)
        self.assertEqual(accepted.status_code, 200)
        self.assertTrue(accepted.json()["result"]["ok"])


if __name__ == "__main__":
    unittest.main()
