# SPARC design notes


Long-form notes behind the [README](../README.md): architecture, the AI pipeline, power, motion, and the engineering decisions.

A solar-powered rover that sees, listens, talks, remembers people and events, and makes its own
decisions. Everything runs on local hardware. No cloud, no internet.

Power comes from a 100 W solar panel and a portable battery. Three computers share the work: two
Raspberry Pis with AI accelerators handle vision and speech, and a laptop runs the large reasoning
model. A separate microcontroller owns the motors, so a software crash can't leave the wheels
running.

## Goals

1. Run untethered on sunlight. A 100 W panel and a 256 Wh battery carry the whole compute and
   drive load.
2. Sense continuously without burning power. Cheap always-on triggers, expensive processors idle
   until something matters.
3. Keep the AI away from anything dangerous. The language model picks from options that ordinary
   code generated and will re-check before acting.
4. Tell the truth. The robot never claims it did something it didn't. That's enforced in code.
5. Move safely around people. Deterministic code produces every number that reaches a motor.

---

## The core idea

Always sensing. Not always thinking. Deterministic code owns reality and the AI advises.

Every sense has a cheap, always-on trigger that gates an expensive, on-demand stage. That one
pattern is what makes continuous operation affordable in power, heat, and compute, and it's what
makes a solar budget realistic.

```
Vision:  on-sensor detector (always on, ~free)  →  AI accelerator (on demand)  →  large vision model
Audio:   voice activity + wake word (always on) →  speech-to-text (on demand)  →  reasoning model
```

Motion runs the same way in reverse. The AI picks what and where. Deterministic code decides how.

---

## System architecture

Three computers, each with one job, talking over a local network.

```mermaid
flowchart LR
    subgraph A["Node A: Vision"]
        A1["Raspberry Pi 5<br/>+ 26 TOPS AI accelerator<br/>+ on-sensor AI camera"]
        A2["World model · scheduler<br/>· safety validator"]
    end
    subgraph B["Node B: Speech & local AI"]
        B1["Raspberry Pi 5<br/>+ generative AI accelerator"]
        B2["Speech-to-text<br/>· fast option selector"]
    end
    subgraph C["Node C: Reasoning"]
        C1["35B 3b MOE ornith 1.5 model,<br/>patiently waiting for the qwen 3.8 35B MOE"]
        C2["Decision generation<br/>· long-term memory"]
    end
    subgraph M["Motion controller"]
        M1["ESP32<br/>PID · encoders · heartbeat · E-stop"]
    end
    A <--> B
    B <--> C
    A <--> C
    B --> M
```

Vision must never wait behind speech, speech must never wait behind reasoning, and the motors
must never wait behind any of them. Each box owns one class of work. The wheels, the one thing
that can hurt someone, sit behind a dedicated microcontroller that keeps running even if every
other computer stops.

### Perception ladder

| Tier | Runs on | Rate | Cost | What it answers |
|---|---|---|---|---|
| 0 | On-sensor camera chip | Always on | ~free | "Something or someone is there" |
| 0.5 | Vision accelerator | 1–2 Hz | ~free | What it looks like, semantically; how unusual it is |
| 1 | Vision accelerator | On demand | ~10–30 ms | Who it is, body position, distance |
| 2 | Laptop model | Event-gated | 1–3 s | Intent, ambiguity, "why" |
| 2′ | On-board AI accelerator | Fallback | 2–3 s | Keeps seeing when the laptop is unreachable |

---

## The AI system: a chain of small models

Local models are improving fast, but none of them can take raw images and sound in one end and
produce trustworthy motor commands out the other. Ask one model to perceive, reason, decide, and
act, and you get confident nonsense at the worst moment.

So the work is split across a chain of models, each with one narrow job. Summarize this frame.
Combine this with memory. Pick one of these three options. Each stage has a small enough job
that it's hard to get wrong, and its output is small enough to check.

