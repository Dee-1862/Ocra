# Using the ESP32-P4-EYE as the face camera: research (2026-10)

Question: can the ESP32-P4-EYE be the camera for the laptop's face numbers (pain expression, heart rate)? Everything here is from documents and repositories read online; **nothing was run on the board.** Confidence is marked on each claim.

## What the board is
- Espressif ESP32-P4-EYE: ESP32-P4, OV2710 2 MP MIPI-CSI camera, 240x240 LCD, microSD, 16 MB flash, two USB-C ports (a USB 2.0 high-speed *device* port and a *debug* port for flashing/serial). [User guide](https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32p4/esp32-p4-eye/user_guide.html) (sure). Windows showed it as COM16, USB 303A:1001 = the debug port (sure, from this machine).
- Espressif's board support package `espressif/esp32_p4_eye` drives the camera through the `esp_video` component (~2.0), needs ESP-IDF 5.4 or newer. [BSP](https://github.com/espressif/esp-bsp/tree/master/bsp/esp32_p4_eye) (sure).

## FreeWili already sells this as the "WILEYE Camera Orca"
- FreeWili's docs describe the WILEYE as an ESP32-P4-EYE with **custom firmware** plus an **adapter** that connects it to a FREE-WILi, a USB-C cable and a microSD card. [WILEYE page](https://docs.freewili.com/extending-with-orcas/wileye-camera-orca/) (from search summaries; the docs site refused my fetch tool, so the detail below is second-hand).
- Firmware: three prebuilt files (`bootloader.bin`, `partition-table.bin`, `wileye_app_demo.bin`, ~6.9 MB) flashed with `esptool` through the debug port. No source and no readme in that repository. [WILEye-Firmware](https://github.com/freewili/WILEye-Firmware) (sure about the files; the flash addresses are not stated there).
- The FreeWili talks to it over a UART, with a command line, a UI and a WebAssembly API. The one command quoted is `t`, which **takes a single picture**, saved to the WILEYE's SD card or streamed to the FreeWili's file system (from a search summary, medium confidence).
- **Consequence:** the official route gives still pictures, not live video. Face tracking and heart rate from video need a steady 15-30 frames a second, so stills do not fit. (My reasoning, not stated in their docs.)
- The red board with the Qwiic logo and a USB-C that fits the OG may be that adapter. **Unconfirmed**: needs its printed name.

## Ways to get live video to the laptop
| Route | What it needs | Evidence | Risk |
|---|---|---|---|
| **UVC webcam firmware** (appears as a normal camera) | ESP-IDF 5.5, `esp32_p4_eye` BSP + `esp_video` for the sensor, `usb_device_uvc` to send MJPEG over the device USB-C port | `usb_device_uvc` supports ESP32-P4 [component](https://components.espressif.com/components/espressif/usb_device_uvc/versions/1.1.2/examples/usb_webcam?language=en). Espressif's own `usb_webcam` example supports only S2/S3 [example](https://github.com/espressif/esp-iot-solution/tree/master/examples/usb/device/usb_webcam). Working P4 webcams exist for other boards: [esp32p4-uvc-video](https://github.com/r4d10n/esp32p4-uvc-video) (OV5647, 1080p30 MJPEG, ESP-IDF 5.5), [cerebro-p4](https://github.com/franciscoaldun/cerebro-p4) (Windows saw it without drivers). | **No ready example for the P4-EYE's OV2710 found.** Someone has to join the BSP camera setup to the UVC driver and test it. Overwrites the factory/WILEYE firmware. |
| **Wi-Fi MJPEG stream** | Same camera setup, plus Wi-Fi (the board's radio is a separate ESP32-C6) and an HTTP server | `esp_video` has a `simple_video_server` example with `/stream` MJPEG, written for ESP32-P4 MIPI-CSI boards [example](https://components.espressif.com/components/espressif/esp_video/versions/1.3.1/examples/simple_video_server?language=en) | Not P4-EYE-specific; Wi-Fi adds delay and drop-outs. Laptop side is easy: OpenCV can open a stream address (needs a small `--face` change). |
| **Official WILEYE firmware** | FreeWili adapter, UART from the OG's main CPU | Docs summary above | Stills only; needs main-CPU firmware that does not exist yet. |
| **Laptop webcam or DroidCam** | Nothing | Works now (camera 0 and 1 on this laptop) | None for the project. |

## Things that could bite later
- **Heart rate (rPPG) wants clean, steady video.** MJPEG compression and uneven frame rates degrade it. Webcams often send MJPEG too, so this is not new, but any embedded camera should be checked against the laptop camera before trusting its numbers. (Reasoning; not tested here.)
- **Throughput:** cerebro-p4 measured memory bandwidth, not the video blocks, as the limit on the P4 (6-16 fps with three neural networks running; plain UVC passthrough is much lighter). [cerebro-p4](https://github.com/franciscoaldun/cerebro-p4)
- **Restoring the factory demo** is possible: Espressif keeps factory binaries in `esp-dev-kits/examples/esp32-p4-eye` (files with a `p4x_` prefix are for the ESP32-P4X board, `p4_` for the original). Check the revision printed on your board first. (From a search summary.)
- The UVC route uses the *device* USB-C port; that is the port the adapter may also use. Unknown until the adapter is identified.

## Recommendation
1. Use the laptop camera or DroidCam for now.
2. If the P4-EYE must be the camera: build the UVC firmware as its own small project, starting from the BSP's `display_camera_csi` example plus `usb_device_uvc`, with the 640x480 MJPEG mode first. Expect days, not hours, and a real chance of dead ends.
3. Add `--face <stream address>` on the laptop side only if the Wi-Fi route is chosen.
