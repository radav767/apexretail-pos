import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import PlatformDashboard from './pages/PlatformDashboard';
import "./theme.css";
import "./ui-system.css";
import "./premium-theme.css";

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {new URLSearchParams(location.search).get('console')==='platform'?<PlatformDashboard/>:<App />}
  </StrictMode>,
)
