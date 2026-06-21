import { isDevMode } from '@angular/core';

// Local dev uses localhost. Production build automatically uses your live Render URL.
export const API_BASE_URL = isDevMode() ? 'http://localhost:8000' : 'https://prisk-backend.onrender.com'; // <-- you'll update this with your real Render URL in Part 3