Fewer hallucinations, lower latency, and far fewer tokens moving through the system, because each
model only receives what it needs.

### The pipeline

```mermaid
flowchart LR
    CAM["<b>AI camera</b><br/>motion, objects, people"] -->|"triggers"| VLM["<b>Vision model</b><br/>AI accelerator: Qwen 3 VLM"]
    VLM -->|"≤3 sentence<br/>scene summary"| BRAIN["<b>Reasoning model</b><br/>laptop: 35B multimodal"]
    MEM[("<b>Memory</b><br/>faces · events · facts")] --> BRAIN
    BRAIN -->|"scenario +<br/>3 candidate actions"| PERS["<b>Personality model</b><br/>picks one option"]
    PERS -->|"chosen action"| VAL["<b>Validator</b><br/>deterministic re-check against live state"]
    VAL --> OUT["speech · movement"]
```

| Stage | Runs on | Its one job | What it outputs |
|---|---|---|---|
| Detection | On-sensor AI camera | Notice movement, objects, and people | A trigger; no model call unless something happened |
| Scene summary | Vision accelerator (Qwen 3 VLM) | Look at the frame and describe it | 3 sentences, maximum |
| Scenario + options | Laptop (35B multimodal) | Combine the summary with recent memory: what is happening, what in memory relates to it, what could be done | A 1–5 sentence scenario and 3 candidate actions, including speech and movement |
| Choice | Personality model | Pick the option that fits who this robot is | One option, a single token |
| Execution | Deterministic code | Re-check the choice against live state, then act | Motor commands or speech, or a refusal |

The personality model's whole system prompt is the robot's character. It doesn't reason about the
world or invent actions. It only chooses among options that were already generated and will still
be validated afterward. That's what makes personality safe to have. It can change which
reasonable thing happens, never whether something unreasonable does.

### Memory

Two things make the robot feel like it knows you instead of just seeing you.

Face recognition goes through a vector database. Each enrolled face is stored as a vector, and
recognition is a cosine similarity lookup. That's fast enough to run inline and cheap enough to
re-check constantly.

Conversation memory has a sense of time. A model summarizes what happened and files events against
relative time, so the robot's recollection reads the way a person's would: "Nick said hi a few
minutes ago; Nick entered the room right before that." Anchoring events to each other instead of
raw timestamps lets the reasoning model reconstruct a situation from very few tokens.

These were the two hard problems I spent the most time on: long-term memory that stays true, and
responses fast enough to feel like a conversation.

---

## Power system

Two electrically separate power domains that share only a ground reference. Motors create voltage
dips and electrical noise, and a Raspberry Pi that browns out can corrupt its storage. So
traction current never touches the compute supply.

```mermaid
flowchart TD
    SUN["100 W flexible solar panel"] --> JACK["256 Wh portable battery<br/>built-in protection + solar charging"]
    JACK --> PD["USB-C trigger, 20 V"]
    PD --> F1["3 A fuse"] --> R1["5.2 V / 5 A regulator"] --> P1["Pi: vision"]
    PD --> F2["3 A fuse"] --> R2["5.2 V / 5 A regulator"] --> P2["Pi: speech/AI"]
    BAT["Traction battery"] --> FUSE["7.5 A fuse"] --> SW["Main switch"]
    SW --> MON["Current/voltage monitor"] --> D1["Motor driver L"] & D2["Motor driver R"]
    D1 --> ML["Left gearmotor + encoder"]
    D2 --> MR["Right gearmotor + encoder"]
    ES["Emergency stop"] -.->|"cuts driver enable"| D1 & D2
```

Measured and design budget:

| Load | Typical | Peak allowance |
|---|---:|---:|
| Vision node (Pi + accelerator + camera + cooling) | 10–15 W | 25 W |
| Speech/AI node (Pi + accelerator + camera, storage, audio) | 12–18 W | 25 W |
| Conversion losses + motion controller | 3–6 W | 8 W |
| Total | 25–39 W | 58 W |

