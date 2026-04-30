// Polyfill for crypto.randomUUID - 兼容非HTTPS环境和旧浏览器
if (!crypto.randomUUID) {
  Object.defineProperty(crypto, "randomUUID", {
    value: function (): string {
      return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (c: string) {
        const r = (Math.random() * 16) | 0;
        const v = c === "x" ? r : (r & 0x3) | 0x8;
        return v.toString(16);
      });
    },
    configurable: true,
  });
}

import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import "./index.css";
import App from "./App";
import { I18nProvider } from "./i18n";
import { ThemeProvider } from "./themes";
import { exposePluginSDK } from "./plugins";

// Expose the plugin SDK before rendering so plugins loaded via <script>
// can access React, components, etc. immediately.
exposePluginSDK();

createRoot(document.getElementById("root")!).render(
  <BrowserRouter>
    <I18nProvider>
      <ThemeProvider>
        <App />
      </ThemeProvider>
    </I18nProvider>
  </BrowserRouter>,
);
