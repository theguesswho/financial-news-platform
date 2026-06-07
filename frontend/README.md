# Financial News Platform - Frontend

Next.js 14 frontend for the Financial News Platform with TypeScript, Tailwind CSS, and Zustand.

## Quick Start

### Prerequisites
- Node.js 18+
- Backend API running on `http://localhost:8000`

### Installation

```bash
# Dependencies already installed
npm run dev
```

Visit `http://localhost:3000`

## Project Structure

```
frontend/
├── app/                     # Next.js pages
│   ├── login/              # Login
│   ├── register/           # Registration
│   ├── dashboard/          # Dashboard
│   └── page.tsx            # Landing
├── components/
│   ├── common/             # UI components (Button, Input, Card)
│   └── layout/             # MainLayout with navigation
├── lib/
│   ├── api-client.ts       # Axios HTTP client
│   └── auth-store.ts       # Zustand state
├── types/
│   └── api.ts              # Generated types (from backend)
└── .env.local              # Config
```

## Features

✅ User registration & login  
✅ JWT authentication  
✅ Protected routes  
✅ Beautiful UI components  
✅ API client with auto token management  
✅ Global auth state (Zustand)  

## Tech Stack

- Next.js 14 (App Router)
- TypeScript
- Tailwind CSS
- Zustand (state)
- React Hook Form (forms)
- Zod (validation)
- Axios (HTTP)

## Environment

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Troubleshooting

**"Cannot connect to API"**
- Check backend is running: `python3 start_api.py`
- Check `.env.local` has correct API URL

**"Login stuck"**
- Check browser console (F12)
- Verify backend CORS allows localhost:3000

## Next Steps

1. ✅ Week 3: Auth + Landing (DONE)
2. Week 4: Dashboard + Watchlist + Portfolio
3. Week 5: Advanced Screener + Charts

