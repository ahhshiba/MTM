FROM node:20-alpine AS build
WORKDIR /app
COPY frontend/ /app/
RUN npm ci --include=dev --include=optional
RUN npm run build

FROM node:20-alpine
WORKDIR /app
COPY --from=build /app/ /app/
ENV PORT=80
EXPOSE 80
CMD ["npm", "run", "start", "--", "-p", "80"]
