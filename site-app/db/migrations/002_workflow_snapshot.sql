create table if not exists workflow_snapshots (
  id text primary key,
  payload jsonb not null,
  observed_at timestamptz not null
);
alter table workflow_snapshots enable row level security;
