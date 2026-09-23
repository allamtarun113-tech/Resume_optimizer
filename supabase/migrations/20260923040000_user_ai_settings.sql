-- Bring-your-own OpenAI key: each user's key (encrypted by the backend) and model choice.

create table public.user_ai_settings (
  user_id uuid primary key references auth.users (id) on delete cascade,
  encrypted_api_key text not null,      -- Fernet ciphertext; the key never leaves the backend
  key_last4 text not null,
  model_small text not null,
  model_large text,                     -- null = use model_small everywhere
  updated_at timestamptz not null default now()
);

-- Backend-only (secret key). RLS on with no policies: the API roles can't read it.
alter table public.user_ai_settings enable row level security;
revoke all on public.user_ai_settings from anon, authenticated;
grant select, insert, update, delete on public.user_ai_settings to service_role;
