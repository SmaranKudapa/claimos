-- Claim OS shared case record (app claimos-site). Applied with: naive db migrate db/migrations/001_init.sql --app <id>
create table candidates (
  case_id text primary key, county text, tax_year int, parcel_id text, address text, unit text, city text, zip text,
  use text, homestead boolean, just_value numeric, assessed_value numeric, defensible_value numeric,
  annual_savings numeric, neighbor_ratio numeric, sales_ratio numeric, tier text, filing_closes date,
  filing_status text, run_id text, imported_at timestamptz default now(),
  addr_key text  -- upper(regexp_replace(trim(address), '\s+', ' ', 'g')) || '|' || coalesce(zip,'')
);
create index on candidates (addr_key);
create table signups (
  id uuid primary key default gen_random_uuid(), created_at timestamptz default now(),
  address text not null, city text, zip text, email text not null, phone text, call_ok boolean default false,
  consent boolean not null, case_id text references candidates(case_id), verdict text,
  status text default 'new',   -- new | contacted | replied | stopped
  contacted_at timestamptz, notes text
);
create table cases (
  case_id text primary key, address text, county text, owner_email text,
  stage text,  -- find | qualify | signup | evidence | file | waiting | appeal | won | stopped
  status text, county_value numeric, requested_value numeric, annual_savings numeric, filing_deadline date,
  needs_from_owner text, history jsonb default '[]', updated_at timestamptz default now()
);
