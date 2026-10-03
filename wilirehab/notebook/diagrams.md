# V3 diagrams (Mermaid)

Source: the hackathon notes on design evolution, mind map, user flow and architecture. Mermaid renders on GitHub, Obsidian and VS Code's markdown preview; Notability will not render it, so redraw by hand there.

**Three of the pasted texts were cut off.** I marked each cut `[truncated in paste]` and did not guess the ending. Paste the missing text and I will fill it in.

**Conflicts with earlier pages, to settle:**
- This version uses **chest and arm IMUs**; the older hardware list says IMUs are still *to buy* and the v9 design dropped them in favour of webcam-only. V3 effectively reinstates them (Step 5 in Page 10 becomes required, not optional).
- The pages say **OLED screen**. The OG's panel is an ST7789 colour **LCD** (`bsp/display_cpu/lcd/st7789.h`). Use "OG screen" unless you have a different board.
- "Seamlessly" falls back to IMU rotation: IMU rotation alone has no absolute reference and drifts, so the fallback holds for seconds to minutes, not indefinitely. Worth stating in the paper.
- The ">10 degrees" lean threshold and the heart-rate "massive spike" are not yet defined numbers. They need values from evaluation testing.

---

## Design evolution (V1 to V3)

```mermaid
flowchart TD
    V1["V1 Baseline<br/>Webcam-only tracking on a PC<br/>Target: general hand motor impairment"]
    F1["Flaw: tracking drops when the hand turns sideways,<br/>clenches, or is blocked by the other arm.<br/>No support for amputees."]
    V2["V2 Wearable pivot<br/>FreeWili-OG + IMUs on arm and chest<br/>Target: adds amputees"]
    F2["Flaw: fixes occlusion and measures trunk<br/>compensation, but loses visual hand tracking.<br/>No visual mirror, so no phantom limb pain therapy."]
    V3["V3 Sensor fusion, current<br/>Laptop webcam: MediaPipe + rPPG<br/>fused with FreeWili-OG IMUs<br/>Target: limited mobility AND upper-limb loss"]
    FIX["Fix: camera draws the mirrored virtual hand<br/>for phantom pain, while t... [truncated in paste]"]

    V1 --> F1 --> V2 --> F2 --> V3 --> FIX
```

---

## System mind map

```mermaid
mindmap
  root((Multimodal Rehab Station))
    Vision and Vitals Hub - Laptop
      MediaPipe
        Tracks intact hand for mirroring
      rPPG
        Facial blood flow
        Heart rate and stress
    Wearable Kinematics Hub - FreeWili-OG
      Residual IMU
        Tracks arm rotation
      Trunk IMU
        Detects cheating
        Forward leaning
      OG screen
        Live patient biofeedback dashboard
    Game Engine - The Therapy
      Phantom Mirror Mode
        Focus: pain reduction
      Reach and Rotate
        Focus: motor control
      Adaptive Difficulty
        Reacts to fatigue
        Reacts to HR spikes
```

---

## User flow

```mermaid
flowchart TD
    A["1. Setup and baseline<br/>Patient sits at the station"] --> A1["Webcam finds the face:<br/>resting heart rate baseline via rPPG"]
    A --> A2["FreeWili-OG zeroes chest and arm IMUs:<br/>neutral posture"]
    A1 & A2 --> B{"2. Mode select"}
    B -->|"Path A: mobility loss"| PA["Calibrate maximum wrist angle"]
    B -->|"Path B: limb loss"| PB["Set up mirrored hand display<br/>based on which limb is intact"]
    PA & PB --> C["3. Active gameplay<br/>Reach and rotate games.<br/>Phantom therapy: watch the mirrored virtual hand<br/>while moving the intact hand"]
    C --> D{"4. Live corrections"}
    D -->|"Chest IMU: lean over 10 degrees"| D1["Pause game or deduct points"]
    D -->|"Webcam: large heart-rate spike"| D2["Scale difficulty down automatically"]
    D -->|"Otherwise"| C
    D1 & D2 --> C
    C --> E["5. Session review on the OG screen:<br/>range of motion hit, number of trunk leans...<br/>[truncated in paste]"]
```

---

## Architecture flow, inputs to outputs

```mermaid
flowchart LR
    subgraph IN["Inputs"]
        CAM["Webcam video, RGB"]
        OGS["FreeWili-OG sensors"]
    end

    subgraph PROC["Processing logic"]
        MP["MediaPipe<br/>hand landmarks"]
        RP["rPPG<br/>pulse"]
        CH["Chest IMU<br/>pitch and roll"]
        AR["Arm IMU<br/>rotation"]
        FUS["Sensor fusion engine<br/>camera + IMU angles.<br/>If the camera loses the hand,<br/>fall back to IMU rotation"]
        COMP["Compensation filter<br/>chest IMU vs zeroed posture baseline"]
        AUTO["Autonomic monitor<br/>rolling average heart rate,<br/>flags sudden stress or pain spikes"]
    end

    subgraph OUT["Outputs"]
        UI["Main UI<br/>game graphics + mirrored virtual hand"]
        HW["Hardware UI<br/>live stats on the OG screen"]
        LOG["Data log<br/>structured CSV for the therapist"]
    end

    CAM --> MP
    CAM --> RP
    OGS --> CH
    OGS --> AR
    MP --> FUS
    AR --> FUS
    CH --> COMP
    RP --> AUTO
    FUS --> UI
    COMP --> UI
    COMP --> HW
    AUTO --> UI
    FUS --> LOG
    COMP --> LOG
    AUTO --> LOG
    UI --> HW
```

