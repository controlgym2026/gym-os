# Gym OS

Gym member & membership-plan management SaaS with face-biometric attendance
integration. A LivnexaCare venture.

## Stack

| Layer    | Tech                          | Host                         |
|----------|-------------------------------|------------------------------|
| Web      | Next.js 15 (Pages Router, TS) | Vercel                       |
| API      | FastAPI                       | Render                       |
| Database | Supabase Postgres             | Supabase (Seoul / ap-northeast-2) |
| Files    | Cloudflare R2                 | Cloudflare                   |
| Email    | Resend                        | Resend                       |

## Layout

```
gym-os/
├── apps/
│   ├── web/   Next.js frontend
│   └── api/   FastAPI backend
├── render.yaml           (Phase 3)
└── supabase/             (Phase 2)
```

## Local development

### Web (`apps/web`)

```bash
cd apps/web
npm install --legacy-peer-deps
cp .env.example .env.local   # fill in real values
npm run dev                  # http://localhost:3000
```

### API (`apps/api`)

```bash
cd apps/api
python -m venv .venv
source .venv/Scripts/activate   # Git Bash on Windows
pip install -r requirements.txt
cp .env.example .env             # fill in real values
./run.sh                         # http://localhost:8000/health
```

> Run the backend with `python -m uvicorn`, never bare `uvicorn`.
> Use `--legacy-peer-deps` for every npm install (there is an `.npmrc` in
> `apps/web` that enforces this).

## Secrets

Real values live only in `.env` / `.env.local` (git-ignored) or the hosting
provider's dashboard. `.env.example` files list variable names only.
The Supabase `service_role` key belongs to `apps/api` only — never the web app.
