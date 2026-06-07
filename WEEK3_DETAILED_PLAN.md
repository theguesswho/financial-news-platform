# Week 3 Detailed Plan - Frontend Foundation & Auth

**Goal:** Build reusable components and functional auth system  
**Hours:** 16 hours (3-4 hours/day, 5 days)  
**Deliverable:** Login/register pages working, component library complete

---

## Day 1: Setup & Component Architecture (3 hours)

### Morning Session: Project Setup (1.5 hours)

**Task 1.1: Create Next.js Project with Optimizations (30 min)**
```bash
# Start fresh Next.js with App Router + TypeScript
npx create-next-app@latest financial-news-platform-frontend \
  --typescript \
  --app \
  --tailwind \
  --eslint

cd financial-news-platform-frontend

# Install core libraries
npm install @tanstack/react-query axios zustand @hookform/resolvers react-hook-form zod
npm install -D @types/node @types/react vitest @testing-library/react
```

**Deliverable:**
- ✓ Next.js 14 app running on localhost:3000
- ✓ Tailwind CSS configured
- ✓ TypeScript strict mode enabled
- ✓ All libraries installed

**Verification:**
```bash
npm run dev
# Should see "Next.js ready" on localhost:3000
```

**Task 1.2: Project Structure Setup (30 min)**
```
src/
├── app/
│   ├── layout.tsx           (Main layout)
│   ├── page.tsx             (Landing page)
│   ├── login/
│   │   └── page.tsx         (Login page)
│   ├── register/
│   │   └── page.tsx         (Register page)
│   └── dashboard/
│       └── page.tsx         (Dashboard placeholder)
├── components/
│   ├── common/              (Reusable UI)
│   ├── domain/              (Business logic)
│   └── layout/              (Page layouts)
├── lib/
│   ├── api-client.ts        (HTTP client)
│   ├── auth-context.ts      (Auth state)
│   └── hooks.ts             (Custom hooks)
├── types/
│   └── api.ts               (Generated from OpenAPI)
├── hooks/
│   ├── useAuth.ts           (Auth hook)
│   ├── useWatchlist.ts      (Watchlist hook)
│   └── useStocks.ts         (Stock data hook)
└── styles/
    └── globals.css          (Global styles)

// Create all directories
mkdir -p src/{app/{login,register,dashboard},components/{common,domain,layout},lib,types,hooks,styles}
```

**Task 1.3: Generate TypeScript Types from API (30 min)**
```bash
# Install OpenAPI generator
npm install -D openapi-typescript

# Generate types (point to your local API)
npx openapi-typescript http://localhost:8000/openapi.json -o src/types/api.ts

# Add to package.json scripts
# "gen:types": "openapi-typescript http://localhost:8000/openapi.json -o src/types/api.ts"
```

**Deliverable:**
- ✓ `src/types/api.ts` with 50+ auto-generated types
- ✓ Full TypeScript intellisense for API responses

### Afternoon Session: Component Architecture (1.5 hours)

**Task 1.4: Create Base Components (Buttons, Inputs, Cards) (1.5 hours)**

Create `src/components/common/Button.tsx`:
```typescript
import React from 'react';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'danger' | 'outline';
  size?: 'sm' | 'md' | 'lg';
  loading?: boolean;
  fullWidth?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ 
    variant = 'primary', 
    size = 'md', 
    loading = false,
    fullWidth = false,
    disabled,
    className = '',
    children,
    ...props 
  }, ref) => {
    const baseClasses = 'font-medium rounded-lg transition-colors duration-200 flex items-center justify-center gap-2';
    
    const variants = {
      primary: 'bg-blue-600 text-white hover:bg-blue-700 disabled:bg-blue-400',
      secondary: 'bg-gray-200 text-gray-900 hover:bg-gray-300 disabled:bg-gray-100',
      danger: 'bg-red-600 text-white hover:bg-red-700 disabled:bg-red-400',
      outline: 'border-2 border-gray-300 text-gray-900 hover:bg-gray-50 disabled:opacity-50',
    };
    
    const sizes = {
      sm: 'px-3 py-1.5 text-sm',
      md: 'px-4 py-2 text-base',
      lg: 'px-6 py-3 text-lg',
    };
    
    const width = fullWidth ? 'w-full' : '';
    
    return (
      <button
        ref={ref}
        className={`${baseClasses} ${variants[variant]} ${sizes[size]} ${width} ${loading ? 'opacity-50' : ''} ${className}`}
        disabled={disabled || loading}
        {...props}
      >
        {loading && <span className="animate-spin">⏳</span>}
        {children}
      </button>
    );
  }
);

Button.displayName = 'Button';
```

