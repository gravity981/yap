import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "@tanstack/react-router";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import "./index.css";
import "@/i18n";
import { ThemeProvider } from "@/lib/theme";
import { createAppRouter } from "@/router";

const queryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 30_000 } } });
const router = createAppRouter();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </ThemeProvider>
  </StrictMode>,
);
