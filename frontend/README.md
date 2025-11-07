# Mortgage CRM - Frontend

React-based frontend for the Agentic AI Mortgage CRM system.

## Features

- Modern React 18 with Hooks
- React Router for navigation
- Responsive design
- JWT authentication
- Complete CRUD operations for:
  - Leads
  - Loans
  - Tasks
  - Dashboard analytics

## Quick Start

### Prerequisites

- Node.js 16+ and npm
- Backend API running on http://localhost:8000

### Installation

```bash
# Install dependencies
npm install

# Start development server
npm start
```

The app will open at http://localhost:3000

### Build for Production

```bash
npm run build
```

## Project Structure

```
src/
├── components/       # Reusable components
│   └── Navigation.js
├── pages/           # Page components
│   ├── Login.js
│   ├── Dashboard.js
│   ├── Leads.js
│   ├── Loans.js
│   └── Tasks.js
├── services/        # API services
│   └── api.js
├── utils/           # Utility functions
│   └── auth.js
├── App.js           # Main app with routing
└── index.js         # Entry point
```

## Available Scripts

- `npm start` - Run development server
- `npm run build` - Build for production
- `npm test` - Run tests

## Demo Credentials

```
Email: demo@example.com
Password: demo123
```

## API Configuration

The frontend connects to the backend API at:
- Development: http://localhost:8000
- Configure via `REACT_APP_API_URL` environment variable

## Browser Support

- Chrome (latest)
- Firefox (latest)
- Safari (latest)
- Edge (latest)
