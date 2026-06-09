import React from "react";
import ReactDOM from "react-dom/client";
import "@fontsource-variable/geist";
import App from "./App";
import { initTheme } from "./theme";

// Apply the saved theme before first paint to avoid a flash of the default.
initTheme();

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
