"""HTTP API for analyzing camera snapshots with a local Ollama model."""
import base64
import binascii
import hmac
import io
import os

import httpx
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field, ValidationError
from PIL import Image, UnidentifiedImageError

API_KEY = os.environ.get("VISION_API_KEY", "")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://ollama:11434").rstrip("/")
MODEL = os.environ.get("VISION_MODEL", "qwen3-vl:4b-instruct")
MAX_IMAGE_BYTES = 8 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 25_000_000
app = FastAPI(title="Camera Vision API")


class AnalyzeRequest(BaseModel):
    image: str = Field(min_length=1, max_length=((MAX_IMAGE_BYTES + 2) // 3) * 4)
    prompt: str = Field(min_length=1, max_length=4000)


class DetectedObject(BaseModel):
    label: str
    description: str


class Analysis(BaseModel):
    description: str
    objects: list[DetectedObject]


def validate_image(encoded: str) -> None:
    try:
        image = base64.b64decode(encoded, validate=True)
        if len(image) > MAX_IMAGE_BYTES:
            raise ValueError("Image is too large")
        with Image.open(io.BytesIO(image)) as opened:
            if opened.format not in {"JPEG", "PNG", "WEBP"}:
                raise ValueError("Unsupported image format")
            opened.verify()
    except (ValueError, binascii.Error, UnidentifiedImageError, OSError, Image.DecompressionBombError) as err:
        raise HTTPException(status_code=400, detail="Invalid or oversized image") from err


@app.post("/analyze", response_model=Analysis)
async def analyze(request: AnalyzeRequest, authorization: str = Header(default="")):
    if not API_KEY or not hmac.compare_digest(authorization, f"Bearer {API_KEY}"):
        raise HTTPException(status_code=401, detail="Unauthorized")
    validate_image(request.image)
    payload = {
        "model": MODEL,
        "stream": False,
        "format": Analysis.model_json_schema(),
        "options": {"temperature": 0},
        "messages": [{"role": "user", "content": (
            "Analyze this camera image. Describe only visible evidence; acknowledge uncertainty. "
            "Return a concise description and a list of visible objects with descriptions. "
            f"User request: {request.prompt}"
        ), "images": [request.image]}],
    }
    try:
        async with httpx.AsyncClient(timeout=570) as client:
            response = await client.post(f"{OLLAMA_URL}/api/chat", json=payload)
            response.raise_for_status()
            return Analysis.model_validate_json(response.json()["message"]["content"])
    except (httpx.HTTPError, KeyError, ValueError, ValidationError) as err:
        raise HTTPException(status_code=502, detail="Vision model request failed") from err
