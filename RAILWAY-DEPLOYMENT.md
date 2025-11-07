# Railway Deployment Guide

## 🚂 Deploy Your Mortgage CRM to Railway

Your code is already on GitHub, so Railway can deploy directly from there!

---

## Quick Setup (5-10 minutes)

### Step 1: Sign Up for Railway

1. Go to: **https://railway.app**
2. Click **"Login with GitHub"**
3. Authorize Railway to access your repositories

---

### Step 2: Create New Project

1. Click **"New Project"**
2. Select **"Deploy from GitHub repo"**
3. Find and select: **`mortgage-crm`**
4. Railway will scan your repository

---

### Step 3: Add PostgreSQL Database

1. In your project dashboard, click **"+ New"**
2. Select **"Database"** → **"Add PostgreSQL"**
3. Railway automatically creates a database
4. Railway provides a `DATABASE_URL` variable

---

### Step 4: Deploy Backend

1. Click **"+ New"** → **"GitHub Repo"**
2. Select your `mortgage-crm` repository
3. Configure the service:
   - **Root Directory:** `backend`
   - **Start Command:** Auto-detected from Dockerfile

---

### Step 5: Configure Environment Variables

In your backend service, go to **Variables** tab and add:

```
DATABASE_URL = ${{Postgres.DATABASE_URL}}
SECRET_KEY = [Generate a random string - see below]
PORT = 8000
ENVIRONMENT = production
```

**Generate SECRET_KEY:**
Run this in your Terminal:
```bash
openssl rand -hex 32
```
Copy the output and use it as SECRET_KEY.

---

### Step 6: Link Database to Backend

1. In backend service settings
2. Go to **"Variables"** tab
3. Click **"+ Reference"**
4. Select your PostgreSQL database
5. Add variable: `DATABASE_URL = ${{Postgres.DATABASE_URL}}`

---

### Step 7: Deploy!

1. Click **"Deploy"**
2. Wait 2-3 minutes for build
3. Railway will give you a public URL like:
   ```
   https://mortgage-crm-production.up.railway.app
   ```

---

## ✅ Testing Your Deployment

After deployment, test your API:

```
https://your-app.up.railway.app/health
https://your-app.up.railway.app/docs
```

---

## 🎨 Deploy Frontend (Recommended: Use Vercel)

Railway is great for backend, but Vercel is optimized for React:

### Deploy to Vercel (Free)

1. Go to: **https://vercel.com**
2. Click **"New Project"**
3. Import from GitHub: `mortgage-crm`
4. Configure:
   - **Framework Preset:** Create React App
   - **Root Directory:** `frontend`
   - **Build Command:** `npm run build`
   - **Output Directory:** `build`
5. Add Environment Variable:
   ```
   REACT_APP_API_URL = https://your-railway-backend.up.railway.app
   ```
6. Click **"Deploy"**

Your frontend will be live at:
```
https://mortgage-crm.vercel.app
```

---

## 🔧 Post-Deployment Configuration

### Update CORS in Backend

After deploying frontend, update backend CORS settings:

**In `backend/main.py`:**
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://mortgage-crm.vercel.app",  # Your Vercel URL
        "http://localhost:3000"              # Local development
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

Commit and push:
```bash
git add backend/main.py
git commit -m "Update CORS for production"
git push
```

Railway will automatically redeploy.

---

## 💰 Railway Pricing

**Starter Plan (Free):**
- $5 free credit per month
- Enough for small projects
- Database included

**Developer Plan ($20/month):**
- $20 credit included
- Better for production
- Multiple services

---

## 📊 What Gets Deployed

### Backend Service
- FastAPI application
- All API endpoints
- Database connection
- Sample data generation

### Database Service
- PostgreSQL database
- Auto-configured connection
- Persistent storage

---

## 🔍 Monitoring

Railway provides:
- Real-time logs
- Deployment history
- Resource usage metrics
- Automatic HTTPS

---

## 🆘 Troubleshooting

### Build Fails
- Check Dockerfile is in `backend/` directory
- Verify `requirements.txt` is present
- Check Railway logs for specific errors

### Database Connection Error
- Ensure `DATABASE_URL` variable is set
- Verify database service is running
- Check database is linked to backend service

### App Won't Start
- Verify `PORT` environment variable is set to 8000
- Check logs for Python errors
- Ensure all dependencies are in requirements.txt

---

## 🎯 Complete Deployment Checklist

- [ ] Railway account created
- [ ] New project created from GitHub
- [ ] PostgreSQL database added
- [ ] Backend service deployed
- [ ] Environment variables configured
- [ ] Database linked to backend
- [ ] Deployment successful
- [ ] API endpoints working
- [ ] Frontend deployed to Vercel
- [ ] CORS updated for frontend URL
- [ ] Demo account working

---

## 🌐 Your Live URLs

After deployment:

**Backend API:**
```
https://your-app.up.railway.app
```

**API Documentation:**
```
https://your-app.up.railway.app/docs
```

**Frontend (Vercel):**
```
https://mortgage-crm.vercel.app
```

---

## 🚀 Automatic Deployments

Railway automatically deploys when you push to GitHub:

```bash
# Make changes to code
git add .
git commit -m "Update feature"
git push

# Railway automatically deploys the new version
```

---

## 📞 Support

- Railway Docs: https://docs.railway.app
- Railway Discord: https://discord.gg/railway
- Your project: https://railway.app/project/[your-project-id]

---

**Ready to deploy? Start here:** https://railway.app
