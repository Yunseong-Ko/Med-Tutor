import unittest
from http.server import BaseHTTPRequestHandler
from unittest.mock import patch

from scripts.serve_ontology_graph import Handler, INDEX, public_asset_path


class _BrokenWriter:
    def write(self, _raw):
        raise BrokenPipeError


class OntologyGraphServerTests(unittest.TestCase):
    def test_cancelled_graph_response_is_not_a_server_error(self):
        handler = object.__new__(Handler)
        handler.wfile = _BrokenWriter()

        handler._write_body(b"large graph payload")

    def test_numeric_send_error_log_arguments_are_supported(self):
        handler = object.__new__(Handler)
        with patch.object(BaseHTTPRequestHandler, "log_message") as parent_log:
            handler.log_message("code %d, message %s", 404, "Not Found")

        parent_log.assert_called_once()

    def test_static_server_never_exposes_repository_or_private_data(self):
        self.assertEqual(public_asset_path("/"), INDEX)
        self.assertEqual(
            public_asset_path("/frontend/ontology_graph_live.html"),
            INDEX,
        )
        self.assertIsNone(public_asset_path("/data_private/concept_registry.json"))
        self.assertIsNone(public_asset_path("/schemas/external_kg_review_worklist.schema.json"))
        self.assertIsNone(public_asset_path("/docs/Ontology_Manifest_20260711.json"))
        self.assertIsNone(public_asset_path("/api_server.py"))
        self.assertIsNone(public_asset_path("/frontend/app.js"))
        self.assertIsNone(public_asset_path("/frontend/cpx-osce/past-exam-data.js"))
        self.assertIsNone(public_asset_path("/frontend/styles.css.bak_precpx"))


if __name__ == "__main__":
    unittest.main()
