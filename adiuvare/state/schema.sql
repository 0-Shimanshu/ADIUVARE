create table if not exists audit_events (
    id integer primary key autoincrement,
    identity text not null,
    endpoint text not null,
    score real not null,
    verdict text not null,
    breakdown_json text not null,
    detail_json text not null default '{}',
    created_at text default current_timestamp
);

create index if not exists idx_audit_created_at
    on audit_events (created_at);

create index if not exists idx_audit_identity
    on audit_events (identity, created_at);

create table if not exists identity_state (
    identity text primary key,
    seen integer not null,
    score_ewma real not null,
    blocked_until real not null,
    monitored_remaining integer not null default 0,
    monitored_multiplier real not null default 1.0
);

create table if not exists whitelist_state (
    identity text primary key
);

create table if not exists banned_ip_state (
    ip text primary key
);

create table if not exists config_history (
    id integer primary key autoincrement,
    kind text not null default 'patch',
    patch_json text not null,
    created_at text default current_timestamp
);
