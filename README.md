# Clanker AI for Home Assistant

A generic Home Assistant custom integration for sending automation prompts to the queued Clanker AI Gateway. It supports text chat, camera image analysis with a vision model, and image generation. Actions wait for the queued job to finish and return its job response for use with `response_variable`.

## Install

Copy `custom_components/clanker_ai` into the `custom_components` directory of your Home Assistant configuration, restart Home Assistant, then add **Clanker AI** under **Settings → Devices & services → Add integration**. The default gateway URL is `http://100.112.231.81:4000`.

To change the gateway IP or URL later, open **Settings → Devices & services → Clanker AI → Configure** and update the Gateway URL.

## Chat or analyze an image

```yaml
action: clanker_ai.chat
data:
  config_entry_id: YOUR_CONFIG_ENTRY_ID
  model: qwen3vl-32b-q4km-v8k
  prompt: Describe what is happening. Be concise and mention uncertainty.
  camera_entity_id: camera.front_door
response_variable: ai_result
```

For text only, omit `camera_entity_id`. `system_prompt`, `priority` (0–9), `tags`, and `timeout` (seconds) are optional. The completed job response is available as `ai_result.result`.

## Generate an image

```yaml
action: clanker_ai.generate_image
data:
  config_entry_id: YOUR_CONFIG_ENTRY_ID
  model: flux-schnell-q4ks-img
  prompt: A small robot watering plants in a sunny greenhouse
  width: 512
  height: 512
response_variable: image_result
```

The completed job response is available as `image_result`; its `result` contains the gateway image result. Use its returned image URL in a notification or other action.

## Use the result

```yaml
action: persistent_notification.create
data:
  title: Clanker AI
  message: "{{ ai_result.result.choices[0].message.content }}"
```

The gateway has no API key authentication configured. Keep it on a trusted network or add access control through a trusted HTTPS reverse proxy before exposing it beyond your LAN/VPN.
