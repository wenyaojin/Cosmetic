import type { NextConfig } from "next";
import path from "node:path";

const nextConfig: NextConfig = {
  output: "standalone",
  // Pin Turbopack's workspace root to THIS folder. Without this, Next 15+
  // walks up looking for a lockfile and picks Q:\Cosmetic\package-lock.json,
  // which drags Q:\Cosmetic\downloads (1.5G of medical images) and other
  // sibling projects into the file-watcher — causing OOM / whole-system hang
  // on a network drive like Q:\.
  turbopack: {
    root: path.resolve(__dirname),
  },
};

export default nextConfig;
