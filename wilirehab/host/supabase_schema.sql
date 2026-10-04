-- WiliRehab: one table of finished rounds. Run this once in the Supabase SQL editor.
--
-- Numbers only: no video, no names. `participant` is a pseudonymous code such as P001; keep the
-- list that says who P001 is somewhere else, off this database.
--
-- Security model: the program on the laptop uses the project's ANON key, which is public by
-- design, so it must only be able to ADD rows. Row-level security is switched on and the only
-- policy lets the anon role insert. Nothing can read, change or delete rows with that key.
-- You read the data in the Supabase dashboard (or with the service_role key, kept off the
-- laptop and never committed).

create table if not exists public.rounds (
    id               bigint generated always as identity primary key,
    created_at       timestamptz not null default now(),
    participant      text        not null,
    session_id       text        not null default '',
    game             text        not null,
    seconds          real,
    hits             integer,
    attempts         integer,
    hit_rate         real,
    roll_range_deg   real,
    pitch_range_deg  real,
    peak_dps         real,
    tremor_rms_mg    real,
    pain_events      integer,
    pain_score       integer,
    decision         text,
    decision_reason  text,
    extra            jsonb
);

alter table public.rounds enable row level security;

drop policy if exists "devices can add rounds" on public.rounds;
create policy "devices can add rounds"
    on public.rounds for insert
    to anon
    with check (true);

-- Nothing else is granted: no select, update or delete policy exists for anon.

-- ---------------------------------------------------------------------------------------------
-- One table per agent. The hand agent writes hand_readings, the face agent face_readings (and the
-- orchestrator writes rounds, above). A snapshot is kept every few seconds (WILIREHAB_SAMPLE_S,
-- default 5), not every reading. A few columns are typed for easy querying; `data` holds the
-- whole reading as JSON so nothing is lost. Same security model: the laptop's anon key can only
-- ADD rows. The face table holds numbers derived from the webcam (expression, heart rate), the
-- most sensitive data here: only collect it with the person's informed consent.
-- Safe to run this whole file again: every statement is idempotent.

create table if not exists public.hand_readings (
    id          bigint generated always as identity primary key,
    created_at  timestamptz not null default now(),
    participant text        not null,
    session_id  text        not null default '',
    role        text        not null default '',
    jerk_peak   real,
    rom         real,
    data        jsonb
);

create table if not exists public.face_readings (
    id          bigint generated always as identity primary key,
    created_at  timestamptz not null default now(),
    participant text        not null,
    session_id  text        not null default '',
    pspi_mean   real,
    bpm         real,
    state       text,
    data        jsonb
);

alter table public.hand_readings enable row level security;
alter table public.face_readings enable row level security;

drop policy if exists "devices can add hand readings" on public.hand_readings;
create policy "devices can add hand readings"
    on public.hand_readings for insert to anon with check (true);

drop policy if exists "devices can add face readings" on public.face_readings;
create policy "devices can add face readings"
    on public.face_readings for insert to anon with check (true);

notify pgrst, 'reload schema';
