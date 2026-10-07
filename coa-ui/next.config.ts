import type { NextConfig } from "next"

const nextConfig: NextConfig = {
  // The Docker image runs the standalone server.
  output: "standalone",
  experimental: {
    // Server Actions carry the CoA PDF; the default body limit is 1 MB.
    serverActions: { bodySizeLimit: "10mb" },
  },
}

export default nextConfig
