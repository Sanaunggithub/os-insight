# Build the dashboard with a pinned Node 22 Alpine release.
FROM node:22.17.1-alpine3.22 AS build

# Keep npm files and application code in a predictable directory.
WORKDIR /app

# Copy dependency manifests first so source edits do not invalidate installation.
COPY package*.json ./

# Install the locked dependency tree needed to compile and type-check the dashboard.
RUN npm ci

# Copy the dashboard source only after dependencies are installed.
COPY . .

# Compile optimized production assets in the build stage.
RUN npm run build

# Use the same pinned, compact Node release for the production runtime.
FROM node:22.17.1-alpine3.22 AS runtime

# Create an explicit non-root account for serving the dashboard.
RUN addgroup -S app && adduser -S -G app -h /app app

# Run the dashboard from a predictable application directory.
WORKDIR /app

# Mark this container as production so Next.js uses production behavior.
ENV NODE_ENV=production

# Copy manifests before installing runtime dependencies to keep this layer cacheable.
COPY package*.json ./

# Install only production packages; build-time tooling stays out of the runtime image.
RUN npm ci --omit=dev

# Copy only the compiled Next.js application and assign it to the runtime account.
COPY --from=build --chown=app:app /app/.next ./.next

# Drop root so the production web process runs as the explicitly created account.
USER app

# Document the port used by the Next.js production server.
EXPOSE 3000

# Check the web process with Node's built-in fetch, without adding curl.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 CMD ["node", "-e", "fetch('http://127.0.0.1:3000').then(r => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(1))"]

# Start Next.js directly as PID 1 so it receives SIGTERM without npm or a shell.
CMD ["node", "node_modules/next/dist/bin/next", "start", "--hostname", "0.0.0.0", "--port", "3000"]
