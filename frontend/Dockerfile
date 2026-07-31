# Build Stage
FROM node:20-alpine AS build

WORKDIR /app

# Copy package configs
COPY package.json package-lock.json* ./

# Install npm dependencies
RUN npm install

# Copy source code and build
COPY . .
RUN npm run build

# Production Stage
FROM nginx:1.25-alpine

# Copy built static assets from build stage
COPY --from=build /app/dist /usr/share/nginx/html

# Copy custom Nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Expose port 80
EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
