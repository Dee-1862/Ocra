# Design and improvements log, and working abstract

Source: the hackathon notes on the design log and abstract, copied as pasted. Not Mermaid.

**The abstract was cut off in the paste** after "the platform treats p". Marked `[truncated in paste]`; nothing was added. Everything below it is as written.

---

## Design and improvements log

### Issue 1: Tracking occlusion
- **Problem:** pure camera tracking broke when the user made a fist or turned their hand sideways.
- **Fix:** added the FreeWili-OG and IMUs as a fallback. If MediaPipe confidence drops, the IMU rotation data takes over.

### Issue 2: Feedback distraction
- **Problem:** forcing the patient to stare at the laptop screen for stats breaks their physical alignment.
- **Fix:** moved the live feedback (smoothness score, compensation warnings) to the FreeWili-OG screen, acting as a wearable dashboard.

### Issue 3: Objective difficulty scaling
- **Problem:** we need to know whether the game is too hard without pausing to ask the patient.
- **Fix:** rPPG through the webcam tracks heart rate. If physical or cognitive strain spikes, the game engine scales difficulty down automatically.

### Notes added while filing (not from the original text)
- Issue 1: define "confidence drops" as a number and a hold time, otherwise the handoff will flicker. Test 2 in the evaluation plan measures this.
- Issue 3: heart rate is a proxy for strain, not a measurement of it. Heat, caffeine, anxiety and rPPG error all move it. Keep self-reported pain (0 to 10) in the loop and say so in the limitations.
- Issue 2: the OG's panel is an LCD, not OLED.

---

## Working abstract

**Working title:** Low-Cost Multimodal Tracking for Upper-Limb Rehabilitation and Phantom Pain Management

**Author:** Deekshith Reddy Bhoomireddy

**Abstract:**
Serious gaming and extended reality offer proven benefits for physical rehabilitation and phantom limb pain reduction, but clinical systems remain prohibitively expensive and prone to tracking failures. We present a low-cost, multimodal rehabilitation station combining computer vision, remote photoplethysmography (rPPG), and wearable inertial sensors (IMUs). The system supports two user groups: patients with reduced hand mobility and those with upper-limb loss.

By leveraging real-time camera tracking for intact-limb mirroring, the platform treats p... **[truncated in paste]**

### Wording to check before this goes anywhere
- "**Proven** benefits": the evidence in the research notes is mixed. Lendaro et al. found no difference between two XR approaches, and the mirror-vs-VR meta-analysis found no difference between them. Safer: "show promise" or "have reported benefits". Open and read the papers first (their status is still `to read`).
- "**Prone to tracking failures**" is fine as a motivation, but cite the Afyouni limitation (Leap misreading a child's hand).
- "**Treats** phantom pain" claims clinical effect. the paper plan says this is a technical feasibility paper with no patient testing. Prefer "supports" or "delivers phantom-limb exercises".
- The older abstract promised an evaluation on the authors with simulated impairments; this draft does not mention one yet.

## Changelog
| Date | Change |
|---|---|
| 2026-10-03 | Design log and abstract filed from the hackathon notes; abstract truncated in paste. |

## Ideas considered and not pursued

### Replacing the gyroscope with Wi-Fi signals (2026-10-03)
Proposed in a pasted text (unsourced, written by another AI tool): use an accelerometer plus Wi-Fi channel state information (CSI) or signal strength (RSSI / fine timing) to stand in for a missing gyroscope.
Not pursued, because:
- The OG has no Wi-Fi radio. Its antennas belong to two sub-GHz CC1101 radios, which cannot do 802.11 or CSI. The text's "Wi-Fi from a MHz antenna" mixes the two up.
- Reading CSI needs a Wi-Fi chip with special firmware or drivers. A normal laptop does not expose it.
- Wi-Fi timing and signal strength give position to metres, not the centimetres of hand movement.
- Inferring rotation from CSI phase is a research problem, not an established method, and the text cites nothing.
- The need was misdescribed: tilt from an accelerometer does not drift (gravity is a fixed reference). What is missing is a gyroscope for fast motion and yaw.
