# Deployment Guide - FinanceIQ

This guide covers deploying FinanceIQ to production using modern cloud platforms.

## Quick Start (5 minutes)

### Option 1: Vercel + Railway (Recommended)

Best for: Getting live quickly with minimal setup

#### Step 1: Deploy Frontend to Vercel

1. Go to [vercel.com](https://vercel.com) and sign up (free)
2. Click "New Project"
3. Import your GitHub repository
4. Select `frontend` as the root directory
5. Add environment variable:
   ```
   NEXT_PUBLIC_API_URL=https://your-backend-url.railway.app
   ```
6. Click "Deploy" (takes ~2 minutes)
7. You'll get a live URL like `https://financiq.vercel.app`

**That's it for frontend!** Vercel automatically handles:
- HTTPS/SSL
- Global CDN distribution
- Automatic deployments on git push
- Free tier allows unlimited deployments

#### Step 2: Deploy Backend to Railway

1. Go to [railway.app](https://railway.app) and sign up (free)
2. Click "New Project" → "Deploy from GitHub"
3. Select your repository
4. Railway will detect it's a Python project
5. Add environment variables in Railway dashboard:
   ```
   DB_HOST_IP=postgres
   DB_PASSWORD=secure_password
   DB_USER=postgres
   DB_NAME=financialnewsplatform
   JWT_SECRET_KEY=your-super-secret-key-here
   JWT_EXPIRE_MINUTES=1440
   ```
6. Click "Deploy"
7. Add PostgreSQL plugin:
   - Click "Add" button
   - Search "PostgreSQL"
   - Click "Provision"
   - Railway auto-connects the database
8. Your backend is live at the Railway-generated URL

**Total setup time: ~15 minutes**

---

## Complete Setup with Docker

### Option 2: Docker Locally + Deploy Anywhere

#### Prerequisites
- Docker Desktop installed
- Docker Compose installed

#### Local Testing with Docker

```bash
# From project root
docker-compose up
```

This starts:
- PostgreSQL database (localhost:5432)
- Backend API (localhost:8000)
- Frontend (localhost:3001)

Access at `http://localhost:3001`

#### Deploy Docker Container

**To AWS ECS:**
```bash
# Build image
docker build -f Dockerfile.backend -t financeiq-backend:latest .

# Push to AWS ECR (requires AWS CLI setup)
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin {ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com
docker tag financeiq-backend:latest {ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/financeiq-backend:latest
docker push {ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/financeiq-backend:latest
```

**To DigitalOcean App Platform:**
1. Push code to GitHub
2. Go to DigitalOcean App Platform
3. Select repository
4. DigitalOcean auto-detects Dockerfile
5. Configure environment variables
6. Deploy

---

## Step-by-Step: Vercel + Railway

### Frontend Deployment (Vercel)

**Prerequisites:**
- GitHub account with code pushed
- Vercel account (free)

**Steps:**

1. **Create Vercel Account**
   - Go to vercel.com
   - Click "Sign Up"
   - Choose "GitHub" and authorize
   - Click "Continue"

2. **Import Project**
   - Dashboard → "New Project"
   - Search for your repository
   - Click "Import"

3. **Configure Project**
   - Framework: "Next.js" (auto-detected)
   - Root Directory: "frontend"
   - Build Command: `npm run build`
   - Install Command: `npm ci`
   - Output Directory: `.next`

4. **Add Environment Variables**
   - Click "Environment Variables"
   - Add variable:
     ```
     Name: NEXT_PUBLIC_API_URL
     Value: https://your-railway-backend-url
     ```
   - Leave scope as "Production"

5. **Deploy**
   - Click "Deploy"
   - Wait 2-3 minutes
   - You'll get a live URL: `https://your-project.vercel.app`

6. **Custom Domain (Optional)**
   - Click "Settings" → "Domains"
   - Add your custom domain
   - Update DNS records as shown
   - Wait ~10 minutes for propagation

### Backend Deployment (Railway)

**Prerequisites:**
- GitHub account with code pushed
- Railway account (free with GitHub)

**Steps:**

1. **Create Railway Account**
   - Go to railway.app
   - Click "Login with GitHub"
   - Authorize Railway
   - Accept terms

2. **Deploy Project**
   - Dashboard → "New Project"
   - Select "Deploy from GitHub repo"
   - Search for your repository
   - Click to select
   - Railway detects Python project
   - Click "Deploy Now"

3. **Add Database**
   - In Railway dashboard, click "+ Add"
   - Search "PostgreSQL"
   - Click "PostgreSQL"
   - Click "Provision"
   - Wait ~2 minutes

4. **Configure Environment Variables**
   - Click on backend service
   - Go to "Variables" tab
   - Add variables:
     ```
     DB_HOST_IP=${{ DATABASE_URL_PRIVATE | split_host }}
     DB_PASSWORD=${{ DATABASE_PASSWORD }}
     DB_USER=${{ DATABASE_USER }}
     DB_NAME=${{ DATABASE_NAME }}
     JWT_SECRET_KEY=your-super-secret-key-here
     JWT_EXPIRE_MINUTES=1440
     ```
   - Database variables auto-populate from PostgreSQL plugin

5. **Update Frontend API URL**
   - Go back to Vercel dashboard
   - Project Settings → Environment Variables
   - Update `NEXT_PUBLIC_API_URL` to your Railway backend URL
   - Redeploy (click the most recent deployment → Redeploy)

6. **Verify**
   - Visit your Vercel frontend URL
   - Open DevTools (F12)
   - Try to log in or navigate to screener
   - Check Network tab - requests should go to your Railway backend

---

## Post-Deployment Checklist

- [ ] Frontend loads at Vercel URL
- [ ] Backend health check responds: `https://your-backend/health`
- [ ] Login page works
- [ ] Navigation works
- [ ] API errors show (expected if no data yet)
- [ ] Custom domain configured (if desired)
- [ ] Enable Vercel analytics in Settings
- [ ] Set up Railway error monitoring

---

## Monitoring & Logs

### Vercel Logs
- Dashboard → Your Project → Deployments → Click deployment → "Logs"
- Shows build logs and runtime errors
- Filter by "Production" or "Preview"

### Railway Logs
- Dashboard → Backend Service → "Logs" tab
- Real-time application logs
- Shows startup messages, requests, errors

### Database Access
**Railway:**
```bash
# Railway provides connection string in Variables
# Format: postgresql://user:password@host:port/database
psql postgresql://user:password@host:port/database

# Then run SQL:
SELECT COUNT(*) FROM users;
SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';
```

---

## Troubleshooting

### Issue: "Network Error" on Frontend
**Cause:** Backend URL not set or incorrect
**Fix:** 
- Check Vercel environment variable: `NEXT_PUBLIC_API_URL`
- Verify Railway backend URL is correct and accessible
- Check browser console for full error message

### Issue: 401 Unauthorized
**Cause:** JWT token expired or invalid
**Fix:**
- Clear browser localStorage (DevTools → Application → Clear Storage)
- Log in again
- Check backend logs for JWT errors

### Issue: Database Connection Failed
**Cause:** Connection string incorrect or database down
**Fix:**
```bash
# Test connection locally:
psql postgresql://user:password@host:port/database -c "SELECT NOW();"

# Check Railway database status in dashboard
# Verify DATABASE_URL is set in environment variables
```

### Issue: Build Fails on Vercel
**Cause:** Usually missing dependency or environment variable
**Fix:**
- Check "Logs" in Vercel dashboard
- Look for error message
- Common: Missing `NEXT_PUBLIC_API_URL`
- Redeploy after fixing

---

## Environment Variables Reference

### Frontend (.env.local or Vercel)
```
NEXT_PUBLIC_API_URL=https://your-backend-url
```
**Note:** Must start with `NEXT_PUBLIC_` to be available in browser

### Backend (.env or Railway)
```
DB_HOST_IP=your-database-host
DB_PASSWORD=your-database-password
DB_USER=postgres
DB_NAME=financialnewsplatform
JWT_SECRET_KEY=change-this-to-a-strong-secret
JWT_EXPIRE_MINUTES=1440
FMP_API_KEY=optional-for-data-pipeline
ANTHROPIC_API_KEY=optional-for-ai-features
```

---

## Performance Tips

1. **Enable Caching on Vercel**
   - Settings → Functions → Streaming: OFF (improves cache)
   - ISR (Incremental Static Regeneration) configured

2. **Database Indexing**
   - Add indexes on frequently queried columns
   - Example: `CREATE INDEX idx_users_email ON users(email);`

3. **Monitor Build Size**
   - Vercel dashboard shows bundle size
   - Keep under 500KB for optimal performance

4. **CDN Caching**
   - Vercel Edge Middleware handles caching automatically
   - Static assets cached globally

---

## Security Checklist

- [ ] JWT_SECRET_KEY is strong (>32 characters, random)
- [ ] Database password is strong
- [ ] No secrets in git (use environment variables)
- [ ] HTTPS enforced (automatic on Vercel/Railway)
- [ ] CORS properly configured for your domain
- [ ] Rate limiting enabled (Railway provides this)
- [ ] Database backups enabled (Railway provides automatic backups)

---

## Scaling (When You Need It)

**Vercel:** Automatic scaling - handles traffic spikes
- Pay-as-you-go for high traffic
- No configuration needed

**Railway:** Auto-scaling available
- Pro plan includes auto-scaling
- Set min/max instances in Settings

---

## Support

- **Vercel:** vercel.com/support (excellent docs & support)
- **Railway:** discord.gg/railway (very responsive community)
- **GitHub Issues:** Post questions in your repo

---

**Status:** Ready for Production Deployment  
**Last Updated:** June 7, 2026
