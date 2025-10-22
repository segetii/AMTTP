# Build stage
FROM node:18-alpine AS builder
WORKDIR /usr/src/app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Production stage
FROM node:18-alpine
WORKDIR /usr/src/app
COPY --from=builder /usr/src/app/package*.json ./
# Install only production dependencies for a slimmer image
RUN npm ci --omit=dev
COPY --from=builder /usr/src/app/dist ./dist
EXPOSE 3000
# Basic healthcheck to ensure service is responding
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
	CMD node -e "fetch('http://localhost:3000/health').then(r=>{if(!r.ok)process.exit(1)}).catch(()=>process.exit(1))" || exit 1
CMD ["node", "dist/index.js"]