The edge `UI --> HW` and the exact wiring of what feeds the OG screen are my reading of "pushes live stats back"; check them against your intent.

---

# Earlier version (v9, webcam-only), kept for history

Diagrams carried over from the old notebook pages before they were removed. They describe the superseded webcam-only design; the V3 diagrams above replace them.

## v9 mind map

```mermaid
mindmap
  root((WiliRehab))
    Users
      Reduced hand and wrist movement
        Stroke
        Cerebral palsy
        Trauma
        Arthritis
      Upper limb loss
        Phantom limb pain
        Trunk and shoulder compensation
        Balance asymmetry
        Prosthesis training motivation
    Sensing
      Laptop webcam
        MediaPipe Hands
        MediaPipe Pose
        Face Mesh
          rPPG heart rate
          Facial strain
          Blink fatigue
      FREE-WILi OG
        Feedback screen
        Buttons and pain check-in
        Maestro Qwiic port
          BNO085 IMUs
      Kit ESP32 table station
        Knob
        FSR squeeze ball
        Buttons
        LED strip targets
        Ultrasonic
      Raspberry Pi
        Wobble board balance
      Laptop mic
        Voice commands
    Games
      Wrist path
      Knob turn
      Squeeze meter
      Light chase
      Reach with still trunk
      Mirror hand
      Residual forearm rotation
      Balance hold
    Adaptation
      Range of motion
      Smoothness SPARC
      Compensation
      Fatigue
      Heart rate
      Strain and self report
    Evidence
      Afyouni 2017
      Phantom pain XR trials
      Mirror vs VR meta analysis
      Compensation studies
      Prosthesis abandonment
      MediaPipe validity
      IMU validity
      rPPG toolbox and bias
      UNBC McMaster
    Output
      Therapist dashboard
      Session report
      Paper
        Demo or poster paper
        Zenodo record
        arXiv preprint
```

## v9 patient session

```mermaid
flowchart TD
    A[Patient sits at table, laptop in front, OG beside it] --> B[Choose mode on OG buttons: Hand mode or Limb-loss mode]
    B --> C[Calibration about 1 minute]
    C --> C1[Move wrist through comfortable range]
    C --> C2[Squeeze ball once at max]
    C --> C3[Reach to farthest LED]
    C --> C4[Resting heart rate from webcam]
    C1 & C2 & C3 & C4 --> D[Personal profile shown on OG screen]
    D --> E[Play game round]
    E --> F{During round}
    F -->|Compensation detected| G[Pause scoring, buzz, show cue on OG]
    F -->|Camera loses hand| H[IMU keeps the angle, indicator shows IMU only]
    F -->|Heart rate high or strain on face| I[Ease targets, offer break]
    F -->|Calm and accurate| J[Push targets slightly further]
    G & H & I & J --> E
    E --> K[End of round: 0 to 10 pain check-in on OG buttons]
    K --> L{More rounds?}
    L -->|Yes| E
    L -->|No| M[Session summary on OG screen]
    M --> N[Data saved as numbers only, no video]
```

## v9 therapist flow

```mermaid
flowchart TD
    T1[Open dashboard on laptop] --> T2[Pick patient profile]
    T2 --> T3[Set goals: target angles, games, session length]
    T3 --> T4[Patient plays at clinic or home]
    T4 --> T5[Review trends: ROM, smoothness, compensation count, heart rate, pain reports]
    T5 --> T6[Adjust goals]
    T6 --> T4
    T5 --> T7[Export PDF or CSV]
```

## v9 architecture flow

```mermaid
flowchart LR
    subgraph Inputs
        W[Laptop webcam]
        MIC[Laptop mic]
        IMU[BNO085 IMUs on hand and forearm]
        OGB[OG buttons]
        ESP[Kit ESP32 table station: knob, FSR, buttons, ultrasonic]
        PI[Pi + IMU on wobble board]
    end

    subgraph Transport
        USB[USB serial from OG]
        WIFI[Wi-Fi WebSocket or MQTT]
    end

    subgraph Laptop processing
        MP[MediaPipe Hands, Pose, Face Mesh]
        RPPG[rPPG: POS or CHROM via rPPG-Toolbox]
        STRAIN[Facial strain score from action units]
        VOICE[Voice command recognizer]
        HUB[Timestamped data hub]
        FUSE[Fusion: camera + IMU wrist angle, trunk lean]
        MET[Metrics: ROM, SPARC, tremor, compensation, fatigue]
        ADAPT[Adaptation engine]
        GAME[Game engine]
        LOG[Session log, numbers only]
    end

    subgraph Outputs
        SCREEN[Laptop game screen]
        OGS[OG feedback screen and buzzer]
        LED[LED strip targets]
        DASH[Therapist dashboard and export]
    end

    W --> MP
    W --> RPPG
    MP --> STRAIN
    MIC --> VOICE
    IMU --> USB
    OGB --> USB
    ESP --> WIFI
    PI --> WIFI
    USB --> HUB
    WIFI --> HUB
    MP --> HUB
    RPPG --> HUB
    STRAIN --> HUB
    VOICE --> HUB
    HUB --> FUSE --> MET --> ADAPT --> GAME
    HUB --> ADAPT
    GAME --> SCREEN
    GAME --> OGS
    GAME --> LED
    GAME --> LOG --> DASH
```
