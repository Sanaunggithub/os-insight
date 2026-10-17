FROM node:22-alpine

WORKDIR /app

COPY package*.json ./
# npm ci uses the committed lockfile for repeatable container installs.
RUN npm ci

COPY . .

# Produce optimized static assets before starting the production server.
RUN npm run build

EXPOSE 3000

CMD ["npm", "run", "start"]
