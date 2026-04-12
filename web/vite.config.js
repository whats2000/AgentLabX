import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "node:path";
export default defineConfig({
    plugins: [react()],
    resolve: {
        alias: { "@": path.resolve(__dirname, "src") },
    },
    server: {
        port: 5173,
        proxy: {
            "/api": "http://localhost:8000",
            "/ws": { target: "ws://localhost:8000", ws: true },
        },
    },
    build: {
        outDir: "dist",
        emptyOutDir: true,
        sourcemap: true,
    },
    test: {
        environment: "jsdom",
        globals: true,
        setupFiles: ["./tests/setup.ts"],
    },
});
