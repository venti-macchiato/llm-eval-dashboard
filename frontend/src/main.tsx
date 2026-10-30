import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./styles/base.css";
import "./styles/components.css";
import "./styles/views/leaderboard.css";
import "./styles/views/history.css";
import "./styles/views/compare.css";
import "./styles/views/workbench.css";
import { App } from "./App";
import { ThemeProvider } from "./lib/theme";

const container = document.getElementById("root");
if (!container) throw new Error("#root element not found");

createRoot(container).render(
  <StrictMode>
    <ThemeProvider>
      <App />
    </ThemeProvider>
  </StrictMode>,
);
