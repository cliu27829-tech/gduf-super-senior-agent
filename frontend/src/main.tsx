import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { AuthProvider } from "./auth";
import { LocationProvider } from "./location";
import App from "./App";
import "./styles.css";
import "./styles/base.css";
import "./styles/components.css";
import "./styles/responsive.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider><LocationProvider><App /></LocationProvider></AuthProvider>
    </BrowserRouter>
  </StrictMode>,
);
