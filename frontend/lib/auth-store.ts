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
