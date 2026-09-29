import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import FeedbackDashboard from "./components/FeedbackDashboard.jsx";
import "./index.css";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <FeedbackDashboard />
  </StrictMode>,
);