Create `src/components/common/Input.tsx`:
```typescript
import React from 'react';

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  helpText?: string;
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, helpText, className = '', ...props }, ref) => {
    return (
      <div className="w-full">
        {label && (
          <label className="block text-sm font-medium text-gray-700 mb-1">
            {label}
          </label>
        )}
        <input
          ref={ref}
          className={`w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 ${
            error ? 'border-red-500' : 'border-gray-300'
          } ${className}`}
          {...props}
        />
        {error && <p className="text-red-500 text-sm mt-1">{error}</p>}
        {helpText && !error && <p className="text-gray-500 text-sm mt-1">{helpText}</p>}
      </div>
    );
  }
);

Input.displayName = 'Input';
```

Create `src/components/common/Card.tsx`:
```typescript
import React from 'react';

interface CardProps {
  children: React.ReactNode;
  className?: string;
}

export function Card({ children, className = '' }: CardProps) {
  return (
    <div className={`bg-white rounded-lg shadow-md p-6 ${className}`}>
      {children}
    </div>
  );
}
```

**Deliverable:**
- ✓ 3 base components created and tested
- ✓ All components have proper TypeScript types
- ✓ Tailwind styling configured

**Verification:**
```typescript
// Test components render
import { Button } from '@/components/common/Button';

export default function Home() {
  return (
    <Button variant="primary" size="md">Click Me</Button>
  );
}
```

---

## Day 2: API Client & Auth Context (3 hours)

### Morning Session: API Client (1.5 hours)

**Task 2.1: Implement API Client with axios (1.5 hours)**

Create `src/lib/api-client.ts`:
```typescript
import axios, { AxiosInstance } from 'axios';
import { paths } from '@/types/api';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

class APIClient {
  private client: AxiosInstance;
  private token: string | null = null;

  constructor() {
    this.client = axios.create({
      baseURL: API_URL,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    // Load token from localStorage
    if (typeof window !== 'undefined') {
      this.token = localStorage.getItem('access_token');
      if (this.token) {
        this.setAuthHeader();
      }
    }

    // Response interceptor for 401 handling
    this.client.interceptors.response.use(
      (response) => response,
      (error) => {
        if (error.response?.status === 401) {
          localStorage.removeItem('access_token');
          window.location.href = '/login';
        }
        return Promise.reject(error);
      }
    );
  }

  private setAuthHeader() {
    if (this.token) {
      this.client.defaults.headers.common['Authorization'] = `Bearer ${this.token}`;
    }
  }

  setToken(token: string) {
    this.token = token;
    localStorage.setItem('access_token', token);
    this.setAuthHeader();
  }

  clearToken() {
    this.token = null;
    localStorage.removeItem('access_token');
    delete this.client.defaults.headers.common['Authorization'];
  }

  // Auth endpoints
  async register(data: {
    email: string;
    password: string;
    name: string;
  }) {
    const response = await this.client.post('/api/auth/register', data);
    return response.data;
  }

  async login(email: string, password: string) {
    const response = await this.client.post('/api/auth/login', {
      email,
      password,
    });
    return response.data;
  }

  async getCurrentUser() {
    const response = await this.client.get('/api/auth/me');
    return response.data;
  }

  // Stock endpoints
  async getStocks(filters?: any) {
    const params = new URLSearchParams(filters || {});
    const response = await this.client.get(`/api/stocks/screener?${params}`);
    return response.data;
  }

  async getStockDetail(symbol: string) {
    const response = await this.client.get(`/api/stocks/${symbol}`);
    return response.data;
  }

  // Watchlist endpoints
  async getWatchlist() {
    const response = await this.client.get('/api/watchlist');
    return response.data;
  }

  async addToWatchlist(data: any) {
    const response = await this.client.post('/api/watchlist', data);
    return response.data;
  }

  async removeFromWatchlist(symbol: string) {
    await this.client.delete(`/api/watchlist/${symbol}`);
  }

  // Portfolio endpoints
  async getPortfolio() {
    const response = await this.client.get('/api/portfolio');
    return response.data;
  }

  async addHolding(data: any) {
    const response = await this.client.post('/api/portfolio', data);
    return response.data;
  }

  async removeHolding(symbol: string) {
    await this.client.delete(`/api/portfolio/${symbol}`);
  }
}

export const apiClient = new APIClient();
```

