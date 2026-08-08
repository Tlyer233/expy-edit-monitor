import React from 'react'
import ReactDOM from 'react-dom/client'
import { HashRouter, Routes, Route } from 'react-router-dom'
import EditMonitorPage from './pages/EditMonitorPage.jsx'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <HashRouter>
      <Routes>
        <Route path="*" element={<EditMonitorPage />} />
      </Routes>
    </HashRouter>
  </React.StrictMode>
)
