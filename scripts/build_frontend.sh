#!/bin/bash
set -e

cd frontend

npm run build

# Build .amplify-hosting structure required for Amplify WEB_COMPUTE SSR
mkdir -p .amplify-hosting/compute/default
mkdir -p .amplify-hosting/static/_next

# Copy Next.js standalone server + its bundled node_modules/.next/server
cp -r .next/standalone/. .amplify-hosting/compute/default/

# Static files must be copied alongside the server (not included in standalone by default)
cp -r .next/static .amplify-hosting/compute/default/.next/static

# CDN-served static assets
cp -r .next/static .amplify-hosting/static/_next/static
if [ -d public ]; then
  cp -r public/. .amplify-hosting/static/
fi

# Wrapper script that bakes build-time env vars into the server process.
# Amplify injects env vars at build time; this captures them so the
# Next.js API routes can reach the backend at runtime.
cat > .amplify-hosting/compute/default/run.js << RUNJS
process.env.BACKEND_API_URL = process.env.BACKEND_API_URL || "${BACKEND_API_URL}";
process.env.BACKEND_API_KEY = process.env.BACKEND_API_KEY || "${BACKEND_API_KEY}";
process.env.BACKEND_STREAMING_URL = process.env.BACKEND_STREAMING_URL || "${BACKEND_STREAMING_URL}";
require('./server.js');
RUNJS

# Routing manifest
cat > .amplify-hosting/deploy-manifest.json << 'EOF'
{
  "version": 1,
  "routes": [
    {
      "path": "/_next/static/*",
      "target": { "kind": "Static" },
      "definition": { "cache": "public, max-age=31536000, immutable" }
    },
    {
      "path": "/*.*",
      "target": { "kind": "Static" },
      "fallback": { "kind": "Compute", "src": "default" }
    },
    {
      "path": "/*",
      "target": { "kind": "Compute", "src": "default" }
    }
  ],
  "computeResources": [
    {
      "name": "default",
      "runtime": "nodejs20.x",
      "entrypoint": "run.js"
    }
  ],
  "framework": {
    "name": "Next.js",
    "version": "14.2.35"
  }
}
EOF

echo "Build complete. .amplify-hosting structure created."
