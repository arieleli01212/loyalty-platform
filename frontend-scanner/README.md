# Loyalty Scanner — Staff PWA

A mobile-first Progressive Web App for staff to stamp and redeem customer loyalty cards via QR code scanning.

## Setup

```bash
cd frontend-scanner
npm install
```

Copy the environment file and adjust the API URL if needed:

```bash
cp .env.example .env
# Edit VITE_API_BASE if your backend is not on localhost:8000
```

## Development

```bash
npm run dev
```

> **Camera access requires HTTPS or localhost.** When testing on a physical tablet over the local network, either serve over HTTPS or use a tunnelling tool like `ngrok`.

## Production build

```bash
npm run build
npm run preview
```

## Type checking

```bash
npm run typecheck
```

## How to demo

1. Start the backend (`uvicorn app.main:app --reload` from the repo root or via docker-compose).
2. `npm run dev` in this directory (or deploy the `dist/` folder behind HTTPS).
3. Open the URL in a tablet browser; sign in with a staff account.
4. Toggle **Stamp** or **Redeem**, then point the camera at a customer's wallet QR code.

## PWA install

When served over HTTPS the browser will offer an "Add to Home Screen" prompt. Once installed it launches as a standalone app (no browser chrome) — ideal for a counter tablet.
