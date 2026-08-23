# BB Builders Preconstruction & Bid Management Demo

This repository contains a frontend-only interactive demonstration of the proposed BB Builders bid automation platform.

## Demo workflow

Project Intake → Documents → AI Review → Trade Scopes → Bid Packages → Contractor Discovery → Outreach → Bid Intake → Bid Comparison → Client Proposal → Awarded Project

The primary walkthrough follows project **BB-2026-041 — Retail Store Tenant Improvement**. After starting the application, open the dashboard and use **Demo Guide** for quick navigation through the recommended presentation sequence.

## Technology

- Next.js
- TypeScript
- Tailwind CSS
- shadcn/ui-style component primitives

## Development

```bash
npm install
npm run dev
```

Open `http://localhost:3000`. The root route redirects to the dashboard.

## Validation and production build

```bash
npm run lint
npm run typecheck
npm run build
npm start
```

The project uses standard Next.js conventions and requires no environment variables or custom server configuration for deployment to Vercel.

## Important demo disclosure

All project data, subcontractors, bids, AI findings, communication activity, pricing, and client activity are fictional demonstration data.

No backend, AI service, email system, file processing service, authentication system, persistent storage, or database is connected. Temporary interactions reset when the application reloads.