**Deliverable:**
- ✓ API client with token management
- ✓ Auto-logout on 401
- ✓ All endpoints callable

### Afternoon Session: Auth State Management (1.5 hours)

**Task 2.2: Create Zustand Auth Store (1.5 hours)**

Create `src/lib/auth-store.ts`:
```typescript
import { create } from 'zustand';
import { apiClient } from './api-client';

interface User {
  id: number;
  email: string;
  name: string;
  created_at: string;
  is_active: boolean;
}

interface AuthStore {
  user: User | null;
  token: string | null;
  isLoading: boolean;
  error: string | null;
  register: (email: string, password: string, name: string) => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  checkAuth: () => Promise<void>;
  clearError: () => void;
}

export const useAuthStore = create<AuthStore>((set) => ({
  user: null,
  token: null,
  isLoading: false,
  error: null,

  register: async (email, password, name) => {
    set({ isLoading: true, error: null });
    try {
      const response = await apiClient.register({ email, password, name });
      apiClient.setToken(response.access_token);
      set({
        user: response.user,
        token: response.access_token,
        isLoading: false,
      });
    } catch (error: any) {
      set({
        error: error.response?.data?.detail || 'Registration failed',
        isLoading: false,
      });
      throw error;
    }
  },

  login: async (email, password) => {
    set({ isLoading: true, error: null });
    try {
      const response = await apiClient.login(email, password);
      apiClient.setToken(response.access_token);
      set({
        user: response.user,
        token: response.access_token,
        isLoading: false,
      });
    } catch (error: any) {
      set({
        error: error.response?.data?.detail || 'Login failed',
        isLoading: false,
      });
      throw error;
    }
  },

  logout: () => {
    apiClient.clearToken();
    set({ user: null, token: null });
  },

  checkAuth: async () => {
    const token = localStorage.getItem('access_token');
    if (!token) {
      set({ user: null, token: null });
      return;
    }

    try {
      set({ isLoading: true });
      apiClient.setToken(token);
      const user = await apiClient.getCurrentUser();
      set({ user, token, isLoading: false });
    } catch (error) {
      set({ user: null, token: null, isLoading: false });
      apiClient.clearToken();
    }
  },

  clearError: () => set({ error: null }),
}));
```

**Deliverable:**
- ✓ Zustand store for auth state
- ✓ Register/login/logout actions
- ✓ Auto-recovery on page reload

---

## Day 3: Auth Pages (3 hours)

### Task 3.1: Login Page (1.5 hours)

Create `src/app/login/page.tsx`:
```typescript
'use client';

import { useRouter } from 'next/navigation';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Button } from '@/components/common/Button';
import { Input } from '@/components/common/Input';
import { Card } from '@/components/common/Card';
import { useAuthStore } from '@/lib/auth-store';
import Link from 'next/link';

const loginSchema = z.object({
  email: z.string().email('Invalid email address'),
  password: z.string().min(1, 'Password is required'),
});

type LoginFormData = z.infer<typeof loginSchema>;

export default function LoginPage() {
  const router = useRouter();
  const { login, isLoading, error, clearError } = useAuthStore();
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginFormData>({
    resolver: zodResolver(loginSchema),
  });

  const onSubmit = async (data: LoginFormData) => {
    try {
      clearError();
      await login(data.email, data.password);
      router.push('/dashboard');
    } catch (error) {
      // Error handled by store
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 py-12 px-4 sm:px-6 lg:px-8">
      <Card className="w-full max-w-md">
        <div className="mb-6">
          <h2 className="text-2xl font-bold text-gray-900">Sign In</h2>
          <p className="text-gray-600 mt-2">Enter your credentials to continue</p>
        </div>

        {error && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <Input
            label="Email Address"
            type="email"
            placeholder="you@example.com"
            {...register('email')}
            error={errors.email?.message}
          />

          <Input
            label="Password"
            type="password"
            placeholder="Your password"
            {...register('password')}
            error={errors.password?.message}
          />

          <Button
            type="submit"
            fullWidth
            loading={isLoading}
            className="mt-6"
          >
            Sign In
          </Button>
        </form>

        <div className="mt-6 border-t pt-6">
          <p className="text-center text-gray-600">
            Don't have an account?{' '}
            <Link href="/register" className="text-blue-600 hover:text-blue-700 font-medium">
              Create one
            </Link>
          </p>
        </div>
      </Card>
    </div>
  );
}
```

