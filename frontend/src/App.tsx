import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { ProtectedRoute } from "./components/ProtectedRoute";
import AdminPage from "./pages/AdminPage";
import AuthPage from "./pages/AuthPage";
import CanteensPage from "./pages/CanteensPage";
import ChatPage from "./pages/ChatPage";
import DashboardPage from "./pages/DashboardPage";
import HomePage from "./pages/HomePage";
import KnowledgePage from "./pages/KnowledgePage";
import MapPage from "./pages/MapPage";
import NotificationsPage from "./pages/NotificationsPage";
import ProfilePage from "./pages/ProfilePage";
import ProcessesPage from "./pages/ProcessesPage";
import TasksPage from "./pages/TasksPage";

const protect = (element: React.ReactNode) => <ProtectedRoute>{element}</ProtectedRoute>;
const protectAdmin = (element: React.ReactNode) => <ProtectedRoute admin>{element}</ProtectedRoute>;

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<HomePage />} />
        <Route path="register" element={<AuthPage mode="register" />} />
        <Route path="login" element={<AuthPage mode="login" />} />
        <Route path="dashboard" element={protect(<DashboardPage />)} />
        <Route path="chat" element={protect(<ChatPage />)} />
        <Route path="map" element={protect(<MapPage />)} />
        <Route path="canteens" element={protect(<CanteensPage />)} />
        <Route path="notifications" element={protect(<NotificationsPage />)} />
        <Route path="tasks" element={protect(<TasksPage />)} />
        <Route path="processes" element={protect(<ProcessesPage />)} />
        <Route path="knowledge/import" element={protect(<KnowledgePage mode="import" />)} />
        <Route path="knowledge/sources" element={protect(<KnowledgePage mode="sources" />)} />
        <Route path="profile" element={protect(<ProfilePage />)} />
        <Route path="admin/*" element={protectAdmin(<AdminPage />)} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
