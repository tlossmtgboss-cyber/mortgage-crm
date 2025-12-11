# Mortgage CRM - Quick Start Guide

## 🚀 Get Running in 5 Minutes

### Prerequisites
- Docker installed
- Python 3.9+ installed
- Node.js 16+ and npm installed

---

## Step 1: Start Database (30 seconds)

```bash
cd mortgage-crm
docker-compose up -d
```

Wait a few seconds for PostgreSQL to start.

---

## Step 2: Start Backend (2 minutes)

Open a new terminal:

```bash
cd mortgage-crm/backend

# Create virtual environment
python -m venv venv

# Activate it
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create environment file
cp .env.example .env

# Start the server
python main.py
```

You should see:
```
✅ Database tables created successfully
✅ Sample data created successfully
✅ CRM is ready!
📚 API Documentation: http://localhost:8000/docs
🔐 Demo Login: admin@perenniaai.com / demo123
```

**Backend is now running at http://localhost:8000**

---

## Step 3: Start Frontend (2 minutes)

Open another new terminal:

```bash
cd mortgage-crm/frontend

# Install dependencies
npm install

# Start development server
npm start
```

Your browser will automatically open to http://localhost:3000

---

## Step 4: Login

Use the demo account:
- **Email:** admin@perenniaai.com
- **Password:** demo123

Click "Use Demo Account" button or enter credentials manually.

---

## 🎉 You're Done!

You should now see the dashboard with:
- Total leads: 3
- Hot leads: Sample data
- Active loans: 2
- Pipeline volume: $950,000

### What to Try:

1. **View Leads** - Click "Leads" in nav bar
2. **Add a Lead** - Click "+ Add Lead" button
3. **View Loans** - Click "Loans" in nav bar
4. **Check Tasks** - Click "Tasks" to see AI task board
5. **API Docs** - Visit http://localhost:8000/docs

---

## 🛑 To Stop Everything

```bash
# Stop frontend (Ctrl+C in frontend terminal)
# Stop backend (Ctrl+C in backend terminal)

# Stop database
docker-compose down
```

---

## 🔧 Troubleshooting

### Port Already in Use

**Backend (8000):**
```bash
lsof -i :8000
kill -9 <PID>
```

**Frontend (3000):**
```bash
lsof -i :3000
kill -9 <PID>
```

### Database Won't Start
```bash
docker-compose down
docker-compose up -d
docker ps  # Should show postgres container running
```

### Module Not Found Error
```bash
# Backend
pip install --upgrade -r requirements.txt

# Frontend
rm -rf node_modules
npm install
```

---

## 📚 Next Steps

- Read [COMPLETE-CRM-SUMMARY.md](../COMPLETE-CRM-SUMMARY.md) for full features
- Check [backend/README.md](backend/README.md) for API details
- Check [frontend/README.md](frontend/README.md) for UI details
- Run tests: `python backend/test_api.py`

---

## ✨ Quick Reference

| What | URL |
|------|-----|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |
| Demo Email | admin@perenniaai.com |
| Demo Password | demo123 |

---

**Happy CRM-ing! 🏡💰**
