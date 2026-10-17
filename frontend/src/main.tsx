import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.tsx'
import './index.css'
import './styles/native-agent.css'
import './styles/course-workspace.css'
import './styles/course-portal.css'
import './styles/disclosure.css'
import { initializeSystemAppearance } from './store/useSystemStore'
import { registerSW } from 'virtual:pwa-register'

initializeSystemAppearance()
registerSW({ immediate: true })

async function start() {
  const params = new URLSearchParams(location.search)
  if (import.meta.env.DEV && params.has('preview')) {
    sessionStorage.setItem('unimind-design-preview', params.get('preview') === '0' ? '0' : '1')
  }
  const preview = import.meta.env.DEV && sessionStorage.getItem('unimind-design-preview') === '1'
  const PreviewControls = preview ? (await import('./dev/FullAppPreview')).PreviewControls : null
  ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
      {PreviewControls && <PreviewControls />}
      <App />
    </React.StrictMode>,
  )
}

void start()
