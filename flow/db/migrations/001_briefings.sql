create table if not exists briefings (
  case_id text primary key,
  token text not null unique,
  version int not null,
  has_evidence boolean not null default false,
  deck jsonb not null,
  built_at timestamptz not null default now()
);
