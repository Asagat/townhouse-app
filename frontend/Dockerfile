FROM node:20-alpine

WORKDIR /app
RUN chown -R node:node /app

COPY --chown=node:node package*.json ./

COPY --chown=node:node *.tgz ./ 

USER node
RUN npm install

COPY --chown=node:node . .

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
