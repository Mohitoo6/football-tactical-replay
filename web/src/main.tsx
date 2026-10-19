import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
// base styles first, so each page's own CSS (imported by App's pages) can override them
import './styles/base.css';
import App from './App';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