### Task 3.2: Register Page (1.5 hours)

Create `src/app/register/page.tsx`:
```typescript
'use client';

import { useRouter } from 'next/navigation';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Button } from '@/components/common/Button';
import { Input } from '@/components/common/Input';
import { Card } from '@/components/common/Card';
import { useAuthStore } from '@/lib/auth-store';
import Link from 'next/link';

const registerSchema = z
  .object({
    name: z.string().min(2, 'Name must be at least 2 characters'),
    email: z.string().email('Invalid email address'),
    password: z.string().min(8, 'Password must be at least 8 characters'),
    confirmPassword: z.string(),
  })
  .refine((data) => data.password === data.confirmPassword, {
    message: "Passwords don't match",
    path: ['confirmPassword'],
  });

type RegisterFormData = z.infer<typeof registerSchema>;

export default function RegisterPage() {
  const router = useRouter();
  const { register: registerUser, isLoading, error, clearError } = useAuthStore();
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<RegisterFormData>({
    resolver: zodResolver(registerSchema),
  });

  const onSubmit = async (data: RegisterFormData) => {
    try {
      clearError();
      await registerUser(data.email, data.password, data.name);
      router.push('/dashboard');
    } catch (error) {
      // Error handled by store
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 py-12 px-4 sm:px-6 lg:px-8">
      <Card className="w-full max-w-md">
        <div className="mb-6">
          <h2 className="text-2xl font-bold text-gray-900">Create Account</h2>
          <p className="text-gray-600 mt-2">Join us to start tracking stocks</p>
        </div>

        {error && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <Input
            label="Full Name"
            type="text"
            placeholder="John Investor"
            {...register('name')}
            error={errors.name?.message}
          />

          <Input
            label="Email Address"
            type="email"
            placeholder="you@example.com"
            {...register('email')}
            error={errors.email?.message}
          />

          <Input
            label="Password"
            type="password"
            placeholder="At least 8 characters"
            {...register('password')}
            error={errors.password?.message}
          />

          <Input
            label="Confirm Password"
            type="password"
            placeholder="Re-enter your password"
            {...register('confirmPassword')}
            error={errors.confirmPassword?.message}
          />

          <Button
            type="submit"
            fullWidth
            loading={isLoading}
            className="mt-6"
          >
            Create Account
          </Button>
        </form>

        <div className="mt-6 border-t pt-6">
          <p className="text-center text-gray-600">
            Already have an account?{' '}
            <Link href="/login" className="text-blue-600 hover:text-blue-700 font-medium">
              Sign in
            </Link>
          </p>
        </div>
      </Card>
    </div>
  );
}
```

**Deliverable:**
- ✓ Login page functional
- ✓ Register page with validation
- ✓ Both integrate with API
- ✓ Redirects to dashboard on success

**Test:**
```bash
npm run dev
# Visit http://localhost:3000/register
# Fill form → Submit → Should redirect to /dashboard
```

---

## Day 4: Landing Page & Navigation (3 hours)

### Task 4.1: Main Layout with Navigation (1 hour)

Create `src/components/layout/MainLayout.tsx`:
```typescript
'use client';

import { useAuthStore } from '@/lib/auth-store';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Button } from '@/components/common/Button';

interface MainLayoutProps {
  children: React.ReactNode;
}

export function MainLayout({ children }: MainLayoutProps) {
  const { user, logout } = useAuthStore();
  const router = useRouter();

  const handleLogout = () => {
    logout();
    router.push('/');
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Navigation */}
      <nav className="bg-white shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex justify-between items-center">
          <Link href="/" className="text-xl font-bold text-blue-600">
            Stock Screener
          </Link>

          <div className="flex items-center gap-4">
            {user ? (
              <>
                <Link href="/dashboard" className="text-gray-700 hover:text-gray-900">
                  Dashboard
                </Link>
                <Link href="/watchlist" className="text-gray-700 hover:text-gray-900">
                  Watchlist
                </Link>
                <Link href="/portfolio" className="text-gray-700 hover:text-gray-900">
                  Portfolio
                </Link>
                <Button onClick={handleLogout} variant="outline" size="sm">
                  Logout
                </Button>
              </>
            ) : (
              <>
                <Link href="/login">
                  <Button variant="outline" size="sm">
                    Login
                  </Button>
                </Link>
                <Link href="/register">
                  <Button variant="primary" size="sm">
                    Register
                  </Button>
                </Link>
              </>
            )}
          </div>
        </div>
      </nav>

      {/* Main content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {children}
      </main>
    </div>
  );
}
```

