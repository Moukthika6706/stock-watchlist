import axios from 'axios';
import { getToken, handleAuthFailure } from './auth';

export const API_URL = process.env.REACT_APP_API_URL || 'http://127.0.0.1:5000';

const api = axios.create({ baseURL: API_URL, timeout: 15000 });

api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

function requestCarriedToken(config) {
  const headers = config?.headers;
  if (!headers) return false;
  const value = typeof headers.get === 'function' ? headers.get('Authorization') : headers.Authorization;
  return Boolean(value);
}

// Any auth failure on a call that carried our token means the token is no good:
// 401 = missing or expired, 422 = flask-jwt-extended's code for malformed or
// tampered tokens. Either way, drop it and go back to login. A 401 from /login
// itself (bad credentials) carries no token and is left to the form.
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status;
    if ((status === 401 || status === 422) && requestCarriedToken(error.config)) {
      handleAuthFailure();
    }
    return Promise.reject(error);
  }
);

export function errorMessage(error, fallback = 'Something went wrong. Please try again.') {
  if (error?.response?.data?.message) return error.response.data.message;
  if (error?.code === 'ERR_NETWORK' || error?.message === 'Network Error') {
    return `Cannot reach the API at ${API_URL}. Is the backend running?`;
  }
  return fallback;
}

export default api;
