import base64
import io
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from fastapi import HTTPException
from PIL import Image

import app


class ImageValidationTest(unittest.TestCase):
    def test_accepts_image_and_rejects_bad_data(self):
        data = io.BytesIO()
        Image.new("RGB", (2, 2)).save(data, format="PNG")
        app.validate_image(base64.b64encode(data.getvalue()).decode())
        with self.assertRaises(HTTPException):
            app.validate_image("not base64!")

    def test_result_schema_requires_description_and_objects(self):
        result = app.Analysis.model_validate({"description": "A door", "objects": []})
        self.assertEqual(result.description, "A door")
        with self.assertRaises(ValueError):
            app.Analysis.model_validate({"description": "A door"})


class EndpointTest(unittest.TestCase):
    def test_auth_and_successful_analysis(self):
        data = io.BytesIO()
        Image.new("RGB", (2, 2)).save(data, format="PNG")
        payload = {"image": base64.b64encode(data.getvalue()).decode(), "prompt": "Describe it"}
        response = unittest.mock.Mock()
        response.json.return_value = {"message": {"content": '{"description":"A door", "objects":[]}'}}
        with patch.object(app, "API_KEY", "secret"), patch.object(app.httpx.AsyncClient, "post", new_callable=AsyncMock, return_value=response):
            with TestClient(app.app) as client:
                self.assertEqual(client.post("/analyze", json=payload).status_code, 401)
                result = client.post("/analyze", json=payload, headers={"Authorization": "Bearer secret"})
                self.assertEqual(result.status_code, 200)
                self.assertEqual(result.json(), {"description": "A door", "objects": []})


if __name__ == "__main__":
    unittest.main()
