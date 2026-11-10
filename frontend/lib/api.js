/**
 * API client for backend communication
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

/**
 * Get auth token from localStorage
 */
function getToken() {
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('token');
    // Clean token - remove quotes and whitespace if present
    if (token) {
      return token.trim().replace(/^["']|["']$/g, '');
    }
    return null;
  }
  return null;
}

/**
 * Set auth token in localStorage
 */
function setToken(token) {
  if (typeof window !== 'undefined') {
    // Ensure token is a string and clean (no extra quotes)
    const cleanToken = String(token).trim().replace(/^["']|["']$/g, '');
    localStorage.setItem('token', cleanToken);
    // Only log in development mode
    if (process.env.NODE_ENV === 'development') {
      console.log('Token stored (first 30 chars):', cleanToken.substring(0, 30) + '...');
    }
  }
}

/**
 * Remove auth token from localStorage
 */
function removeToken() {
  if (typeof window !== 'undefined') {
    localStorage.removeItem('token');
  }
}

/**
 * Returns true for fetch/network errors (connection refused, CORS, etc.)
 */
function isNetworkError(error) {
  return (
    error.name === 'TypeError' ||
    error.message?.includes('fetch') ||
    error.message === 'Failed to fetch' ||
    error.message?.includes('Cannot connect')
  );
}

/**
 * Standard user-facing message when the backend is unreachable
 */
function networkErrorMessage() {
  return `Cannot connect to backend server at ${API_URL}. Please make sure:\n1. The backend server is running\n2. CORS is properly configured\n3. The API URL is correct`;
}

/**
 * Make API request with authentication
 */
async function apiRequest(endpoint, options = {}) {
  const token = getToken();
  const headers = {
    'Content-Type': 'application/json',
    ...options.headers,
  };

  if (token) {
    // Ensure token is clean (no extra quotes or whitespace)
    const cleanToken = token.trim().replace(/^["']|["']$/g, '');
    headers['Authorization'] = `Bearer ${cleanToken}`;
    if (process.env.NODE_ENV === 'development') {
      console.log('Token being sent (first 30 chars):', cleanToken.substring(0, 30) + '...');
      console.log('Token length:', cleanToken.length);
    }
  } else {
    if (process.env.NODE_ENV === 'development') {
      console.warn('No token found for request to:', endpoint);
    }
  }

  const config = {
    ...options,
    headers,
  };

  try {
    if (process.env.NODE_ENV === 'development') {
      console.log('Making request to:', `${API_URL}${endpoint}`);
    }

    let response;
    try {
      response = await fetch(`${API_URL}${endpoint}`, config);
    } catch (fetchError) {
      // Catch network errors (CORS, connection refused, etc.)
      if (process.env.NODE_ENV === 'development') {
        console.error('Fetch error:', fetchError);
      }
      if (isNetworkError(fetchError)) {
        throw new Error(networkErrorMessage());
      }
      throw fetchError;
    }
    
    // Handle network errors
    if (!response) {
      throw new Error('Network error: Could not connect to server. Make sure the backend is running at ' + API_URL);
    }
    
    // Handle non-JSON responses (e.g., 204 No Content)
    const contentType = response.headers.get('content-type');
    if (!contentType || !contentType.includes('application/json')) {
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      // For successful non-JSON responses (like 204), return null
      return null;
    }

    // Try to parse JSON, but handle empty responses gracefully
    let data;
    try {
      const text = await response.text();
      if (!text || text.trim() === '') {
        // Empty response body
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        return null;
      }
      data = JSON.parse(text);
    } catch (parseError) {
      // If JSON parsing fails but response is OK, return null
      if (response.ok) {
        return null;
      }
      // If response is not OK, throw error
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    if (!response.ok) {
      // Handle authentication errors - redirect to login (but not if we're already on login page)
      if (response.status === 401) {
        // Don't redirect if we're already trying to login (prevents page refresh on incorrect credentials)
        if (endpoint !== '/auth/login' && typeof window !== 'undefined') {
          console.error('401 Unauthorized error - redirecting to login');
          removeToken();
          window.location.href = '/login';
        }
      }
      
      // Handle error message extraction - FastAPI validation errors can be objects or arrays
      let errorMessage = `HTTP error! status: ${response.status}`;
      
      if (data) {
        if (typeof data.detail === 'string') {
          errorMessage = data.detail;
        } else if (Array.isArray(data.detail)) {
          // Handle validation error arrays: [{"loc": ["field"], "msg": "error", "type": "type"}]
          const messages = data.detail.map(err => {
            if (typeof err === 'string') return err;
            if (err.msg) return `${err.loc?.join('.') || 'Field'}: ${err.msg}`;
            return JSON.stringify(err);
          });
          errorMessage = messages.join(', ');
        } else if (typeof data.detail === 'object' && data.detail !== null) {
          // Handle object errors - try to extract meaningful message
          if (data.detail.msg) {
            errorMessage = data.detail.msg;
          } else if (data.detail.message) {
            errorMessage = data.detail.message;
          } else {
            errorMessage = JSON.stringify(data.detail);
          }
        } else if (typeof data.message === 'string') {
          errorMessage = data.message;
        } else if (data.message) {
          errorMessage = String(data.message);
        }
      }
      
      throw new Error(errorMessage);
    }

    return data;
  } catch (error) {
    if (isNetworkError(error)) {
      // Re-use already-formatted message if present, otherwise create one
      throw new Error(
        error.message?.includes('Cannot connect') ? error.message : networkErrorMessage()
      );
    }
    throw error;
  }
}

/**
 * API methods
 */
export const api = {
  // Auth
  register: (email, username, password) =>
    apiRequest('/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, username, password }),
    }),

  login: (email, password) =>
    apiRequest('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),

  // Medical History
  getMedicalHistory: () =>
    apiRequest('/medical/history', {
      method: 'GET',
    }),

  updateMedicalHistory: (data) =>
    apiRequest('/medical/history', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // User Preferences
  getUserPreferences: () =>
    apiRequest('/preferences', {
      method: 'GET',
    }),

  updateUserPreferences: (data) =>
    apiRequest('/preferences', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // Agents
  chatWithAgent: (message, agentType = 'physical-fitness', imageBase64 = null) =>
    apiRequest(`/agents/${agentType}/chat`, {
      method: 'POST',
      body: JSON.stringify({ 
        message, 
        agent_type: agentType,
        image_base64: imageBase64 
      }),
    }),

  /**
   * Stream chat with coordinator agent using Server-Sent Events (SSE)
   * @param {string} message - User message
   * @param {string|null} imageBase64 - Optional base64 image
   * @param {Function} onStep - Callback for step updates: (stepText: string) => void
   * @param {Function} onResponse - Callback for final response: (response: object) => void
   * @param {Function} onError - Callback for errors: (error: string) => void
   * @returns {Promise<void>}
   */
  chatWithCoordinatorAgentStream: async (message, imageBase64 = null, onStep, onResponse, onError) => {
    const token = getToken();
    if (!token) {
      onError('Not authenticated');
      return;
    }

    try {
      const response = await fetch(`${API_URL}/agents/coordinator/chat/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          message,
          agent_type: 'coordinator',
          image_base64: imageBase64,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Failed to get response' }));
        onError(errorData.detail || `HTTP ${response.status}`);
        return;
      }

      // Read SSE stream
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || ''; // Keep incomplete line in buffer

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6)); // Remove 'data: ' prefix
              
              if (data.type === 'step') {
                onStep(data.data);
              } else if (data.type === 'response') {
                onResponse(data.data);
              } else if (data.type === 'error') {
                onError(data.data.error || 'Unknown error');
              }
            } catch (e) {
              console.error('Failed to parse SSE data:', e, line);
            }
          }
        }
      }
    } catch (error) {
      console.error('Streaming error:', error);
      onError(error.message || 'Failed to connect to server');
    }
  },

  // Conversation History
  getConversationHistory: (agentType = null) => {
    const url = agentType 
      ? `/conversation/messages?agent_type=${agentType}`
      : '/conversation/messages'
    return apiRequest(url, {
      method: 'GET',
    })
  },

  saveMessage: (role, content, warnings = null, imagePath = null, agentType = 'coordinator') =>
    apiRequest('/conversation/messages', {
      method: 'POST',
      body: JSON.stringify({ role, content, warnings, image_path: imagePath, agent_type: agentType }),
    }),

  uploadImage: async (imageBase64) => {
    let response
    try {
      response = await fetch(`${API_URL}/conversation/upload-image`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${getToken()?.trim().replace(/^["']|["']$/g, '')}`,
        },
        body: JSON.stringify({ image_base64: imageBase64 }),
      })
    } catch (fetchErr) {
      throw new Error(isNetworkError(fetchErr) ? networkErrorMessage() : fetchErr.message)
    }
    if (!response.ok) {
      const body = await response.json().catch(() => ({}))
      throw new Error(body.detail || body.error || `Upload failed (HTTP ${response.status})`)
    }
    return response.json()
  },

  clearConversationHistory: () =>
    apiRequest('/conversation/messages', {
      method: 'DELETE',
    }),

  deleteAccount: () =>
    apiRequest('/auth/delete-account', {
      method: 'DELETE',
    }),

  // Logs
  getWorkoutLogs: (limit = 10, offset = 0) =>
    apiRequest(`/logs/workouts?limit=${limit}&offset=${offset}`, {
      method: 'GET',
    }),
  
  getNutritionLogs: (limit = 10, offset = 0) =>
    apiRequest(`/logs/nutrition?limit=${limit}&offset=${offset}`, {
      method: 'GET',
    }),
  
  getMentalFitnessLogs: (limit = 10, offset = 0) =>
    apiRequest(`/logs/mental-fitness?limit=${limit}&offset=${offset}`, {
      method: 'GET',
    }),

  deleteWorkoutLog: (logId) =>
    apiRequest(`/logs/workouts/${logId}`, {
      method: 'DELETE',
    }),

  deleteNutritionLog: (logId) =>
    apiRequest(`/logs/nutrition/${logId}`, {
      method: 'DELETE',
    }),

  deleteMentalFitnessLog: (logId) =>
    apiRequest(`/logs/mental-fitness/${logId}`, {
      method: 'DELETE',
    }),
};

export { getToken, setToken, removeToken, API_URL };

