# MHacks submission: checklist, demo plan, draft answers

Written for: the team lead filling in Devpost and the ASI:One Submission Agent. Drafts only, nothing
here has been submitted. Fill the placeholders yourself.

## 1. What the submission asks for, and where we stand

| Requirement (from the MHacks text) | Status | What is needed |
|---|---|---|
| Devpost submission | not done | Team lead. |
| Register with the **MHacks Submission Agent** on ASI:One (create team, get a Team ID, teammates join) | not done | Team lead, in ASI:One. Needs the URLs below. |
| **Public GitHub repository URL** (required) | **not ready** | `origin` is your fork `Dee-1862/wiliOGbsp`. Check it is public (open it logged out). Clean the repo first, see section 2. Commit the new files (they are untracked). |
| Demo video URL | optional | Plan in section 3. Say "simulated patient". |
| **Agentverse agent profile URLs** (bonus; one per agent built) | partly | The gateway agent is connected by mailbox, so it has a profile. The four chain agents run locally in one program and are NOT on Agentverse, so they cannot be listed unless converted (section 4). |
| **ASI:One shared chat URL** (bonus) | not done | Run the gateway with `ORCA_PUBLIC_ANSWERS=1`, chat with it from Agentverse ("Chat with Agent"), then asi1.ai, search icon, Current chat, Share chat. Use only simulated (DEMO01) data. |

## 2. Before the repository is public

Found in the repo (tracked files):
- `orca/host/sessions/` has about 70 recorded session files (`*.csv`, `*.jsonl`) from your own testing. They were committed before the ignore rule existed, so the rule does not hide them. They are your own sensor numbers, but they include face-derived readings. Decide whether you are happy for them to be public. To stop tracking (files stay on disk): `git rm --cached -r orca/host/sessions orca/host/mag_test.csv`, then commit. They stay in the git HISTORY unless history is rewritten; do not do that without deciding it on purpose.
- `orca/host/devices.json` (your OGs' USB serial numbers) and `orca/host/og_settings.json` are tracked. Low risk; `git rm --cached` them too if you prefer.
- `.env` is correctly ignored and not tracked. Never commit it.
- `orca/host/tests/` is in `.gitignore`, so the tests are not in the repo. Judges cannot run them. Consider deleting that line.
- `orca/host/models/face_landmarker.task` (a MediaPipe model, a few MB) is tracked. Fine, but say where it comes from in the README.
- The `.gitignore` mentions `tools/publish.py`, which does not exist in this repo, so there is no allowlist step: what is committed is what is public.
- The repo is a fork of FreeWili's BSP (`upstream`). Keep their licence and credit them in the README.

## 3. A three-minute demo that shows the agents clearly

Every shot uses the SIMULATED patient (Card 29). Say so on camera.
1. (15 s) The problem: one noisy sensor cannot tell a weak hand from a resting one, and a false alert loses a clinician's trust.
2. (30 s) The kit: two FreeWili OGs worn as controllers, one as the screen, a laptop. Show the screen OG menu.
3. (45 s) The chain on the OG screen: Devices, Filtered, Checked, Decided, Did. Start the simulated patient; point at the dots and the stage colours.
4. (45 s) The Steps page: FILTERED (drops a glitch), CHECKED (four tests with evidence), DECIDED (verdict and the rule), DID (saved, recommendation). Show session 5 (watch: the game is NOT made harder) and session 6 (concerning, verified: eased).
5. (30 s) ASI:One: open the shared chat with the gateway agent; ask "what are the agents doing?" and "why is the verdict that?"; the answer lists the four tests. Show the Agentverse agent profile page.
6. (15 s) Supabase: the three tables, rows for DEMO01. Then the GitHub URL and the line: "research prototype, thresholds not clinically validated".

## 4. Agents count for the bonus

- **Honest and quick:** one Agentverse agent, the gateway ("Orca Insights"). It fronts the four-agent chain and answers questions from the chain's own step log. Give its profile URL.
- **More bonus, more risk:** run Filter, Check, Decide and Act as four separate agents, each with its own mailbox and profile. Their messages would then travel through Agentverse (internet needed, a few seconds of delay, data leaves the laptop), so it is only appropriate with simulated data. It needs code changes and testing, and a live demo that depends on the internet can fail on stage. Only do it if there is time to test it.

## 5. Draft answer: "What problem does your project solve?"

At-home rehabilitation gives clinicians very little to go on. A wearable can count repetitions, but one noisy sensor cannot tell a weak hand from a resting one, and an alert that turns out to be wrong makes people stop trusting the system. Orca uses low-cost FreeWili devices as controllers and as a screen, with a chain of four Fetch.ai agents: Filter, Check, Decide and Act. They drop bad readings, fact-check any imbalance between the hands four ways before calling it real, decide with a stated rule (a half-checked finding can never make the game harder), and act. Every step is visible on the device screen and, through ASI:One, in chat. It is a research prototype with placeholder thresholds, demonstrated here on simulated data, and makes no medical claims.

## 6. Fields to fill in (placeholders)

Project name: ______  Table number (optional): ______  Your name: ______  Your email: ______
Team size (1-4): ______  Public GitHub URL: ______  Demo video URL (optional): ______
Agents built: ______  Agent profile URLs: ______  Shared chats: ______  Shared chat URLs: ______
