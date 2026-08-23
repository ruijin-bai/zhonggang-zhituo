FROM node:22-alpine AS build
WORKDIR /app

COPY package.json ./
RUN npm install
COPY . .
RUN npm run check && npm run build && npm prune --omit=dev

FROM node:22-alpine AS runtime
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1
WORKDIR /app

RUN addgroup -S zhituo && adduser -S zhituo -G zhituo

COPY --from=build /app/package.json ./package.json
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/.next ./.next
COPY --from=build /app/public ./public

USER zhituo
EXPOSE 3000

CMD ["npm", "run", "start", "--", "-H", "0.0.0.0", "-p", "3000"]
