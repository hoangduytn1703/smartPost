import { NavLink, Route, Routes } from "react-router-dom";
import JobsPage from "./pages/JobsPage";
import PhonePage from "./pages/PhonePage";
import ReviewPage from "./pages/ReviewPage";
import SettingsPage from "./pages/SettingsPage";

export default function App() {
  return (
    <Routes>
      <Route path="/phone" element={<PhonePage />} />
      <Route
        path="*"
        element={
          <div className="shell">
            <nav className="nav">
              <span className="nav__brand">smartPost</span>
              <div className="nav__links">
                <NavLink to="/" end>
                  Video
                </NavLink>
                <NavLink to="/settings">Cài đặt</NavLink>
              </div>
            </nav>
            <main className="main">
              <Routes>
                <Route path="/" element={<JobsPage />} />
                <Route path="/jobs/:id" element={<ReviewPage />} />
                <Route path="/settings" element={<SettingsPage />} />
              </Routes>
            </main>
          </div>
        }
      />
    </Routes>
  );
}
