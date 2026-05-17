FROM node:22-alpine
WORKDIR /app
COPY dashboard/package*.json ./
RUN npm install
COPY dashboard/ ./
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