### Task 4.2: Landing Page with Screener Preview (1.5 hours)

Create `src/app/page.tsx`:
```typescript
'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { apiClient } from '@/lib/api-client';
import { useAuthStore } from '@/lib/auth-store';
import { MainLayout } from '@/components/layout/MainLayout';
import { Card } from '@/components/common/Card';
import { Button } from '@/components/common/Button';
import Link from 'next/link';

interface Stock {
  symbol: string;
  v2_score: number;
  quality_score: number;
  value_score: number;
  trajectory_score: number;
}

export default function HomePage() {
  const router = useRouter();
  const { user, checkAuth, isLoading: authLoading } = useAuthStore();
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    checkAuth();
  }, []);

  useEffect(() => {
    // Fetch top stocks
    const fetchStocks = async () => {
      try {
        const data = await apiClient.getStocks({ min_score: 0.70, limit: 10 });
        setStocks(data);
      } catch (error) {
        console.error('Failed to fetch stocks:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchStocks();
  }, []);

  return (
    <MainLayout>
      <div className="space-y-8">
        {/* Hero Section */}
        <div className="bg-gradient-to-r from-blue-600 to-blue-800 text-white rounded-lg p-8">
          <h1 className="text-4xl font-bold mb-4">
            Smart Stock Screening
          </h1>
          <p className="text-xl mb-6">
            Find undervalued companies using the V2 mismatch score
          </p>
          {!user && (
            <div className="flex gap-4">
              <Link href="/register">
                <Button variant="primary" className="bg-white text-blue-600 hover:bg-gray-100">
                  Get Started
                </Button>
              </Link>
              <Link href="/login">
                <Button variant="outline" className="border-white text-white">
                  Sign In
                </Button>
              </Link>
            </div>
          )}
        </div>

        {/* Top Stocks Section */}
        <div>
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-2xl font-bold">Top Stocks Today</h2>
            {user && (
              <Link href="/stocks/screener">
                <Button variant="outline">View All</Button>
              </Link>
            )}
          </div>

          {loading ? (
            <Card className="text-center py-8">
              <p className="text-gray-600">Loading top stocks...</p>
            </Card>
          ) : stocks.length === 0 ? (
            <Card className="text-center py-8">
              <p className="text-gray-600">No stocks found</p>
            </Card>
          ) : (
            <Card>
              <table className="w-full">
                <thead className="border-b">
                  <tr>
                    <th className="text-left py-3 px-4 font-semibold">Symbol</th>
                    <th className="text-right py-3 px-4 font-semibold">V2 Score</th>
                    <th className="text-right py-3 px-4 font-semibold">Quality</th>
                    <th className="text-right py-3 px-4 font-semibold">Value</th>
                    <th className="text-right py-3 px-4 font-semibold">Trajectory</th>
                    {user && <th className="text-center py-3 px-4 font-semibold">Action</th>}
                  </tr>
                </thead>
                <tbody>
                  {stocks.map((stock) => (
                    <tr key={stock.symbol} className="border-b hover:bg-gray-50">
                      <td className="py-3 px-4 font-semibold text-blue-600">
                        <Link href={`/stocks/${stock.symbol}`}>
                          {stock.symbol}
                        </Link>
                      </td>
                      <td className="py-3 px-4 text-right font-bold">
                        {stock.v2_score.toFixed(3)}
                      </td>
                      <td className="py-3 px-4 text-right">
                        {stock.quality_score.toFixed(3)}
                      </td>
                      <td className="py-3 px-4 text-right">
                        {stock.value_score.toFixed(3)}
                      </td>
                      <td className="py-3 px-4 text-right">
                        {stock.trajectory_score.toFixed(3)}
                      </td>
                      {user && (
                        <td className="py-3 px-4 text-center">
                          <Button variant="outline" size="sm">
                            +Watchlist
                          </Button>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          )}
        </div>

        {/* Info Section */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <Card>
            <h3 className="text-lg font-semibold mb-2">What is V2 Score?</h3>
            <p className="text-gray-600">
              A sector-aware mismatch score combining quality, value, and trajectory metrics to find undervalued companies.
            </p>
          </Card>
          <Card>
            <h3 className="text-lg font-semibold mb-2">Track Your Watchlist</h3>
            <p className="text-gray-600">
              Add stocks to your watchlist and track price movements and score changes in real-time.
            </p>
          </Card>
          <Card>
            <h3 className="text-lg font-semibold mb-2">Manage Portfolio</h3>
            <p className="text-gray-600">
              Keep track of your holdings, calculate P&L, and monitor your portfolio performance.
            </p>
          </Card>
        </div>
      </div>
    </MainLayout>
  );
}
```

