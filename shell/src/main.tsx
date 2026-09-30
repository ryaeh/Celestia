import React from "react";
import ReactDOM from "react-dom/client";
import "@fontsource-variable/geist";
import App from "./App";
import Overlay from "./pages/Overlay";
import { isOverlayView } from "./lib/overlayWindow";
import { initTheme } from "./theme";

// Apply the saved theme before first paint to avoid a flash of the default.
initTheme();

// The same bundle serves the main window and the companion bubble
// (tauri.conf.json window "overlay" loads index.html?view=overlay).
const overlay = isOverlayView();
if (overlay) document.documentElement.classList.add("overlay-view");

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    {overlay ? <Overlay /> : <App />}
  </React.StrictMode>,
);
