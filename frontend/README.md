# Holos Frontend

Next.js frontend for the Holos AI Fitness Application.

## Setup

### Prerequisites

- Node.js 18+
- npm or yarn

### Installation

1. Install dependencies:
```bash
npm install
```

2. Set up environment variables:
```bash
cp .env.example .env.local
# Edit .env.local with your API URL (default: http://localhost:8000)
```

3. Run the development server:
```bash
npm run dev
```

The app will be available at `http://localhost:3000`

## Project Structure

```
frontend/
├── app/              # Next.js App Router pages
├── components/       # React components
├── lib/              # Utilities (API client, etc.)
└── public/           # Static assets
```

## Environment Variables

Create a `.env.local` file in the `frontend/` directory:

- `NEXT_PUBLIC_API_URL`: Backend API URL (default: `http://localhost:8000`)

**Note**: Environment variables prefixed with `NEXT_PUBLIC_` are exposed to the browser.

## Pages

- `/` - Home page with login/register links
- `/login` - User login page
- `/register` - User registration page
- `/onboarding` - Medical history and preferences setup (first-time users)
- `/dashboard` - Main chat interface with Physical Fitness Agent
- `/medical` - View and edit medical history
- `/preferences` - View and edit user preferences

## Components

- `MedicalHistoryForm` - Reusable form for medical history input
- `ButtonSelector` - Multi-select button component for goals/exercise types
- `MedicalWarning` - Component for displaying medical conflict warnings

## Features

- JWT token-based authentication
- Conversation persistence (messages saved to database)
- Medical conflict detection warnings
- Workout log viewing
- Responsive design with modern UI/UX

