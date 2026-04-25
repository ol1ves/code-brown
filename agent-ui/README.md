# agent-ui

Isolated frontend for `/agent/run` SSE stream.

## Env

Create `.env.local`:

```
LIVE_URL=http://localhost:8000
API_KEY=your_backend_key
```

`API_KEY` stays server-side in route handler.

## Run

```
npm install
npm run dev
```
