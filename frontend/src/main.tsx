import { createRoot } from "react-dom/client";
import App from "./App";
import { Authentication } from "./auth";
import "./styles.css";
import "./premium.css";
import "./workbench.css";
import "./review-ux.css";
const root = createRoot(document.getElementById("root")!);
async function start() {
  try {
    const response = await fetch("/api/v1/config");
    if (!response.ok)
      throw new Error("Application configuration is unavailable.");
    const config = await response.json();
    root.render(
      <Authentication config={config}>
        <App />
      </Authentication>,
    );
  } catch (e) {
    root.render(
      <div className="startup" role="alert">
        <h1>Unable to start InvoiceGuard</h1>
        <p>{(e as Error).message}</p>
        <button onClick={() => window.location.reload()}>
          Retry connection
        </button>
      </div>,
    );
  }
}
void start();
import "./focus.css";
