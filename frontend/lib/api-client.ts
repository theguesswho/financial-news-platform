import axios, { AxiosInstance } from 'axios';

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

    if (typeof window !== 'undefined') {
      this.token = localStorage.getItem('access_token');
      if (this.token) {
        this.setAuthHeader();
      }
    }

    this.client.interceptors.response.use(
      (response) => response,
      (error) => {
        if (error.response?.status === 401) {
          localStorage.removeItem('access_token');
          if (typeof window !== 'undefined') {
            window.location.href = '/login';
          }
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

  async register(data: { email: string; password: string; name: string }) {
    const response = await this.client.post('/api/auth/register', data);
    return response.data;
  }

  async login(email: string, password: string) {
    const response = await this.client.post('/api/auth/login', { email, password });
    return response.data;
  }

  async getCurrentUser() {
    const response = await this.client.get('/api/auth/me');
    return response.data;
  }

  async getStocks(filters?: any) {
    const params = new URLSearchParams(filters || {});
    const response = await this.client.get(`/api/stocks/screener?${params}`);
    return response.data;
  }

  async getStockDetail(symbol: string) {
    const response = await this.client.get(`/api/stocks/${symbol}`);
    return response.data;
  }

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

  async getPortfolio() {
    const response = await this.client.get('/api/portfolio');
    return response.data;
  }

  async getPortfolioSummary() {
    const response = await this.client.get('/api/portfolio/summary');
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
