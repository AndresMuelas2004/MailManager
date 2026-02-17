# Frontend (`frontend`)

This is the React + TypeScript frontend for MailManager.
It consumes the FastAPI backend and provides mailbox and inbox UI flows.

## Stack

- React 19
- TypeScript
- Vite
- React Router
- Tailwind CSS (configured in the project)
- ESLint

## Scripts

```bash
npm run dev      # start Vite dev server
npm run build    # type-check and production build
npm run lint     # run ESLint
npm run preview  # preview the production build
```

## Setup

```bash
cd frontend
npm install
npm run dev
```

Default dev URL:

- `http://localhost:5173`

## Backend API Configuration

The frontend HTTP client uses:

- `VITE_API_BASE_URL` when provided
- fallback: `http://localhost:8000`

Example (`.env.local`):

```bash
VITE_API_BASE_URL=http://localhost:8000
```

## Project Structure

```text
src/
|-- api/
|   |-- client/       # request wrapper and API error normalization
|   |-- endpoints/    # endpoint-specific API calls
|   `-- types/        # DTO and validation-related types
|-- app/
|   |-- layout/
|   |-- providers/
|   `-- routes/
|-- components/       # shared UI and common components
|-- features/         # feature modules
|-- pages/            # page-level screens
|-- styles/
`-- main.tsx
```

## Routing

Current routes are defined in `src/app/routes/router.tsx`:

- `/` -> mailbox page
- `/m/:mailboxId/inbox` -> mailbox inbox page

## HTTP Layer

`src/api/client/http.ts` centralizes API requests.

It provides:

- Base URL resolution
- JSON request/response handling
- API error normalization
- Network error fallback messages

## Development Notes

- Run backend (`backend/main.py`) before testing frontend flows.
- CORS in backend allows `http://localhost:5173`.
- Keep DTO changes synchronized with backend schemas.
