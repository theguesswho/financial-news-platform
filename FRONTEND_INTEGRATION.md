# Frontend Integration Guide

This document outlines how the Next.js/React frontend will integrate with the FastAPI backend.

---

## Architecture Overview

```
┌────────────────────────────────────────────────┐
│         Next.js Frontend (Vercel)              │
│  • Landing page with screener                  │
│  • Auth pages (register/login)                 │
│  • Dashboard, watchlist, portfolio             │
│  • Stock detail pages                          │
└────────────────────────────────────────────────┘
                       ↓ REST API
┌────────────────────────────────────────────────┐
│      FastAPI Backend (Railway/Heroku)          │
│  • /api/auth      (register, login, me)        │
│  • /api/watchlist (CRUD operations)            │
│  • /api/portfolio (holdings, P&L)              │
│  • /api/stocks    (screener, detail, search)   │
└────────────────────────────────────────────────┘
                       ↓ SQL Queries
┌────────────────────────────────────────────────┐
│       PostgreSQL (Production Database)         │
└────────────────────────────────────────────────┘
```

---

## Environment Setup

### Next.js Configuration

Create `.env.local` in the frontend root:
```env
NEXT_PUBLIC_API_URL=http://localhost:8000        # Development
# NEXT_PUBLIC_API_URL=https://api.yoursite.com   # Production
```

### API Client Setup

Create `lib/api-client.ts`:
```typescript
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

class APIClient {
  private token: string | null = null;

  constructor() {
    // Load token from localStorage on initialization
    if (typeof window !== "undefined") {
      this.token = localStorage.getItem("access_token");
    }
  }

  setToken(token: string) {
    this.token = token;
    localStorage.setItem("access_token", token);
  }

  clearToken() {
    this.token = null;
    localStorage.removeItem("access_token");
  }

  private async request<T>(
    method: string,
    path: string,
    body?: any
  ): Promise<T> {
    const headers: HeadersInit = {
      "Content-Type": "application/json",
    };

    if (this.token) {
      headers["Authorization"] = `Bearer ${this.token}`;
    }

    const response = await fetch(`${API_URL}${path}`, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });

    if (!response.ok) {
      if (response.status === 401) {
        // Token expired or invalid
        this.clearToken();
        // Redirect to login
        window.location.href = "/login";
      }
      const error = await response.json();
      throw new Error(error.detail || "API request failed");
    }

    if (response.status === 204) {
      return null as T;
    }

    return response.json();
  }

  // Authentication
  async register(email: string, password: string, name: string) {
    return this.request("/api/auth/register", "POST", {
      email,
      password,
      name,
    });
  }

  async login(email: string, password: string) {
    return this.request("/api/auth/login", "POST", {
      email,
      password,
    });
  }

  async getCurrentUser() {
    return this.request("/api/auth/me", "GET");
  }

  // Watchlist
  async getWatchlist() {
    return this.request("/api/watchlist", "GET");
  }

  async addToWatchlist(data: any) {
    return this.request("/api/watchlist", "POST", data);
  }

  async removeFromWatchlist(symbol: string) {
    return this.request(`/api/watchlist/${symbol}`, "DELETE");
  }

  // Portfolio
  async getPortfolio() {
    return this.request("/api/portfolio", "GET");
  }

  async getPortfolioSummary() {
    return this.request("/api/portfolio/summary", "GET");
  }

  async addHolding(data: any) {
    return this.request("/api/portfolio", "POST", data);
  }

  async removeHolding(symbol: string) {
    return this.request(`/api/portfolio/${symbol}`, "DELETE");
  }

  // Stocks
  async screenStocks(filters?: any) {
    const params = new URLSearchParams(filters || {});
    return this.request(`/api/stocks/screener?${params}`, "GET");
  }

  async getStockDetail(symbol: string) {
    return this.request(`/api/stocks/${symbol}`, "GET");
  }

  async getStockV2Score(symbol: string) {
    return this.request(`/api/stocks/${symbol}/v2-score`, "GET");
  }

  async searchStocks(query: string, limit = 10) {
    return this.request(
      `/api/stocks/search/${query}?limit=${limit}`,
      "GET"
    );
  }
}

export const apiClient = new APIClient();
```

---

## Component Examples

### Login Component

```typescript
// pages/login.tsx
import { useState } from "react";
import { apiClient } from "@/lib/api-client";
import { useRouter } from "next/router";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");

    try {
      const response = await apiClient.login(email, password);
      apiClient.setToken(response.access_token);
      router.push("/dashboard");
    } catch (err) {
      setError(err.message || "Login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleLogin}>
      <input
        type="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="Email"
        required
      />
      <input
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        placeholder="Password"
        required
      />
      {error && <p style={{ color: "red" }}>{error}</p>}
      <button type="submit" disabled={loading}>
        {loading ? "Logging in..." : "Login"}
      </button>
    </form>
  );
}
```