From roughly 220 Wh usefully delivered, that's about 5.5 to 8.5 hours of continuous operation
with no sun. A 100 W panel realistically delivers 20 to 70 W outdoors. Strong sun covers the
typical compute load and slowly recharges. Poor angle, shade, or heat means the battery still
drains, only more slowly.

Two decisions worth noting. There's no separate solar charge controller. The battery station
already has protection and maximum-power-point charging, and a second controller in front of it
would fight the input and waste power. The panel connects through passive adapters only. And
each Pi gets its own regulator instead of the battery's USB ports. A Pi 5 with accelerators wants
5 V at 5 A, but generic USB-C ports only advertise their headline wattage at higher voltages.
Pulling 20 V once and regulating down per node gives each computer a clean, independently fused
rail, so one node's load can't brown out the other.

---

## Drivetrain and motion control

Slow on purpose and heavily geared: 270:1 gearmotors with quadrature encoders, about 0.084 m/s at
the pack's nominal voltage with 65 mm wheels, about 17,280 encoder counts per wheel revolution.
Slow keeps the control loop stable, keeps the robot safe around people, and leaves the controller
a wide useful duty-cycle range.

Motion has three layers of authority. Each layer can veto the one above it.

| Layer | Runs on | Rate | Owns |
|---|---|---|---|
| L2, Cognitive | Laptop / local AI | ~1 Hz | Symbolic intent: "approach that person", "look there". May be wrong. |
| L1, Primitives | Vision Pi | 50 Hz | Closed-loop state machines, smooth velocity profiles, odometry, obstacle gating, timeouts |
| L0, Reflex/safety | ESP32 | 200+ Hz | PID velocity control, current limits, emergency stop, heartbeat watchdog |

Safety rules, enforced in code:

- Never drive when a person is closer than 0.4 m.
- Maximum 0.35 m/s near people, 0.6 m/s on open floor, always with smooth acceleration ramps.
- Lost heartbeat, stalled sensor, or lost tracking mid-move means stop. Never continue.
- Every motion ends in a reported terminal state, so the reasoning layer learns what actually
  happened instead of assuming success.

The motion stack talks to the wheels through a single `MotorDriver` interface. There's a
simulated implementation behind it as well as the real one, so the whole layer runs on a laptop
with no robot attached. That's how the primitives were developed, and it's what lets the decision
layer be wired into motor commands before anything moves.

---

## What works today

Running continuously on real hardware:

- Spoken conversation: wake-gated listening, speech-to-text, reasoning, spoken reply.
- Person recognition: detection, face embedding, and identity resolution against a vector
  database. Greets people by name and enrolls a new face mid-conversation by voice.
- Long-term memory: semantic memory with duplicate detection, relative-time event ordering, and
  safeguards against the model inventing facts or fabricating their source.
- Truthful self-reporting: the robot can't claim actions it never took. This turned out to be one
  of the hardest and most important problems in the build.
- Supervised, self-healing services: every process restarts automatically and recovers after a
  reboot on all three machines. The robot comes back on its own after a power cut.

### Roadmap

| Milestone | State |
|---|---|
| Supervised, restartable core | ✅ Shipped |
| Visual cognition: real images inform decisions | ✅ Shipped |
| Reliable local spoken conversation | 🚧 Active |
| Robust multi-person visual identity | 🚧 Active |
| Richer perception: attention, proximity, sound events | Planned |
| Deterministic motion foundation: decisions to motor commands | 🚧 In progress |
| Head movement and social orientation | Planned |
| Safe mobile embodiment | Planned |
| Navigation, docking, and sustained autonomy | Future |
| Memory fine-tune: dataset generation and training on a DGX Spark | 🚧 In progress |
| CAD model → URDF → Isaac Sim / Gazebo, fine-tune an open-source VLA (π0 or similar) for movement | 🚧 In progress |

