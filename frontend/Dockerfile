# Build stage
FROM node:20-alpine AS build

WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
RUN npm run build

# Strip content hashes from built filenames so nginx sub_filter always works
# Also update references in index.html
RUN apk add --no-cache perl \
 && cd /app/build \
 && perl -i -pe 's|/static/js/main\.[a-f0-9]+\.js|/static/js/main.js|g; s|/static/css/main\.[a-f0-9]+\.css|/static/css/main.css|g' index.html \
 && cd /app/build/static/js \
 && for f in main.*.js; do mv "$f" main.js 2>/dev/null || true; done \
 && for f in main.*.js.map; do mv "$f" main.js.map 2>/dev/null || true; done \
 && cd /app/build/static/css \
 && for f in main.*.css; do mv "$f" main.css 2>/dev/null || true; done

# Production stage
FROM nginx:alpine

# Copy built files
COPY --from=build /app/build /usr/share/nginx/html

# Copy nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
