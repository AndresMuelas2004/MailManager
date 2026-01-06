import { StrictMode } from "react";
import ReactDOM from "react-dom/client";

import "./styles/globals.css";

import Providers from "./app/providers/Providers";

const rootElement = document.getElementById("root");

if (!rootElement) {
  throw new Error("Root element not found");
}

ReactDOM.createRoot(rootElement).render(
  <StrictMode>
    <Providers />
  </StrictMode>
);