### Watchlist Component

```typescript
// components/Watchlist.tsx
import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api-client";

interface WatchlistEntry {
  id: number;
  symbol: string;
  entry_price: number;
  notes: string;
  updated_at: string;
}

export default function Watchlist() {
  const [entries, setEntries] = useState<WatchlistEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadWatchlist();
  }, []);

  const loadWatchlist = async () => {
    try {
      const data = await apiClient.getWatchlist();
      setEntries(data);
    } catch (err) {
      console.error("Failed to load watchlist:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleRemove = async (symbol: string) => {
    try {
      await apiClient.removeFromWatchlist(symbol);
      setEntries(entries.filter((e) => e.symbol !== symbol));
    } catch (err) {
      console.error("Failed to remove from watchlist:", err);
    }
  };

  if (loading) return <div>Loading...</div>;

  return (
    <div>
      <h2>My Watchlist</h2>
      <table>
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Entry Price</th>
            <th>Notes</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((entry) => (
            <tr key={entry.id}>
              <td>{entry.symbol}</td>
              <td>${entry.entry_price?.toFixed(2)}</td>
              <td>{entry.notes}</td>
              <td>
                <button onClick={() => handleRemove(entry.symbol)}>
                  Remove
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

### Stock Screener Component

```typescript
// components/StockScreener.tsx
import { useState } from "react";
import { apiClient } from "@/lib/api-client";

interface Stock {
  symbol: string;
  v2_score: number;
  quality_score: number;
  value_score: number;
  trajectory_score: number;
  sector: string;
  pe_ratio: number;
}