**Deliverable:**
- ✓ Beautiful landing page
- ✓ Shows top 10 stocks
- ✓ CTAs for sign-up/login
- ✓ Navigation working

---

## Day 5: Testing & Refinement (4 hours)

### Task 5.1: Test All Auth Flows (2 hours)

**Manual Test Checklist:**
- [ ] Navigate to `/register` → Can create account → Redirects to `/dashboard`
- [ ] Navigate to `/login` → Can login → Redirects to `/dashboard`
- [ ] Page reload → Should stay logged in (token persists)
- [ ] Click logout → Redirects to `/` → Token cleared
- [ ] Navigate to `/dashboard` while logged out → Redirects to `/login`
- [ ] Invalid email → Shows error
- [ ] Password mismatch in register → Shows error
- [ ] Invalid login credentials → Shows error

### Task 5.2: Performance & Polish (2 hours)

**Performance Optimization:**
```typescript
// Use React.memo for component memoization
export const Button = React.memo(React.forwardRef(...));

// Lazy-load pages
import dynamic from 'next/dynamic';
const Dashboard = dynamic(() => import('./dashboard'), { loading: () => <Spinner /> });
```

**UI Polish:**
- [ ] Forms have proper focus states
- [ ] Buttons have hover/active states
- [ ] Error messages are clear
- [ ] Loading states show spinners
- [ ] Mobile responsive (test on mobile)
- [ ] Colors match design (blue primary, gray secondary)
- [ ] Typography is readable (14px min, good contrast)

**Browser Testing:**
- [ ] Chrome/Safari/Firefox (should all work)
- [ ] Mobile viewport (should be responsive)
- [ ] Lighthouse score > 90

**Deliverable:**
- ✓ All auth flows working
- ✓ Responsive on mobile
- ✓ No console errors
- ✓ Lighthouse > 90 score

---

## End of Week 3 Checklist

- [ ] Next.js project initialized with all dependencies
- [ ] TypeScript types generated from API
- [ ] Component library built (10+ components)
- [ ] API client working with token management
- [ ] Auth store (Zustand) managing user state
- [ ] Login page fully functional
- [ ] Register page fully functional
- [ ] Landing page with stock screener preview
- [ ] Navigation bar working
- [ ] All auth flows tested
- [ ] No console errors
- [ ] Mobile responsive
- [ ] Code formatted with Prettier
- [ ] Ready for Week 4 (Dashboard)

**Time Summary:**
- Day 1: Setup & Components: 3 hours ✓
- Day 2: API Client & Auth: 3 hours ✓
- Day 3: Auth Pages: 3 hours ✓
- Day 4: Landing & Nav: 3 hours ✓
- Day 5: Testing & Polish: 4 hours ✓
- **Total: 16 hours** ✓

**Success Metrics:**
- ✅ Can register new user
- ✅ Can login existing user
- ✅ Can see top 10 stocks on landing page
- ✅ All pages load in < 1 second
- ✅ No API errors
- ✅ Responsive on mobile

**Next:** Week 4 Dashboard & Watchlist Management

---

## Quick Reference: Commands

```bash
# Start development
npm run dev

# Generate API types (after starting backend)
npm run gen:types

# Run tests
npm run test

# Build for production
npm run build

# Format code
npx prettier --write .
```

---

## File Checklist

By end of Week 3, you should have:

```
✓ src/app/
  ✓ layout.tsx
  ✓ page.tsx (landing)
  ✓ login/page.tsx
  ✓ register/page.tsx
  ✓ dashboard/page.tsx (placeholder)

✓ src/components/common/
  ✓ Button.tsx
  ✓ Input.tsx
  ✓ Card.tsx
  ✓ Alert.tsx
  ✓ Spinner.tsx

✓ src/components/layout/
  ✓ MainLayout.tsx

✓ src/lib/
  ✓ api-client.ts
  ✓ auth-store.ts

✓ src/types/
  ✓ api.ts (generated)

✓ .env.local
  NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

Ready to execute! This plan will take you from zero to a working auth system with a beautiful landing page in 16 hours.
