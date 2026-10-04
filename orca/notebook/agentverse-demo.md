# Demo: one-hand game, two-hand game, the agent chain on the OG, and all four agents on Agentverse

Written for: the team presenting at the hackathon. Drafts to follow, nothing here has been run on
real hardware or on Agentverse yet. Everything shown to a camera must use the SIMULATED participant
(DEMO01): in Agentverse mode the agents' messages travel through Agentverse.

## A. One-time setup

1. `.env` (in this host folder) needs, besides the Supabase lines:
   - `ORCA_PARTICIPANT=DEMO01`   `ORCA_SEED=<a long random phrase>`
   - `ORCA_WINDOW_S=4`   (windows of 4 s, so a 40 s round has the 3 windows the checks need)
   - `ORCA_SAMPLE_S=1`   `ORCA_PUBLIC_ANSWERS=1`   (so the agents can answer in ASI:One)
2. Three OGs set up (Card 27): left hand, right hand, screen.
3. Stop `agents_main` and the gateway if they are running (only one program may hold the games' port).
4. `python -m orca.agent_stage` starts all four agents, each with its own Agentverse mailbox.
   The first time, open each of the four `Inspector` links it prints, click **Connect**, then
   **Mailbox**. Do this once; it is remembered. Each agent then appears in your Agentverse with a
   profile page.
5. Paste the README text in section E into each agent's profile (name, handle and README help
   people find it).

## B. Running order (about five minutes)

Terminals: (1) `python -m orca.agent_stage`  (2) `python -m orca.og_shell`.

1. **One-hand game.** On the screen OG open Brick Break (green). The Hand select screen appears:
   pick the right hand (blue), confirm (green). Play about 40 seconds with ONLY the right hand,
   then End (red), End now (green), pain OK.
   Show on the screen OG: Agents, then the chain with dots moving; select Filter and press green:
   it says `only the right hand played: nothing to compare`. Open Check: the verdict is
   `not enough data`. The point: the agents do not call a resting hand a weak hand.
2. **Two-hand game.** Open Rhythm Flick (it uses both hands). Play 40 seconds, using the left hand
   noticeably less. Finish the round the same way.
   Show: Filter's page says `hands compared: 0.xx (left weaker; range ...)`. Check's page lists the
   four tests with their evidence. Decide's page gives the verdict and the rule. Act's page says
   what was saved. Press green on any agent's page for the list of ALL steps.
3. **Simulated patient, for the two verdicts a short game cannot show.** In a third terminal:
   `python -m orca.demo_data`. Show session 5 (`watch`: the game is NOT made harder) and
   session 6 (`concerning (verified)`: eased).

## C. Showing the agents in Agentverse and ASI:One

1. In Agentverse, My Agents: show the four agents (filter, check, decide, act) listed together.
   Open each profile page and copy its URL (they look like
   `https://agentverse.ai/agents/details/agent1q.../profile`): these are the "Agentverse agent
   profile URLs" for the submission form, four of them.
2. Open ASI:One (asi1.ai). Chat with each agent (Agentverse, the agent's page, "Chat with Agent"):
   - Filter: `what have you been doing?`
   - Check: `why is the verdict that?`  (the four tests, with evidence)
   - Decide: `what did you decide?`  (the difficulty and the rule)
   - Act: `what have you saved?`
   Each answers only for its own stage and says whose a question is when it is not its own.
3. Share the chat: asi1.ai, the search icon, Current chat, Share chat, copy the link. That is the
   "ASI:One shared chat URL". You can use one shared chat per agent (four) or one for all.

## D. The marketplace (an honest note)

Nothing in our code puts an agent in the Agentverse Marketplace; that is decided by Agentverse from
the agent's profile and activity. What helps is: each agent connected by mailbox (done in
section A), a clear name and handle, a README (section E), and the chat protocol, which these
agents have. I have not checked the current listing rules, so treat "in the marketplace" as
something to confirm in Agentverse, not as something we have achieved.

## E. README text for each agent's Agentverse profile

### Orca Filter agent
Drops hand and face readings that cannot be real (sensor glitches, no face in view) and says what
it dropped. Every few seconds it summarises what is left: how the two hands compare, and how
uncomfortable the person looks compared with their OWN calm baseline. Part of a chain of four:
Filter, Check, Decide, Act.
Ask me: "what have you been doing?"
Data: numbers only, never video. Demo data is simulated. Research prototype, thresholds are
placeholders and not clinically validated; not medical advice.

### Orca Check agent
When a round ends, tests a possible imbalance between the hands four ways before anyone is told it
is real: enough data, persists across windows, unusual for THIS person, and other signals (face,
pain) agree. Shows the evidence for each test.
Ask me: "why is the verdict that?"
Data: numbers only. Simulated in demos. Not medical advice.

### Orca Decide agent
Gives the verdict and the difficulty recommendation, with the rule behind it. A finding that is
not fully verified can never make the game harder; a verified concern eases it.
Ask me: "what did you decide?"
Data: numbers only. Simulated in demos. Not medical advice.

### Orca Act agent
Saves each round and the clean readings (to a local queue, then to the database) and states the
recommendation. The last step of the chain.
Ask me: "what have you saved?"
Data: numbers only. Simulated in demos. Not medical advice.
