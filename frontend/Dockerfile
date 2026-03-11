FROM node:20-alpine
WORKDIR /app
# Смена владельца до установки зависимостей
RUN chown -R node:node /app
COPY --chown=node:node package*.json ./

RUN npm install
COPY --chown=node:node . .
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
