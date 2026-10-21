import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import PlatformDashboard from './pages/PlatformDashboard';
import {platformEntry} from './platformEntry';
import "./theme.css";
import "./ui-system.css";
import "./premium-theme.css";

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {platformEntry(location.hostname,location.search)?<PlatformDashboard/>:<App />}
  </StrictMode>,
)
