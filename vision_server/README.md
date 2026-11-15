# Camera Vision GPU server

This branch contains the API that works with the Home Assistant integration on `main`. It accepts one JPEG, PNG or WebP snapshot and a prompt, and uses Ollama to return a JSON description and list of objects. Images are sent to the local Ollama container; neither service intentionally writes snapshots to disk.

## Run on the GPU server

Install Docker and Docker Compose. The default configuration runs on the CPU and does not expose the GPU to Ollama. Copy this directory to the GPU server. Create a `.env` file containing a long, randomly generated API key:

```dotenv
VISION_API_KEY=replace-with-a-long-random-secret
VISION_MODEL=qwen3-vl:4b-instruct
```

```sh
docker compose up -d --build
docker compose exec ollama ollama pull qwen3-vl:4b-instruct
```

Configure Home Assistant with `http://GPU_SERVER_IP:8000` and the same API key. The API listens on all interfaces; restrict port 8000 to Home Assistant with a firewall. HTTP does not encrypt the key or images: use a trusted network, VPN, or HTTPS reverse proxy. The Ollama port is not published.

Start with the 4B model on CPU and measure latency and RAM use. CPU performance depends on memory bandwidth and image size; inference may be slow. To use the GPU, install NVIDIA Container Toolkit and a compatible driver, then add `-f compose.yaml -f compose.gpu.yaml` to every `docker compose` command. To try the larger `qwen3-vl:32b-instruct`, pull it, set `VISION_MODEL` in `.env`, and run `docker compose up -d`. Its approximately 21 GB model file leaves less GPU memory for context and image processing, so actual GPU fit and speed must be measured. Image quality, distance and night lighting affect accuracy; compare models on your own camera snapshots. This is not continuous video tracking.

## API

`POST /analyze` with header `Authorization: Bearer <key>` and JSON body `{"image": "<base64 image bytes>", "prompt": "Describe the scene"}`. Images are limited to 8 MiB and prompts to 4000 characters. A successful response is:

```json
{"description":"A person stands near the door.","objects":[{"label":"person","description":"Standing near the door."}]}
```

Authentication failures return 401, invalid images 400, invalid request fields 422, and model/backend failures 502. The API does not guarantee factual accuracy. Avoid exposing it directly to the internet.
