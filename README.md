# Camera Vision for Home Assistant

A custom integration that sends a camera snapshot and a prompt to the companion Camera Vision API, then returns a description and detected objects to an automation. The API runs separately on the GPU server; its code and setup instructions are on the `vision-server` branch.

## Install

1. Copy `custom_components/camera_vision` to the same location under your Home Assistant configuration directory and restart Home Assistant.
2. In **Settings → Devices & services → Add integration**, add **Camera Vision**, entering the server URL (for example `http://192.168.1.10:8000`) and its API key.
3. Find the integration's configuration entry ID in Developer Tools → Actions using the configuration selector.

The server should be reachable only on a trusted network. HTTP sends the API key and camera images in clear text; use HTTPS through a trusted reverse proxy or a VPN if the network is not trusted.

## Automation example

Trigger the action from motion detection, a doorbell, a schedule, or manually. Replace the trigger, camera and entry ID for your installation:

```yaml
automation:
  - alias: Describe front door motion
    triggers:
      - trigger: state
        entity_id: binary_sensor.front_door_motion
        to: "on"
    actions:
      - action: camera_vision.analyze
        data:
          config_entry_id: YOUR_CONFIG_ENTRY_ID
          camera_entity_id: camera.front_door
          prompt: Describe any people or packages at the door. Say if the view is unclear.
        response_variable: vision
      - action: persistent_notification.create
        data:
          title: Front door
          message: "{{ vision.description }}"
```

The response contains `description` (string) and `objects` (list of objects with `label` and `description`). Treat model results as fallible: a snapshot can miss movement and models can invent or overlook details. Start with motion-triggered analysis and tune the prompt and camera placement using actual examples.
