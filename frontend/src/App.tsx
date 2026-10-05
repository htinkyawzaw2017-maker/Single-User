import { Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import NewProject from './pages/NewProject'
import ProjectShell from './pages/ProjectShell'
import { Navigate } from 'react-router-dom'

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/new" element={<NewProject />} />
        <Route path="/projects/:id/*" element={<ProjectShell />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  )
}