export default function StockScreener() {
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [filters, setFilters] = useState({
    min_score: 0.7,
    sector: "",
    limit: 20,
  });
  const [loading, setLoading] = useState(false);

  const handleSearch = async () => {
    setLoading(true);
    try {
      const data = await apiClient.screenStocks(filters);
      setStocks(data);
    } catch (err) {
      console.error("Screener failed:", err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div style={{ marginBottom: "20px" }}>
        <label>
          Min V2 Score:
          <input
            type="number"
            min="0"
            max="1"
            step="0.1"
            value={filters.min_score}
            onChange={(e) =>
              setFilters({ ...filters, min_score: parseFloat(e.target.value) })
            }
          />
        </label>
        <label>
          Sector:
          <input
            type="text"
            value={filters.sector}
            onChange={(e) =>
              setFilters({ ...filters, sector: e.target.value })
            }
          />
        </label>
        <button onClick={handleSearch} disabled={loading}>
          {loading ? "Screening..." : "Search"}
        </button>
      </div>

      <table>
        <thead>
          <tr>
            <th>Symbol</th>
            <th>V2 Score</th>
            <th>Quality</th>
            <th>Value</th>
            <th>Trajectory</th>
            <th>Sector</th>
            <th>P/E</th>
          </tr>
        </thead>
        <tbody>
          {stocks.map((stock) => (
            <tr key={stock.symbol}>
              <td>{stock.symbol}</td>
              <td>{stock.v2_score.toFixed(3)}</td>
              <td>{stock.quality_score.toFixed(3)}</td>
              <td>{stock.value_score.toFixed(3)}</td>
              <td>{stock.trajectory_score.toFixed(3)}</td>
              <td>{stock.sector}</td>
              <td>{stock.pe_ratio?.toFixed(1)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

### Stock Detail Page

```typescript
// pages/stocks/[symbol].tsx
import { useRouter } from "next/router";
import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api-client";

export default function StockDetailPage() {
  const router = useRouter();
  const { symbol } = router.query;
  const [stock, setStock] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!symbol) return;

    const loadStock = async () => {
      try {
        const data = await apiClient.getStockDetail(symbol as string);
        setStock(data);
      } catch (err) {
        console.error("Failed to load stock:", err);
      } finally {
        setLoading(false);
      }
    };

    loadStock();
  }, [symbol]);

  if (loading) return <div>Loading...</div>;
  if (!stock) return <div>Stock not found</div>;

  const { fundamentals, v2_score } = stock;

  return (
    <div>
      <h1>{symbol}</h1>

      <section>
        <h2>V2 Mismatch Score</h2>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)" }}>
          <div>
            <strong>Quality:</strong>
            <br />
            {v2_score.quality_score.toFixed(3)}
          </div>
          <div>
            <strong>Value:</strong>
            <br />
            {v2_score.value_score.toFixed(3)}
          </div>
          <div>
            <strong>Trajectory:</strong>
            <br />
            {v2_score.trajectory_score.toFixed(3)}
          </div>
        </div>
        <p style={{ fontSize: "24px", fontWeight: "bold" }}>
          Overall: {v2_score.v2_score.toFixed(3)}
        </p>
      </section>

      <section>
        <h2>Fundamentals</h2>
        <table>
          <tbody>
            <tr>
              <td>P/E Ratio</td>
              <td>{fundamentals.pe_trailing?.toFixed(2)}</td>
            </tr>
            <tr>
              <td>PEG Ratio</td>
              <td>{fundamentals.peg_ratio?.toFixed(2)}</td>
            </tr>
            <tr>
              <td>ROE</td>
              <td>{(fundamentals.roe * 100)?.toFixed(1)}%</td>
            </tr>
            <tr>
              <td>Gross Margin</td>
              <td>{(fundamentals.gross_margin * 100)?.toFixed(1)}%</td>
            </tr>
            <tr>
              <td>Operating Margin</td>
              <td>{(fundamentals.operating_margin * 100)?.toFixed(1)}%</td>
            </tr>
            <tr>
              <td>Net Margin</td>
              <td>{(fundamentals.net_margin * 100)?.toFixed(1)}%</td>
            </tr>
            <tr>
              <td>Sector</td>
              <td>{fundamentals.sector}</td>
            </tr>
            <tr>
              <td>Industry</td>
              <td>{fundamentals.industry}</td>
            </tr>
          </tbody>
        </table>
      </section>

      <section>
        <h2>Actions</h2>
        <button>Add to Watchlist</button>
        <button>Add to Portfolio</button>
      </section>
    </div>
  );
}
```

---

## State Management (Context API)

```typescript
// context/AuthContext.tsx
import React, { useState, useEffect, ReactNode } from "react";
import { apiClient } from "@/lib/api-client";

interface User {
  id: number;
  email: string;
  name: string;
}

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  register: (email: string, password: string, name: string) => Promise<void>;
}

const AuthContext = React.createContext<AuthContextType | undefined>(
  undefined
);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    // Check if user is already logged in on app load
    const checkAuth = async () => {
      try {
        const currentUser = await apiClient.getCurrentUser();
        setUser(currentUser);
      } catch {
        setUser(null);
      } finally {
        setIsLoading(false);
      }
    };

    checkAuth();
  }, []);

  const login = async (email: string, password: string) => {
    const response = await apiClient.login(email, password);
    apiClient.setToken(response.access_token);
    setUser(response.user);
  };

  const register = async (
    email: string,
    password: string,
    name: string
  ) => {
    const response = await apiClient.register(email, password, name);
    apiClient.setToken(response.access_token);
    setUser(response.user);
  };

  const logout = () => {
    apiClient.clearToken();
    setUser(null);
  };

  return (
    <AuthContext.Provider
      value={{ user, isLoading, login, logout, register }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = React.useContext(AuthContext);
  if (context === undefined) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
}
```

---

## Protected Routes

```typescript
// components/ProtectedRoute.tsx
import { useAuth } from "@/context/AuthContext";
import { useRouter } from "next/router";
import { ReactNode } from "react";

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { user, isLoading } = useAuth();
  const router = useRouter();

  if (isLoading) {
    return <div>Loading...</div>;
  }

  if (!user) {
    router.push("/login");
    return null;
  }

  return <>{children}</>;
}
```

---

## Error Handling

```typescript
// hooks/useAPI.ts
import { useState } from "react";
import { apiClient } from "@/lib/api-client";

export function useAPI<T>(
  apiCall: () => Promise<T>
) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const execute = async () => {
    setLoading(true);
    setError(null);

    try {
      const result = await apiCall();
      setData(result);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "An error occurred"
      );
    } finally {
      setLoading(false);
    }
  };

  return { data, error, loading, execute };
}
```

---

## Page Structure (Next.js)

```
pages/
├── index.tsx                    # Landing page with screener
├── login.tsx                    # Login page
├── register.tsx                 # Registration page
├── dashboard.tsx                # User dashboard
├── watchlist.tsx                # Watchlist page
├── portfolio.tsx                # Portfolio page
├── portfolio/[symbol].tsx       # Edit holding
├── stocks/
│   ├── screener.tsx             # Advanced screener
│   ├── [symbol].tsx             # Stock detail page
│   └── search.tsx               # Search results
├── account.tsx                  # Account settings
└── api/
    └── [proxy].ts               # Optional: API proxy
```

---

## Deployment

### Frontend (Vercel)

```bash
npm run build
vercel deploy
```

Set environment variable in Vercel:
```
NEXT_PUBLIC_API_URL=https://api.yourdomain.com
```

### Backend (Railway/Heroku)

```bash
git push heroku main
```

Or:
```
railway deploy
```

---

## Summary

The frontend will:
1. Use the API client to communicate with FastAPI
2. Store JWT token in localStorage
3. Include token in all authenticated requests
4. Handle 401 errors by redirecting to login
5. Use Context API for global auth state
6. Implement protected routes for user-specific pages
7. Provide real-time stock screening and portfolio tracking

The separation of concerns keeps the frontend and backend loosely coupled, allowing independent deployment and scaling.