---

## Engineering decisions

The parts I'd most want to talk through in an interview.

MQTT instead of ROS 2. ROS 2 has no supported install on the Pi OS release the AI accelerator
drivers require. So the bus is Mosquitto with typed messages. Every message is a validated schema
object, which means a future migration to ROS 2 touches exactly one module.

Making an unreliable model reliable. Instead of asking the language model to emit structured
commands, ordinary code builds a lettered menu of valid options and the model returns a single
letter, decoded greedily with a one-token limit and clamped in code. The failure surface shrinks
from "parse arbitrary output" to "one character, or fall back." I did this after finding out the
accelerator's serving layer couldn't enforce output schemas at all.

Budgeting prompts like embedded memory. The generative accelerator has a hard 4096-token context
ceiling and delivers roughly 9.5 tokens per second. Every prompt has an enforced token budget, and
over-budget requests are rejected up front instead of overflowing mid-generation.

Separating the motor controller from Linux. A general-purpose OS can't make hard real-time
guarantees, and a robot whose wheels depend on a healthy Python process runs away when that
process hangs. A dedicated microcontroller owns the millisecond-level motor loop and enforces a
command heartbeat. If the computer stops talking, the wheels stop within 250 to 500 ms.

Slow gearing. 270:1 gearmotors cap the rover at roughly 0.084 m/s. That keeps the control loop
stable, makes the robot safe to develop around people, and leaves a wide, useful duty-cycle range
for the controller.

---

## Tech stack

Hardware: Raspberry Pi 5 ×2 · 26 TOPS vision accelerator · generative-AI accelerator ·
on-sensor AI camera · ESP32 · BTS7960 motor drivers · 270:1 encoder gearmotors · INA260 power
monitor · 100 W flexible solar panel · 256 Wh LiFePO4 power station · fused dual-domain wiring ·
latching emergency stop

Software: Python · Pydantic (typed message contracts) · MQTT · SQLite + vector search ·
C/C++ firmware · systemd / launchd supervision

Models: on-sensor object detection · face detection and embedding (vector database with cosine
lookup) · speech-to-text · Qwen 3 vision-language model on the AI accelerator · 35B multimodal
reasoning model running locally on Apple Silicon via MLX · a small personality model for action
selection

---

## Build photos

![100 W flexible solar panel on the 256 Wh power station](media/photos/solar_panel_and_power_station.jpg)

---

## Code in this repository

The full fleet implementation lives in a separate private repository. Public here:

| Path | What it is |
|---|---|
| [`firmware/esp32_motion/`](firmware/esp32_motion/) | ESP32 drive and encoder test firmware: quadrature decoding in an interrupt, BTS7960 PWM control, serial command loop. Boots with motors off. |
| [`hardware_tests/`](hardware_tests/) | Pi bring-up scripts: I2C and GPIO discovery, servo channel finder, ultrasonic range check, manual pan-tilt with soft limits. |
| [`docs/EVAL.md`](docs/EVAL.md) | The eval runs that tuned the reasoning prompt and the long-horizon memory path, with pass rates and latencies. |

### The private repo by the numbers

| | |
|---|---|
| Python, excluding tests | 9,600 lines across four packages (common, node A, node B, node C) |
| Tests | 101 pytest cases, hardware mocked by fixtures, runnable on a laptop |
| Commits | 42 since June 2026 |
| Services | 5 supervised daemons across 2 Raspberry Pis (systemd) and 1 Mac (launchd) |
| Reasoning eval | 8/8 scenarios pass with the final persona, 100% schema-valid output over 28 calls, ~4 s per decision at 3 options |
| Memory eval | 6/6 facts distilled from a 16-event scripted day and recalled correctly the next day through the real retrieval path |
| Locked dependencies | separate pinned lockfiles for each node's OS and Python version |

Source access on request.
